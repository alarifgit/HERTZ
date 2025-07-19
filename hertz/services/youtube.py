# hertz/services/youtube.py
import asyncio
import re
import logging
import json
from typing import List, Dict, Any, Optional, Tuple, Union

import aiohttp

from ..config import Config
from ..services.key_value_cache import KeyValueCache, ONE_HOUR_IN_SECONDS, TEN_MINUTES_IN_SECONDS, ONE_MINUTE_IN_SECONDS
from ..services.api_queue import AsyncRequestQueue

logger = logging.getLogger(__name__)

# Initialize cache
key_value_cache = KeyValueCache()
# Initialize API request queue
request_queue = AsyncRequestQueue(concurrency=4)

async def search_youtube(
    query: str,
    should_split_chapters: bool,
    api_key: str
) -> List[Dict[str, Any]]:
    """
    Search YouTube for a query string
    
    Args:
        query: Search string
        should_split_chapters: Whether to split videos into chapters
        api_key: YouTube API key
        
    Returns:
        List of song metadata dictionaries
    """
    # Try to get from cache
    cache_key = f"youtube_search:{query}"
    cached = await key_value_cache.get(cache_key)
    if cached:
        logger.debug(f"YouTube search cache hit: {query}")
        return json.loads(cached)
    
    # Use the queue to limit API concurrency
    return await request_queue.add(
        _search_youtube_impl, 
        query, 
        should_split_chapters, 
        api_key,
        cache_key
    )

async def _search_youtube_impl(
    query: str, 
    should_split_chapters: bool, 
    api_key: str,
    cache_key: str
) -> List[Dict[str, Any]]:
    """Implementation of YouTube search with API call"""
    try:
        # Search for videos
        async with aiohttp.ClientSession() as session:
            params = {
                'part': 'snippet',
                'maxResults': 1,
                'q': query,
                'type': 'video',
                'key': api_key
            }
            
            async with session.get(
                'https://www.googleapis.com/youtube/v3/search',
                params=params
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"YouTube API error: {error_text}")
                    raise ValueError(f"YouTube API error: {response.status}")
                
                search_data = await response.json()
            
            # No results
            if not search_data.get('items'):
                return []
            
            # Get video IDs to fetch detailed info
            video_id = search_data['items'][0]['id']['videoId']
            
            # Get detailed video info
            video = await get_video_details(video_id, api_key)
            
            if not video:
                return []
            
            # Process chapters if needed
            if should_split_chapters:
                videos = await process_video_chapters(video, api_key)
                if videos:
                    # Cache the result
                    await key_value_cache.set(
                        cache_key,
                        json.dumps(videos),
                        ONE_HOUR_IN_SECONDS
                    )
                    return videos
            
            # Process as single video
            result = [format_video_metadata(video)]
            
            # Cache the result
            await key_value_cache.set(
                cache_key,
                json.dumps(result),
                ONE_HOUR_IN_SECONDS
            )
            
            return result
            
    except Exception as e:
        logger.error(f"Error searching YouTube: {str(e)}")
        return []

async def get_youtube_video(
    url: str,
    should_split_chapters: bool,
    api_key: str
) -> List[Dict[str, Any]]:
    """
    Get metadata for a YouTube video URL
    
    Args:
        url: YouTube URL
        should_split_chapters: Whether to split video into chapters
        api_key: YouTube API key
        
    Returns:
        List of song metadata dictionaries
    """
    # Extract video ID from URL
    video_id = extract_youtube_id(url)
    if not video_id:
        return []
    
    # Try to get from cache
    cache_key = f"youtube_video:{video_id}"
    cached = await key_value_cache.get(cache_key)
    if cached:
        logger.debug(f"YouTube video cache hit: {video_id}")
        return json.loads(cached)
    
    # Use the queue to limit API concurrency
    return await request_queue.add(
        _get_youtube_video_impl,
        video_id,
        should_split_chapters,
        api_key,
        cache_key
    )

