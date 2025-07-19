# hertz/services/file_cache.py
import os
import shutil
import asyncio
import logging
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from ..config import Config
from ..db.client import (
    get_file_cache, create_file_cache, remove_file_cache,
    get_total_cache_size, get_oldest_file_caches
)

logger = logging.getLogger(__name__)

class FileCacheProvider:
    """Provides caching functionality for audio files"""
    
    def __init__(self, config: Config):
        self.config = config
        self.cache_dir = config.CACHE_DIR
        self.cache_limit_bytes = config.cache_limit_bytes
        self._eviction_lock = asyncio.Lock()
        
        # Ensure cache and temp directories exist
        os.makedirs(self.cache_dir, exist_ok=True)
        os.makedirs(os.path.join(self.cache_dir, 'tmp'), exist_ok=True)
    
    async def get_path_for(self, hash_key: str) -> Optional[str]:
        """Get path to cached file if it exists, otherwise return None"""
        # Check if in database
        cache_entry = await get_file_cache(hash_key)
        
        if not cache_entry:
            return None
        
        # Check if file exists
        file_path = os.path.join(self.cache_dir, hash_key)
        if not os.path.exists(file_path):
            # File exists in DB but not on disk, clean up
            await remove_file_cache(hash_key)
            return None
        
        logger.info(f"Using cached file {hash_key} (last accessed: {cache_entry.accessedAt})")
        return file_path
    
    async def cache_file(self, hash_key: str, file_path: str) -> str:
        """Cache a file and add to database with proper locking"""
        # Create temp path for download
        tmp_dir = os.path.join(self.cache_dir, 'tmp')
        os.makedirs(tmp_dir, exist_ok=True)
        
        tmp_path = os.path.join(tmp_dir, f"{hash_key}.tmp")
        final_path = os.path.join(self.cache_dir, hash_key)
        
        # Skip if already cached
        if os.path.exists(final_path):
            # Update accessed time
            await get_file_cache(hash_key)
            return final_path
        
        try:
            # Copy the file to temp location first if it's different
            if os.path.abspath(file_path) != os.path.abspath(final_path):
                shutil.copy2(file_path, tmp_path)
                
                # Get file size
                file_size = os.path.getsize(tmp_path)
                
                # Move to final location
                shutil.move(tmp_path, final_path)
            else:
                # File is already in the right place, just get size
                file_size = os.path.getsize(file_path)
            
            # Register in database
            await create_file_cache(hash_key, file_size)
            
            logger.info(f"Successfully cached file {hash_key} ({file_size} bytes)")
            
            # Run eviction if needed
            await self.evict_if_needed()
            
            return final_path
            
        except Exception as e:
            logger.error(f"Error caching file {hash_key}: {e}")
            # Clean up tmp file if it exists
            if 'tmp_path' in locals() and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception as cleanup_error:
                    logger.error(f"Error cleaning up tmp file: {cleanup_error}")
            raise
    
    async def cleanup(self) -> None:
        """Clean up orphaned cache files and evict if over limit"""
        logger.info("Cleaning up file cache...")
        
        await self.remove_orphaned_files()
        await self.evict_if_needed()
    
    async def remove_orphaned_files(self) -> None:
        """Remove files in cache directory that aren't in database"""
        logger.info("Checking for orphaned cache files...")
        
        # Get list of all files in cache directory
        cache_files = []
        for file_name in os.listdir(self.cache_dir):
            file_path = os.path.join(self.cache_dir, file_name)
            if os.path.isfile(file_path) and not file_name.endswith('.tmp'):
                cache_files.append((file_name, file_path))
        
        # Check each file against database
        for file_hash, file_path in cache_files:
            cache_entry = await get_file_cache(file_hash)
            if not cache_entry:
                logger.info(f"Removing orphaned file: {file_path}")
                try:
                    os.remove(file_path)
                except Exception as e:
                    logger.error(f"Error removing orphaned file: {e}")
        
        # Check for tmp directory files older than 24 hours
        tmp_dir = os.path.join(self.cache_dir, 'tmp')
        for file_name in os.listdir(tmp_dir):
            file_path = os.path.join(tmp_dir, file_name)
            if os.path.isfile(file_path):
                file_age = datetime.now().timestamp() - os.path.getmtime(file_path)
                if file_age > 86400:  # 24 hours
                    logger.info(f"Removing old temporary file: {file_path}")
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        logger.error(f"Error removing temporary file: {e}")
    
    async def evict_if_needed(self) -> None:
        """Evict oldest files if cache size exceeds limit with proper locking"""
        async with self._eviction_lock:
            # Get total size of cache
            total_size = await get_total_cache_size()
            
            # Check if we need to evict
            if total_size <= self.cache_limit_bytes:
                return
            
            bytes_to_free = total_size - self.cache_limit_bytes
            bytes_freed = 0
            
            logger.info(f"Cache size ({total_size} bytes) exceeds limit ({self.cache_limit_bytes} bytes)")
            logger.info(f"Need to free {bytes_to_free} bytes")
            
            # Get oldest files first, in batches
            batch_size = 10
            while bytes_freed < bytes_to_free:
                oldest_files = await get_oldest_file_caches(batch_size)
                if not oldest_files:
                    logger.warning("No more files to evict")
                    break
                
                for file_cache in oldest_files:
                    file_path = os.path.join(self.cache_dir, file_cache.hash)
                    try:
                        if os.path.exists(file_path):
                            size = file_cache.bytes
                            os.remove(file_path)
                            await remove_file_cache(file_cache.hash)
                            bytes_freed += size
                            logger.info(f"Evicted file {file_cache.hash}, freed {size} bytes")
                            
                            if bytes_freed >= bytes_to_free:
                                logger.info(f"Successfully freed {bytes_freed} bytes, enough to be under cache limit")
                                break
                        else:
                            # File exists in DB but not on disk, clean up
                            await remove_file_cache(file_cache.hash)
                    except Exception as e:
                        logger.error(f"Error evicting file {file_cache.hash}: {e}")
            
            logger.info(f"Cache eviction complete. Freed {bytes_freed} bytes.")