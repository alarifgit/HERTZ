# hertz/services/key_value_cache.py
import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, TypeVar, Callable, List

from ..db.client import get_key_value, set_key_value

logger = logging.getLogger(__name__)

T = TypeVar('T')

# Define different cache expiry times
ONE_HOUR_IN_SECONDS = 60 * 60
TEN_MINUTES_IN_SECONDS = 10 * 60
ONE_MINUTE_IN_SECONDS = 60

class KeyValueCache:
    """
    Key-value cache service for storing API responses
    """
    
    def __init__(self):
        self._cache_lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[str]:
        """
        Get a value from the cache
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found or expired
        """
        try:
            return await get_key_value(key)
        except Exception as e:
            logger.error(f"Error getting from cache: {str(e)}")
            return None
    
    async def set(self, key: str, value: str, ttl: int) -> None:
        """
        Set a value in the cache
        
        Args:
            key: Cache key
            value: Value to store
            ttl: Time to live in seconds
        """
        try:
            async with self._cache_lock:
                await set_key_value(key, value, ttl)
        except Exception as e:
            logger.error(f"Error setting cache: {str(e)}")
    
    async def wrap(
        self,
        func: Callable[..., T],
        *args: Any,
        key: Optional[str] = None,
        ttl: int = ONE_HOUR_IN_SECONDS,
        **kwargs: Any
    ) -> T:
        """
        Wrap a function call with caching
        
        Args:
            func: Function to call if cache miss
            *args: Arguments for the function
            key: Optional custom cache key (defaults to function name + args hash)
            ttl: Time to live in seconds
            **kwargs: Keyword arguments for the function
            
        Returns:
            The function result (from cache or fresh)
        """
        # Generate cache key if not provided
        if not key:
            args_str = json.dumps(args, sort_keys=True)
            kwargs_str = json.dumps(kwargs, sort_keys=True)
            key = f"{func.__name__}:{args_str}:{kwargs_str}"
        
        # Try to get from cache
        cached = await self.get(key)
        if cached is not None:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                # If not JSON, return as is
                return cached
        
        # Cache miss, call function
        result = await func(*args, **kwargs)
        
        # Store in cache
        try:
            await self.set(key, json.dumps(result), ttl)
        except (TypeError, json.JSONDecodeError):
            # If not JSON serializable, don't cache
            logger.warning(f"Result for {key} is not JSON serializable, not caching")
        
        return result