async def _get_youtube_video_impl(
    video_id: str,
    should_split_chapters: bool,
    api_key: str,
    cache_key: str
) -> List[Dict[str, Any]]:
    """Implementation of video metadata retrieval"""
    try:
        # Get video details
        video = await get_video_details(video_id, api_key)
        
        if not video:
            return []
        
        # Process chapters if needed
        if should_split_chapters:
            videos = await process_video_chapters(video, api_key)
            if videos:
                # Cache the result
                await key_value_cache.set(
                    cache_key,
                    json.dumps(videos),
                    ONE_HOUR_IN_SECONDS
                )
                return videos
        
        # Process as single video
        result = [format_video_metadata(video)]
        
        # Cache the result
        await key_value_cache.set(
            cache_key,
            json.dumps(result),
            ONE_HOUR_IN_SECONDS
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting YouTube video: {str(e)}")
        return []

async def get_youtube_playlist(
    playlist_id: str,
    should_split_chapters: bool,
    api_key: str
) -> List[Dict[str, Any]]:
    """
    Get metadata for a YouTube playlist with batched processing
    
    Args:
        playlist_id: YouTube playlist ID
        should_split_chapters: Whether to split videos into chapters
        api_key: YouTube API key
        
    Returns:
        List of song metadata dictionaries
    """
    # Try to get from cache
    cache_key = f"youtube_playlist:{playlist_id}"
    cached = await key_value_cache.get(cache_key)
    if cached:
        logger.debug(f"YouTube playlist cache hit: {playlist_id}")
        return json.loads(cached)
    
    # Use the queue to limit API concurrency
    return await request_queue.add(
        _get_youtube_playlist_impl,
        playlist_id,
        should_split_chapters,
        api_key,
        cache_key
    )

async def _get_youtube_playlist_impl(
    playlist_id: str,
    should_split_chapters: bool,
    api_key: str,
    cache_key: str
) -> List[Dict[str, Any]]:
    """Implementation of playlist retrieval"""
    try:
        # Get playlist details first
        async with aiohttp.ClientSession() as session:
            params = {
                'part': 'snippet',
                'id': playlist_id,
                'key': api_key
            }
            
            async with session.get(
                'https://www.googleapis.com/youtube/v3/playlists',
                params=params
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"YouTube API error: {error_text}")
                    raise ValueError(f"YouTube API error: {response.status}")
                
                playlist_data = await response.json()
            
            if not playlist_data.get('items'):
                return []
            
            playlist = playlist_data['items'][0]
            playlist_title = playlist['snippet']['title']
            
            # Get playlist items with pagination
            all_video_ids = []
            next_page_token = None
            
            while True:
                params = {
                    'part': 'snippet,contentDetails',
                    'maxResults': 50,  # Max allowed by API
                    'playlistId': playlist_id,
                    'key': api_key
                }
                
                if next_page_token:
                    params['pageToken'] = next_page_token
                
                # Get items for this page
                async with session.get(
                    'https://www.googleapis.com/youtube/v3/playlistItems',
                    params=params
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"YouTube API error: {error_text}")
                        break
                    
                    items_data = await response.json()
                
                # Extract video IDs from this page
                for item in items_data.get('items', []):
                    video_id = item.get('contentDetails', {}).get('videoId')
                    if video_id:
                        all_video_ids.append(video_id)
                
                # Check if there are more pages
                next_page_token = items_data.get('nextPageToken')
                if not next_page_token:
                    break
            
            # Create playlist object
            playlist_obj = {
                'title': playlist_title,
                'source': playlist_id
            }
            
            # Process videos in batches of 50 (YouTube API limit)
            results = []
            
            # Process in batches to avoid API quota issues
            for i in range(0, len(all_video_ids), 50):
                batch = all_video_ids[i:i+50]
                batch_videos = await get_videos_details(batch, api_key)
                
                for video in batch_videos:
                    if video:
                        # Process chapters if needed
                        if should_split_chapters:
                            chapters = await process_video_chapters(
                                video, 
                                api_key, 
                                playlist_obj
                            )
                            if chapters:
                                results.extend(chapters)
                                continue
                        
                        # Add as single video
                        metadata = format_video_metadata(video, playlist_obj)
                        results.append(metadata)
            
            # Cache the result - using short TTL as playlists change frequently
            await key_value_cache.set(
                cache_key,
                json.dumps(results),
                ONE_HOUR_IN_SECONDS
            )
            
            return results
            
    except Exception as e:
        logger.error(f"Error getting YouTube playlist: {str(e)}")
        return []

async def get_video_details(video_id: str, api_key: str) -> Optional[Dict[str, Any]]:
    """Get detailed information about a YouTube video"""
    # Try to get from cache with 1 hour TTL
    cache_key = f"youtube_video_details:{video_id}"
    cached = await key_value_cache.get(cache_key)
    if cached:
        return json.loads(cached)
    
    async with aiohttp.ClientSession() as session:
        params = {
            'part': 'snippet,contentDetails,statistics',
            'id': video_id,
            'key': api_key
        }
        
        async with session.get(
            'https://www.googleapis.com/youtube/v3/videos',
            params=params
        ) as response:
            if response.status != 200:
                return None
            
            data = await response.json()
        
        if not data.get('items'):
            return None
        
        result = data['items'][0]
        
        # Cache the video details
        await key_value_cache.set(
            cache_key,
            json.dumps(result),
            ONE_HOUR_IN_SECONDS
        )
        
        return result

async def get_videos_details(video_ids: List[str], api_key: str) -> List[Dict[str, Any]]:
    """Get detailed information about multiple YouTube videos"""
    if not video_ids:
        return []
    
    # Batch the video IDs to avoid URL length limitations
    batch_size = 50  # YouTube API maximum
    batches = [video_ids[i:i+batch_size] for i in range(0, len(video_ids), batch_size)]
    
    results = []
    for batch in batches:
        # Create a cache key for this batch
        batch_key = f"youtube_videos_batch:{','.join(batch)}"
        cached = await key_value_cache.get(batch_key)
        
        if cached:
            results.extend(json.loads(cached))
            continue
        
        # Need to fetch this batch
        async with aiohttp.ClientSession() as session:
            params = {
                'part': 'snippet,contentDetails,statistics',
                'id': ','.join(batch),
                'key': api_key
            }
            
            async with session.get(
                'https://www.googleapis.com/youtube/v3/videos',
                params=params
            ) as response:
                if response.status != 200:
                    continue
                
                data = await response.json()
            
            batch_results = data.get('items', [])
            results.extend(batch_results)
            
            # Cache this batch
            await key_value_cache.set(
                batch_key,
                json.dumps(batch_results),
                ONE_HOUR_IN_SECONDS
            )
    
    return results

async def process_video_chapters(
    video: Dict[str, Any],
    api_key: str,
    playlist: Optional[Dict[str, str]] = None
) -> Optional[List[Dict[str, Any]]]:
    """
    Process a video into chapters if available
    
    Args:
        video: Video data
        api_key: YouTube API key
        playlist: Optional playlist data
        
    Returns:
        List of chapter metadata or None if no chapters
    """
    # Get video description
    description = video['snippet']['description']
    
    # Try to extract chapters from description
    chapters = parse_chapters_from_description(
        description, 
        parse_duration(video['contentDetails']['duration'])
    )
    
    if not chapters:
        return None
    
    # Format each chapter as a song
    results = []
    
    for chapter_title, time_info in chapters:
        # Create a copy of the video for this chapter
        chapter = format_video_metadata(video, playlist)
        
        # Update with chapter info
        chapter['title'] = f"{chapter_title} ({chapter['title']})"
        chapter['offset'] = time_info['offset']
        chapter['length'] = time_info['length']
        
        results.append(chapter)
    
    return results

def format_video_metadata(
    video: Dict[str, Any],
    playlist: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Format video data as song metadata"""
    video_id = video['id']
    title = video['snippet']['title']
    channel = video['snippet']['channelTitle']
    
    # Check if video is live
    is_live = (
        video['snippet'].get('liveBroadcastContent') == 'live' or
        video['snippet'].get('liveBroadcastContent') == 'upcoming'
    )
    
    # Get duration
    duration = 0 if is_live else parse_duration(video['contentDetails']['duration'])
    
    # Get thumbnail
    thumbnail_url = None
    thumbnails = video['snippet'].get('thumbnails', {})
    if 'medium' in thumbnails:
        thumbnail_url = thumbnails['medium']['url']
    elif 'default' in thumbnails:
        thumbnail_url = thumbnails['default']['url']
    
    return {
        'title': title,
        'artist': channel,
        'url': video_id,
        'length': duration,
        'offset': 0,
        'playlist': playlist,
        'is_live': is_live,
        'thumbnail_url': thumbnail_url,
        'source': 0  # MediaSource.YOUTUBE
    }

def parse_chapters_from_description(description: str, video_duration: int) -> List[Tuple[str, Dict[str, int]]]:
    """
    Parse chapter timestamps from a video description
    
    Returns:
        List of (chapter_title, {offset, length}) tuples
    """
    if not description:
        return []
    
    # Look for chapter markers in the description
    lines = description.split('\n')
    timestamps = []
    found_first_timestamp = False
    
    for line in lines:
        # Look for timestamp pattern (e.g., 0:00, 1:30, 01:45, 1:30:45)
        match = re.search(r'(\d+:)?(\d+):(\d+)', line)
        if not match:
            continue
        
        # Parse the timestamp
        timestamp_str = match.group(0)
        time_parts = timestamp_str.split(':')
        
        if len(time_parts) == 2:
            minutes, seconds = int(time_parts[0]), int(time_parts[1])
            timestamp = minutes * 60 + seconds
        else:
            hours, minutes, seconds = int(time_parts[0]), int(time_parts[1]), int(time_parts[2])
            timestamp = hours * 3600 + minutes * 60 + seconds
        
        # Check if this might be the first chapter
        if not found_first_timestamp and timestamp <= 1:
            found_first_timestamp = True
        elif not found_first_timestamp:
            continue
        
        # Get the chapter title (text after timestamp)
        title_start = match.end()
        chapter_title = line[title_start:].strip()
        if not chapter_title:
            chapter_title = f"Chapter {len(timestamps) + 1}"
        
        timestamps.append((timestamp, chapter_title))
    
    # Ensure timestamps are in order
    timestamps.sort(key=lambda x: x[0])
    
    # Must have at least 2 timestamps for chapters
    if len(timestamps) < 2:
        return []
    
    # First timestamp should be near the beginning
    if timestamps[0][0] > 10:  # If first timestamp is more than 10 seconds in
        return []
    
    # Convert to chapter format
    chapters = []
    
    for i, (timestamp, title) in enumerate(timestamps):
        # Chapter length is until next timestamp or end of video
        if i < len(timestamps) - 1:
            length = timestamps[i+1][0] - timestamp
        else:
            length = video_duration - timestamp
        
        chapters.append((
            title, 
            {'offset': timestamp, 'length': length}
        ))
    
    return chapters

def parse_duration(duration_str: str) -> int:
    """
    Parse ISO 8601 duration format used by YouTube API
    
    Example: 'PT1H30M15S' -> 5415 seconds
    """
    if not duration_str:
        return 0
    
    # Remove PT prefix
    duration_str = duration_str.replace('PT', '')
    
    hours = 0
    minutes = 0
    seconds = 0
    
    # Extract hours
    h_match = re.search(r'(\d+)H', duration_str)
    if h_match:
        hours = int(h_match.group(1))
    
    # Extract minutes
    m_match = re.search(r'(\d+)M', duration_str)
    if m_match:
        minutes = int(m_match.group(1))
    
    # Extract seconds
    s_match = re.search(r'(\d+)S', duration_str)
    if s_match:
        seconds = int(s_match.group(1))
    
    return hours * 3600 + minutes * 60 + seconds

def extract_youtube_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from a URL"""
    # Standard YouTube URLs
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com/embed/([a-zA-Z0-9_-]{11})',
        r'youtube\.com/v/([a-zA-Z0-9_-]{11})',
        r'youtube\.com/\?v=([a-zA-Z0-9_-]{11})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    # Check if the URL is just the ID
    if re.match(r'^[a-zA-Z0-9_-]{11}$', url):
        return url
    
    return None

async def get_youtube_suggestions(query: str) -> List[str]:
    """Get search suggestions from YouTube for a query"""
    if not query or len(query.strip()) < 2:
        return []
            
    try:
        # Try to get from cache first
        cache_key = f"youtube_suggestions:{query}"
        cached = await key_value_cache.get(cache_key)
        if cached:
            return json.loads(cached)
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://suggestqueries.google.com/complete/search",
                params={
                    "client": "firefox",
                    "ds": "yt",
                    "q": query
                },
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
            ) as response:
                if response.status != 200:
                    return []
                
                # Get response as text first
                text = await response.text()
                
                # Try to parse response as JSON
                try:
                    # Remove JavaScript callback if present
                    if text.startswith("window.google.ac.h("):
                        text = text[text.index("(")+1:text.rindex(")")]
                    
                    data = json.loads(text)
                    suggestions = []
                    if isinstance(data, list) and len(data) > 1:
                        suggestions = data[1]  # Second element contains suggestions array
                    
                    # Cache the suggestions with 10 minute TTL
                    await key_value_cache.set(
                        cache_key,
                        json.dumps(suggestions),
                        TEN_MINUTES_IN_SECONDS
                    )
                    
                    return suggestions
                except json.JSONDecodeError:
                    # Fallback: Try regex extraction
                    import re
                    suggestions = []
                    matches = re.findall(r'"([^"]+)"', text)
                    if matches and len(matches) > 1:
                        suggestions = matches[1:]  # Skip the first match (query)
                    
                    # Cache the suggestions with 10 minute TTL
                    await key_value_cache.set(
                        cache_key,
                        json.dumps(suggestions),
                        TEN_MINUTES_IN_SECONDS
                    )
                    
                    return suggestions
    except Exception as e:
        logger.error(f"Error getting YouTube suggestions: {e}")
        return []

async def test_youtube_api(api_key: str):
    """Test connection to YouTube API"""
    async with aiohttp.ClientSession() as session:
        params = {
            'part': 'snippet',
            'q': 'test',
            'maxResults': 1,
            'key': api_key
        }
        
        async with session.get(
            'https://www.googleapis.com/youtube/v3/search',
            params=params
        ) as response:
            if response.status != 200:
                text = await response.text()
                raise ValueError(f"YouTube API test failed: {response.status} - {text}")
            
            return True