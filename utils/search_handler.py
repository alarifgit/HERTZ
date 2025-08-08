"""
Advanced Search Handler with caching and multiple sources
Minimizes YouTube API usage like Muse does
"""
import asyncio
import aiohttp
import re
import json
import logging
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone, timedelta
import hashlib
import os

logger = logging.getLogger('hertz.search')

class SearchCache:
    """In-memory cache for search results"""
    
    def __init__(self, ttl_seconds: int = 3600):
        self.cache = {}
        self.ttl = ttl_seconds
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached value if not expired"""
        if key in self.cache:
            data, timestamp = self.cache[key]
            if datetime.now() - timestamp < timedelta(seconds=self.ttl):
                return data
            else:
                del self.cache[key]
        return None
    
    def set(self, key: str, value: Any):
        """Store value in cache"""
        self.cache[key] = (value, datetime.now())
    
    def clear_expired(self):
        """Remove expired entries"""
        now = datetime.now()
        expired = [k for k, (_, t) in self.cache.items() 
                  if now - t >= timedelta(seconds=self.ttl)]
        for key in expired:
            del self.cache[key]

class YouTubeSearchHandler:
    """
    Handle YouTube searches without using official API
    Similar to how Muse minimizes API usage
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.session = None
        self.cache = SearchCache(ttl_seconds=7200)  # 2 hour cache
        
        # Headers to appear more like a browser
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        }
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession(headers=self.headers)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    async def search_youtube_scrape(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Search YouTube by scraping (no API needed)
        This is how Muse avoids API rate limits
        """
        # Check cache first
        cache_key = f"scrape:{query}:{limit}"
        cached = self.cache.get(cache_key)
        if cached:
            logger.debug(f"Cache hit for query: {query}")
            return cached
        
        results = []
        
        try:
            # Use invidious instances as fallback (privacy-friendly YouTube proxy)
            invidious_instances = [
                'https://invidious.namazso.eu',
                'https://inv.riverside.rocks',
                'https://invidious.kavin.rocks',
                'https://invidious.osi.kr'
            ]
            
            for instance in invidious_instances:
                try:
                    url = f"{instance}/api/v1/search"
                    params = {
                        'q': query,
                        'type': 'video',
                        'region': 'US',
                        'sort_by': 'relevance'
                    }
                    
                    async with self.session.get(url, params=params, timeout=5) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            for item in data[:limit]:
                                if item.get('type') == 'video':
                                    results.append({
                                        'title': item.get('title', 'Unknown'),
                                        'url': f"https://youtube.com/watch?v={item.get('videoId')}",
                                        'duration': item.get('lengthSeconds', 0),
                                        'channel': item.get('author', 'Unknown'),
                                        'thumbnail': item.get('videoThumbnails', [{}])[0].get('url'),
                                        'views': item.get('viewCount', 0)
                                    })
                            
                            if results:
                                break
                except Exception as e:
                    logger.debug(f"Invidious instance {instance} failed: {e}")
                    continue
            
            # Cache results
            if results:
                self.cache.set(cache_key, results)
                
        except Exception as e:
            logger.error(f"YouTube scrape search failed: {e}")
        
        return results
    
    async def search_youtube_api(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Search using official YouTube API (when available)
        """
        if not self.api_key:
            return []
        
        # Check cache
        cache_key = f"api:{query}:{limit}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        
        results = []
        
        try:
            url = 'https://www.googleapis.com/youtube/v3/search'
            params = {
                'part': 'snippet',
                'q': query,
                'type': 'video',
                'maxResults': limit,
                'key': self.api_key
            }
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    video_ids = [item['id']['videoId'] for item in data.get('items', [])]
                    
                    if video_ids:
                        # Get video details for duration
                        details_url = 'https://www.googleapis.com/youtube/v3/videos'
                        details_params = {
                            'part': 'contentDetails,statistics',
                            'id': ','.join(video_ids),
                            'key': self.api_key
                        }
                        
                        async with self.session.get(details_url, params=details_params) as detail_response:
                            if detail_response.status == 200:
                                details = await detail_response.json()
                                detail_map = {item['id']: item for item in details.get('items', [])}
                        
                        for item in data.get('items', []):
                            video_id = item['id']['videoId']
                            snippet = item['snippet']
                            details = detail_map.get(video_id, {})
                            
                            # Parse duration
                            duration_str = details.get('contentDetails', {}).get('duration', 'PT0S')
                            duration = self._parse_duration(duration_str)
                            
                            results.append({
                                'title': snippet.get('title', 'Unknown'),
                                'url': f"https://youtube.com/watch?v={video_id}",
                                'duration': duration,
                                'channel': snippet.get('channelTitle', 'Unknown'),
                                'thumbnail': snippet.get('thumbnails', {}).get('high', {}).get('url'),
                                'views': int(details.get('statistics', {}).get('viewCount', 0))
                            })
            
            # Cache results
            if results:
                self.cache.set(cache_key, results)
                
        except Exception as e:
            logger.error(f"YouTube API search failed: {e}")
        
        return results
    
    async def search(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Search YouTube using best available method
        """
        # Try API first if available
        if self.api_key:
            results = await self.search_youtube_api(query, limit)
            if results:
                return results
        
        # Fallback to scraping
        return await self.search_youtube_scrape(query, limit)
    
    def _parse_duration(self, duration_str: str) -> int:
        """Parse ISO 8601 duration to seconds"""
        import re
        
        pattern = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')
        match = pattern.match(duration_str)
        
        if not match:
            return 0
        
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        
        return hours * 3600 + minutes * 60 + seconds

class SearchAggregator:
    """
    Aggregate searches from multiple sources
    Provides autocomplete suggestions like Muse
    """
    
    def __init__(self, youtube_api_key: Optional[str] = None):
        self.youtube = YouTubeSearchHandler(youtube_api_key)
        self.suggestion_cache = SearchCache(ttl_seconds=3600)
    
    async def __aenter__(self):
        await self.youtube.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.youtube.__aexit__(exc_type, exc_val, exc_tb)
    
    async def get_suggestions(self, query: str) -> List[str]:
        """
        Get search suggestions for autocomplete
        Uses Google's suggestion API like Muse does
        """
        if len(query) < 2:
            return []
        
        # Check cache
        cache_key = f"suggest:{query}"
        cached = self.suggestion_cache.get(cache_key)
        if cached:
            return cached
        
        suggestions = []
        
        try:
            # Use Google's suggestion API (no key needed)
            url = 'https://suggestqueries.google.com/complete/search'
            params = {
                'client': 'firefox',  # Returns JSON
                'q': query,
                'ds': 'yt'  # YouTube suggestions
            }
            
            async with self.youtube.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if len(data) > 1:
                        suggestions = data[1][:10]  # Get top 10 suggestions
            
            # Cache suggestions
            if suggestions:
                self.suggestion_cache.set(cache_key, suggestions)
                
        except Exception as e:
            logger.debug(f"Failed to get suggestions: {e}")
        
        return suggestions
    
    async def search_with_fallback(self, query: str, limit: int = 5) -> List[Dict]:
        """
        Search with multiple fallback options
        """
        # Direct YouTube URL
        if 'youtube.com/watch' in query or 'youtu.be/' in query:
            return [{'url': query, 'title': 'Direct URL', 'duration': 0}]
        
        # Search YouTube
        results = await self.youtube.search(query, limit)
        
        return results

# Global search handler instance
search_handler = None

async def initialize_search_handler(youtube_api_key: Optional[str] = None):
    """Initialize the global search handler"""
    global search_handler
    search_handler = SearchAggregator(youtube_api_key)
    await search_handler.__aenter__()
    logger.info("🔍 Search handler initialized")

async def cleanup_search_handler():
    """Clean up the global search handler"""
    global search_handler
    if search_handler:
        await search_handler.__aexit__(None, None, None)
        logger.info("🔍 Search handler cleaned up")