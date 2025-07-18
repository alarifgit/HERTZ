# hertz/services/audio_source.py
import asyncio
import logging
import hashlib
import os
import tempfile
import json
from typing import Optional, Dict, Any, List
from pathlib import Path

import disnake
import yt_dlp

from ..services.file_cache import FileCacheProvider

logger = logging.getLogger(__name__)

class AudioSourceManager:
    """
    Manages audio source extraction and caching similar to muse's approach
    """
    
    def __init__(self, file_cache: FileCacheProvider):
        self.file_cache = file_cache
        self._extraction_cache = {}  # In-memory cache for extraction info
        
        # YT-DLP options similar to muse's ytdl setup
        self.ytdl_opts = {
            'format': self._get_format_selector(),
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'extract_flat': False,
            'writethumbnail': False,
            'writeinfojson': False,
            'ignoreerrors': False,
            'retries': 3,
            'fragment_retries': 3,
            'socket_timeout': 30,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            },
            # Cookie handling for better reliability
            'cookiefile': None,  # We'll set this per request if needed
            # Geo-bypass
            'geo_bypass': True,
            'geo_bypass_country': 'US',
        }
        
    def _get_format_selector(self) -> str:
        """
        Get format selector similar to muse's logic
        Prefer opus in webm containers, fallback to other audio formats
        """
        return (
            # Prefer opus codec in webm containers (like muse)
            'bestaudio[ext=webm][acodec=opus]/bestaudio[ext=webm]/'
            # Fallback to m4a 
            'bestaudio[ext=m4a]/'
            # Then any webm container
            'bestaudio[container=webm]/'
            # Finally any audio
            'bestaudio/best[height<=720]'
        )
    
    async def get_audio_source(
        self,
        url: str,
        seek_position: Optional[int] = None,
        duration: Optional[int] = None,
        volume: float = 1.0,
        cache_key: Optional[str] = None
    ) -> disnake.AudioSource:
        """
        Get an audio source for the given URL with caching support like muse
        
        Args:
            url: YouTube video URL or ID
            seek_position: Position to start playback (seconds)
            duration: Duration to play (seconds) 
            volume: Volume level (0.0 to 1.0)
            cache_key: Optional cache key for the file
            
        Returns:
            Discord audio source ready for playback
        """
        # Generate cache key if not provided
        if not cache_key:
            cache_key = hashlib.md5(f"{url}_{seek_position or 0}".encode()).hexdigest()
        
        # Check if we have a cached file
        cached_path = await self.file_cache.get_path_for(cache_key)
        
        if cached_path and os.path.exists(cached_path):
            logger.debug(f"[AUDIO] Using cached file for {url}")
            return self._create_audio_source_from_file(
                cached_path, seek_position, duration, volume
            )
        
        # Extract stream info
        stream_info = await self._extract_stream_info(url)
        
        if not stream_info:
            raise ValueError(f"Could not extract stream info for {url}")
        
        # Get the best stream URL
        stream_url = self._get_best_stream_url(stream_info)
        
        if not stream_url:
            raise ValueError(f"Could not get stream URL for {url}")
        
        # Determine if we should cache this
        should_cache = self._should_cache_stream(stream_info, seek_position)
        
        if should_cache:
            # Cache in background and return immediate source
            asyncio.create_task(
                self._cache_stream_async(stream_url, cache_key, stream_info)
            )
        
        # Return immediate audio source
        return self._create_audio_source_from_url(
            stream_url, seek_position, duration, volume
        )
    
    async def _extract_stream_info(self, url: str) -> Optional[Dict[str, Any]]:
        """Extract stream information using yt-dlp like muse"""
        # Check in-memory cache first
        if url in self._extraction_cache:
            cache_time, info = self._extraction_cache[url]
            # Cache for 10 minutes
            if asyncio.get_event_loop().time() - cache_time < 600:
                return info
        
        try:
            loop = asyncio.get_event_loop()
            
            # Ensure URL is a full YouTube URL
            if len(url) == 11:  # Just video ID
                url = f"https://www.youtube.com/watch?v={url}"
            
            def extract():
                with yt_dlp.YoutubeDL(self.ytdl_opts) as ydl:
                    return ydl.extract_info(url, download=False)
            
            # Run extraction in thread pool
            info = await loop.run_in_executor(None, extract)
            
            if info:
                # Cache the result
                self._extraction_cache[url] = (asyncio.get_event_loop().time(), info)
                
                # Limit cache size
                if len(self._extraction_cache) > 100:
                    # Remove oldest entries
                    oldest_keys = sorted(
                        self._extraction_cache.keys(),
                        key=lambda k: self._extraction_cache[k][0]
                    )[:50]
                    for key in oldest_keys:
                        del self._extraction_cache[key]
                
                return info
            
        except Exception as e:
            logger.error(f"[AUDIO] Error extracting stream info for {url}: {e}")
            return None
        
        return None
    
    def _get_best_stream_url(self, stream_info: Dict[str, Any]) -> Optional[str]:
        """Get the best stream URL from extraction info like muse"""
        # Try direct URL first
        url = stream_info.get('url')
        if url:
            return url
        
        # Look in formats
        formats = stream_info.get('formats', [])
        if not formats:
            return None
        
        # Filter for audio-only formats like muse
        audio_formats = []
        for fmt in formats:
            if (fmt.get('acodec') != 'none' and 
                fmt.get('vcodec') in ('none', None)):
                audio_formats.append(fmt)
        
        # If no audio-only, get formats with audio
        if not audio_formats:
            audio_formats = [f for f in formats if f.get('acodec') != 'none']
        
        if not audio_formats:
            return None
        
        # Prefer opus in webm like muse
        opus_webm = [f for f in audio_formats 
                     if f.get('acodec') == 'opus' and f.get('ext') == 'webm']
        if opus_webm:
            return opus_webm[0]['url']
        
        # Then any webm
        webm_formats = [f for f in audio_formats if f.get('ext') == 'webm']
        if webm_formats:
            return webm_formats[0]['url']
        
        # Sort by audio bitrate and return best
        audio_formats.sort(key=lambda x: x.get('abr', 0), reverse=True)
        return audio_formats[0]['url']
    
    def _should_cache_stream(
        self, 
        stream_info: Dict[str, Any], 
        seek_position: Optional[int]
    ) -> bool:
        """Determine if we should cache this stream like muse"""
        # Don't cache if seeking (partial file)
        if seek_position:
            return False
        
        # Don't cache live streams
        if stream_info.get('is_live'):
            return False
        
        # Don't cache very long videos (> 30 minutes like muse)
        duration = stream_info.get('duration', 0)
        if duration > 30 * 60:
            return False
        
        # Don't cache very short videos (< 10 seconds)
        if duration < 10:
            return False
        
        return True
    
    async def _cache_stream_async(
        self, 
        stream_url: str, 
        cache_key: str, 
        stream_info: Dict[str, Any]
    ) -> None:
        """Cache stream to file system in background like muse"""
        try:
            cache_dir = self.file_cache.cache_dir
            tmp_dir = os.path.join(cache_dir, 'tmp')
            os.makedirs(tmp_dir, exist_ok=True)
            
            tmp_path = os.path.join(tmp_dir, f"{cache_key}.tmp")
            final_path = os.path.join(cache_dir, cache_key)
            
            # Don't re-cache if already exists
            if os.path.exists(final_path):
                return
            
            logger.debug(f"[CACHE] Downloading stream to cache: {cache_key}")
            
            # Use ffmpeg to download and convert to opus like muse
            cmd = [
                'ffmpeg', '-y',
                '-i', stream_url,
                '-c:a', 'libopus',
                '-b:a', '128k',
                '-vn',  # No video
                '-f', 'opus',
                tmp_path
            ]
            
            # Add loudness normalization if we have the info
            loudness_db = stream_info.get('loudness')
            if loudness_db:
                # Apply loudness correction like muse
                cmd.insert(-2, '-filter:a')
                cmd.insert(-2, f'volume={-loudness_db}dB')
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE
            )
            
            _, stderr = await asyncio.wait_for(
                process.communicate(), 
                timeout=300  # 5 minute timeout
            )
            
            if process.returncode == 0 and os.path.exists(tmp_path):
                # Move to final location
                os.rename(tmp_path, final_path)
                
                # Register in cache
                file_size = os.path.getsize(final_path)
                await self.file_cache.cache_file(cache_key, final_path)
                
                logger.info(f"[CACHE] Successfully cached stream: {cache_key} ({file_size} bytes)")
            else:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.warning(f"[CACHE] Failed to cache stream {cache_key}: {error_msg}")
                
        except asyncio.TimeoutError:
            logger.warning(f"[CACHE] Cache download timeout for {cache_key}")
        except Exception as e:
            logger.error(f"[CACHE] Error caching stream {cache_key}: {e}")
        finally:
            # Clean up tmp file
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
    
    def _create_audio_source_from_file(
        self,
        file_path: str,
        seek_position: Optional[int] = None,
        duration: Optional[int] = None,
        volume: float = 1.0
    ) -> disnake.AudioSource:
        """Create audio source from cached file like muse"""
        ffmpeg_options = {
            'before_options': '',
            'options': '-vn'
        }
        
        if seek_position:
            ffmpeg_options['before_options'] += f' -ss {seek_position}'
        
        if duration:
            ffmpeg_options['options'] += f' -t {duration}'
        
        # Add volume filter
        if volume != 1.0:
            ffmpeg_options['options'] += f' -filter:a "volume={volume}"'
        
        source = disnake.FFmpegPCMAudio(file_path, **ffmpeg_options)
        return disnake.PCMVolumeTransformer(source, volume=volume)
    
    def _create_audio_source_from_url(
        self,
        stream_url: str,
        seek_position: Optional[int] = None,
        duration: Optional[int] = None,
        volume: float = 1.0
    ) -> disnake.AudioSource:
        """Create audio source from stream URL like muse"""
        ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn'
        }
        
        if seek_position:
            ffmpeg_options['before_options'] += f' -ss {seek_position}'
        
        if duration:
            ffmpeg_options['options'] += f' -t {duration}'
        
        # Add volume filter and audio normalization like muse
        audio_filters = []
        if volume != 1.0:
            audio_filters.append(f'volume={volume}')
        
        # Add some audio processing like muse
        audio_filters.append('loudnorm=I=-16:LRA=11:TP=-1.5')
        
        if audio_filters:
            ffmpeg_options['options'] += f' -filter:a "{",".join(audio_filters)}"'
        
        source = disnake.FFmpegPCMAudio(stream_url, **ffmpeg_options)
        return disnake.PCMVolumeTransformer(source, volume=volume)
    
    async def get_stream_metadata(self, url: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a stream without creating audio source"""
        info = await self._extract_stream_info(url)
        if not info:
            return None
        
        return {
            'title': info.get('title', 'Unknown'),
            'duration': info.get('duration', 0),
            'uploader': info.get('uploader', 'Unknown'),
            'view_count': info.get('view_count', 0),
            'like_count': info.get('like_count', 0),
            'is_live': info.get('is_live', False),
            'thumbnail': info.get('thumbnail'),
            'description': info.get('description', ''),
            'upload_date': info.get('upload_date'),
            'formats_available': len(info.get('formats', [])),
        }
    
    def clear_extraction_cache(self):
        """Clear the in-memory extraction cache"""
        self._extraction_cache.clear()
        logger.info("[CACHE] Cleared extraction cache")
    
    async def preload_stream(self, url: str) -> bool:
        """Preload stream info for faster playback"""
        try:
            info = await self._extract_stream_info(url)
            return info is not None
        except Exception as e:
            logger.error(f"[PRELOAD] Error preloading {url}: {e}")
            return False
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return {
            'extraction_cache_size': len(self._extraction_cache),
            'extraction_cache_keys': list(self._extraction_cache.keys())[:10],  # First 10 for debugging
        }

# Factory function for easy creation
def create_audio_source_manager(file_cache: FileCacheProvider) -> AudioSourceManager:
    """Create an AudioSourceManager instance"""
    return AudioSourceManager(file_cache)