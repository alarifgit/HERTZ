# hertz/services/youtube.py
import asyncio
import re
import logging
import json
import time
from typing import List, Dict, Any, Optional, Tuple, Union
from datetime import timedelta

import aiohttp

from ..config import Config
from ..services.key_value_cache import KeyValueCache, ONE_HOUR_IN_SECONDS, TEN_MINUTES_IN_SECONDS, ONE_MINUTE_IN_SECONDS
from ..services.api_queue import AsyncRequestQueue

logger = logging.getLogger(__name__)

# Initialize cache
key_value_cache = KeyValueCache()
# Initialize API request queue with conservative concurrency like muse
request_queue = AsyncRequestQueue(concurrency=4)

async def search_youtube(
    query: str,
    should_split_chapters: bool,
    api_key: str
) -> List[Dict[str, Any]]:
    """
    Search YouTube for a query string - improved to match muse's search behavior
    
    Args:
        query: Search string
        should_split_chapters: Whether to split videos into chapters
        api_key: YouTube API key
        
    Returns:
        List of song metadata dictionaries
    """
    # Try to get from cache with reasonable TTL like muse
    cache_key = f"youtube_search:{query}"
    cached = await key_value_cache.get(cache_key)
    if cached:
        logger.debug(f"YouTube search cache hit: {query}")
        return json.loads(cached)
    
    # Use the queue to limit API concurrency like muse
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
    """Implementation of YouTube search with API call and retry logic like muse"""
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            # Search for videos with improved error handling like muse
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30, connect=10),
                connector=aiohttp.TCPConnector(limit=10, limit_per_host=5)
            ) as session:
                params = {
                    'part': 'snippet',
                    'maxResults': 1,  # Only get the first result like muse
                    'q': query,
                    'type': 'video',
                    'key': api_key,
                    'videoCategoryId': '10',  # Music category
                    'order': 'relevance'  # Most relevant first
                }
                
                async with session.get(
                    'https://www.googleapis.com/youtube/v3/search',
                    params=params
                ) as response:
                    if response.status == 429:  # Rate limit
                        retry_after = int(response.headers.get('Retry-After', '60'))
                        logger.warning(f"YouTube API rate limit hit, waiting {retry_after}s")
                        await asyncio.sleep(retry_after)
                        continue
                        
                    if response.status == 403:  # Quota exceeded
                        error_text = await response.text()
                        logger.error(f"YouTube API quota exceeded: {error_text}")
                        raise ValueError("YouTube API quota exceeded")
                        
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"YouTube API error: {error_text}")
                        if attempt == max_retries - 1:
                            raise ValueError(f"YouTube API error: {response.status}")
                        await asyncio.sleep(2 ** attempt)
                        continue
                    
                    search_data = await response.json()
                
                # No results found
                if not search_data.get('items'):
                    logger.info(f"No search results found for: {query}")
                    return []
                
                # Get video ID to fetch detailed info
                video_id = search_data['items'][0]['id']['videoId']
                logger.debug(f"Found video ID {video_id} for query: {query}")
                
                # Get detailed video info like muse does
                video = await get_video_details(video_id, api_key)
                
                if not video:
                    logger.warning(f"Failed to get video details for {video_id}")
                    return []
                
                # Process chapters if needed like muse
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
                
                # Cache the result with reasonable TTL
                await key_value_cache.set(
                    cache_key,
                    json.dumps(result),
                    ONE_HOUR_IN_SECONDS
                )
                
                return result
                
        except asyncio.TimeoutError:
            logger.warning(f"YouTube API timeout on attempt {attempt + 1}")
            if attempt == max_retries - 1:
                raise ValueError("YouTube API timeout after retries")
            await asyncio.sleep(2 ** attempt)
            
        except aiohttp.ClientError as e:
            logger.warning(f"YouTube API connection error on attempt {attempt + 1}: {e}")
            if attempt == max_retries - 1:
                raise ValueError(f"YouTube API connection error: {e}")
            await asyncio.sleep(2 ** attempt)
            
        except Exception as e:
            logger.error(f"Error searching YouTube: {str(e)}")
            if attempt == max_retries - 1:
                return []
            await asyncio.sleep(2 ** attempt)
    
    return []

async def get_youtube_video(
    url: str,
    should_split_chapters: bool,
    api_key: str
) -> List[Dict[str, Any]]:
    """
    Get metadata for a YouTube video URL - improved like muse
    
    Args:
        url: YouTube URL
        should_split_chapters: Whether to split video into chapters
        api_key: YouTube API key
        
    Returns:
        List of song metadata dictionaries
    """
    # Extract video ID from URL like muse does
    video_id = extract_youtube_id(url)
    if not video_id:
        logger.warning(f"Could not extract video ID from URL: {url}")
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
            logger.warning(f"No video details found for {video_id}")
            return []
        
        # Process chapters if needed like muse
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
    Get metadata for a YouTube playlist - improved to match muse's playlist handling
    
    Args:
        playlist_id: YouTube playlist ID
        should_split_chapters: Whether to split videos into chapters
        api_key: YouTube API key
        
    Returns:
        List of song metadata dictionaries
    """
    # Try to get from cache with shorter TTL since playlists change
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
    """Implementation of playlist retrieval with improved error handling like muse"""
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            # Get playlist details first
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=60, connect=10),
                connector=aiohttp.TCPConnector(limit=10, limit_per_host=5)
            ) as session:
                # Get playlist metadata
                params = {
                    'part': 'snippet,contentDetails',
                    'id': playlist_id,
                    'key': api_key
                }
                
                async with session.get(
                    'https://www.googleapis.com/youtube/v3/playlists',
                    params=params
                ) as response:
                    if response.status == 429:  # Rate limit
                        retry_after = int(response.headers.get('Retry-After', '60'))
                        logger.warning(f"YouTube API rate limit hit, waiting {retry_after}s")
                        await asyncio.sleep(retry_after)
                        continue
                        
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"YouTube playlist API error: {error_text}")
                        if attempt == max_retries - 1:
                            raise ValueError(f"YouTube API error: {response.status}")
                        await asyncio.sleep(2 ** attempt)
                        continue
                    
                    playlist_data = await response.json()
                
                if not playlist_data.get('items'):
                    logger.warning(f"Playlist not found: {playlist_id}")
                    return []
                
                playlist = playlist_data['items'][0]
                playlist_title = playlist['snippet']['title']
                
                logger.info(f"Processing playlist '{playlist_title}' ({playlist_id})")
                
                # Get playlist items with pagination like muse does
                all_video_ids = []
                next_page_token = None
                items_processed = 0
                max_items = 1000  # Reasonable limit to prevent abuse
                
                while len(all_video_ids) < max_items:
                    params = {
                        'part': 'snippet,contentDetails',
                        'maxResults': 50,  # Max allowed by API
                        'playlistId': playlist_id,
                        'key': api_key
                    }
                    
                    if next_page_token:
                        params['pageToken'] = next_page_token
                    
                    # Get items for this page with retry logic
                    page_success = False
                    for page_attempt in range(3):
                        try:
                            async with session.get(
                                'https://www.googleapis.com/youtube/v3/playlistItems',
                                params=params
                            ) as response:
                                if response.status == 429:  # Rate limit
                                    retry_after = int(response.headers.get('Retry-After', '30'))
                                    logger.warning(f"YouTube API rate limit hit, waiting {retry_after}s")
                                    await asyncio.sleep(retry_after)
                                    continue
                                    
                                if response.status != 200:
                                    error_text = await response.text()
                                    logger.error(f"YouTube playlist items API error: {error_text}")
                                    if page_attempt == 2:
                                        break
                                    await asyncio.sleep(2 ** page_attempt)
                                    continue
                                
                                items_data = await response.json()
                                page_success = True
                                break
                        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                            logger.warning(f"Connection error on page attempt {page_attempt + 1}: {e}")
                            if page_attempt == 2:
                                break
                            await asyncio.sleep(2 ** page_attempt)
                    
                    if not page_success:
                        logger.error(f"Failed to get playlist page after retries")
                        break
                    
                    # Extract video IDs from this page
                    page_video_ids = []
                    for item in items_data.get('items', []):
                        video_id = item.get('contentDetails', {}).get('videoId')
                        if video_id:
                            page_video_ids.append(video_id)
                    
                    all_video_ids.extend(page_video_ids)
                    items_processed += len(page_video_ids)
                    
                    logger.debug(f"Processed {items_processed} playlist items so far")
                    
                    # Check if there are more pages
                    next_page_token = items_data.get('nextPageToken')
                    if not next_page_token:
                        break
                
                # Create playlist object like muse
                playlist_obj = {
                    'title': playlist_title,
                    'source': playlist_id
                }
                
                logger.info(f"Found {len(all_video_ids)} videos in playlist")
                
                # Process videos in batches like muse to avoid overwhelming the API
                results = []
                batch_size = 50  # YouTube API limit for video details
                
                for i in range(0, len(all_video_ids), batch_size):
                    batch = all_video_ids[i:i+batch_size]
                    logger.debug(f"Processing batch {i//batch_size + 1}: {len(batch)} videos")
                    
                    try:
                        batch_videos = await get_videos_details(batch, api_key)
                        
                        for video in batch_videos:
                            if video:
                                # Skip unavailable videos like muse does
                                if not video.get('snippet') or not video.get('contentDetails'):
                                    logger.debug(f"Skipping unavailable video in playlist")
                                    continue
                                
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
                    except Exception as e:
                        logger.error(f"Error processing playlist batch: {e}")
                        # Continue with other batches
                        continue
                
                logger.info(f"Successfully processed {len(results)} tracks from playlist '{playlist_title}'")
                
                # Cache the result with shorter TTL since playlists change
                await key_value_cache.set(
                    cache_key,
                    json.dumps(results),
                    TEN_MINUTES_IN_SECONDS * 6  # 1 hour
                )
                
                return results
                
        except asyncio.TimeoutError:
            logger.warning(f"YouTube playlist API timeout on attempt {attempt + 1}")
            if attempt == max_retries - 1:
                return []
            await asyncio.sleep(2 ** attempt)
            
        except aiohttp.ClientError as e:
            logger.warning(f"YouTube playlist API connection error on attempt {attempt + 1}: {e}")
            if attempt == max_retries - 1:
                return []
            await asyncio.sleep(2 ** attempt)
            
        except Exception as e:
            logger.error(f"Error getting YouTube playlist: {str(e)}")
            if attempt == max_retries - 1:
                return []
            await asyncio.sleep(2 ** attempt)
    
    return []

async def get_video_details(video_id: str, api_key: str) -> Optional[Dict[str, Any]]:
    """Get detailed information about a YouTube video with retry logic like muse"""
    # Try to get from cache with 1 hour TTL
    cache_key = f"youtube_video_details:{video_id}"
    cached = await key_value_cache.get(cache_key)
    if cached:
        return json.loads(cached)
    
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30, connect=10),
                connector=aiohttp.TCPConnector(limit=10, limit_per_host=5)
            ) as session:
                params = {
                    'part': 'snippet,contentDetails,statistics',
                    'id': video_id,
                    'key': api_key
                }
                
                async with session.get(
                    'https://www.googleapis.com/youtube/v3/videos',
                    params=params
                ) as response:
                    if response.status == 429:  # Rate limit
                        retry_after = int(response.headers.get('Retry-After', '60'))
                        logger.warning(f"YouTube API rate limit hit, waiting {retry_after}s")
                        await asyncio.sleep(retry_after)
                        continue
                        
                    if response.status != 200:
                        if attempt == max_retries - 1:
                            logger.warning(f"Failed to get video details for {video_id}: HTTP {response.status}")
                            return None
                        await asyncio.sleep(2 ** attempt)
                        continue
                    
                    data = await response.json()
                
                if not data.get('items'):
                    logger.warning(f"No video data returned for {video_id}")
                    return None
                
                result = data['items'][0]
                
                # Cache the video details like muse
                await key_value_cache.set(
                    cache_key,
                    json.dumps(result),
                    ONE_HOUR_IN_SECONDS
                )
                
                return result
                
        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            logger.warning(f"Connection error getting video details on attempt {attempt + 1}: {e}")
            if attempt == max_retries - 1:
                return None
            await asyncio.sleep(2 ** attempt)
        except Exception as e:
            logger.error(f"Error getting video details: {e}")
            if attempt == max_retries - 1:
                return None
            await asyncio.sleep(2 ** attempt)
    
    return None

async def get_videos_details(video_ids: List[str], api_key: str) -> List[Dict[str, Any]]:
    """Get detailed information about multiple YouTube videos like muse"""
    if not video_ids:
        return []
    
    # Batch the video IDs to avoid URL length limitations
    batch_size = 50  # YouTube API maximum
    batches = [video_ids[i:i+batch_size] for i in range(0, len(video_ids), batch_size)]
    
    results = []
    for batch in batches:
        # Create a cache key for this batch
        batch_key = f"youtube_videos_batch:{','.join(sorted(batch))}"
        cached = await key_value_cache.get(batch_key)
        
        if cached:
            results.extend(json.loads(cached))
            continue
        
        # Need to fetch this batch with retry logic
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=30, connect=10),
                    connector=aiohttp.TCPConnector(limit=10, limit_per_host=5)
                ) as session:
                    params = {
                        'part': 'snippet,contentDetails,statistics',
                        'id': ','.join(batch),
                        'key': api_key
                    }
                    
                    async with session.get(
                        'https://www.googleapis.com/youtube/v3/videos',
                        params=params
                    ) as response:
                        if response.status == 429:  # Rate limit
                            retry_after = int(response.headers.get('Retry-After', '60'))
                            logger.warning(f"YouTube API rate limit hit, waiting {retry_after}s")
                            await asyncio.sleep(retry_after)
                            continue
                            
                        if response.status != 200:
                            if attempt == max_retries - 1:
                                logger.warning(f"Failed to get batch video details: HTTP {response.status}")
                                break
                            await asyncio.sleep(2 ** attempt)
                            continue
                        
                        data = await response.json()
                
                batch_results = data.get('items', [])
                results.extend(batch_results)
                
                # Cache this batch with shorter TTL
                await key_value_cache.set(
                    batch_key,
                    json.dumps(batch_results),
                    TEN_MINUTES_IN_SECONDS * 6  # 1 hour
                )
                break
                
            except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                logger.warning(f"Connection error getting batch details on attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    break
                await asyncio.sleep(2 ** attempt)
            except Exception as e:
                logger.error(f"Error getting batch details: {e}")
                if attempt == max_retries - 1:
                    break
                await asyncio.sleep(2 ** attempt)
    
    return results

async def process_video_chapters(
    video: Dict[str, Any],
    api_key: str,
    playlist: Optional[Dict[str, str]] = None
) -> Optional[List[Dict[str, Any]]]:
    """
    Process a video into chapters if available - improved to match muse's chapter detection
    
    Args:
        video: Video data
        api_key: YouTube API key
        playlist: Optional playlist data
        
    Returns:
        List of chapter metadata or None if no chapters
    """
    # Get video description
    description = video['snippet'].get('description', '')
    
    # Try to extract chapters from description like muse
    chapters = parse_chapters_from_description(
        description, 
        parse_duration(video['contentDetails']['duration'])
    )
    
    if not chapters:
        logger.debug(f"No chapters found in video {video['id']}")
        return None
    
    logger.info(f"Found {len(chapters)} chapters in video {video['id']}")
    
    # Format each chapter as a song like muse does
    results = []
    
    for chapter_title, time_info in chapters:
        # Create a copy of the video for this chapter
        chapter = format_video_metadata(video, playlist)
        
        # Update with chapter info like muse
        chapter['title'] = f"{chapter_title} ({chapter['title']})"
        chapter['offset'] = time_info['offset']
        chapter['length'] = time_info['length']
        
        results.append(chapter)
    
    return results

def format_video_metadata(
    video: Dict[str, Any],
    playlist: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Format video data as song metadata like muse"""
    video_id = video['id']
    title = video['snippet']['title']
    channel = video['snippet']['channelTitle']
    
    # Check if video is live like muse does
    live_broadcast_content = video['snippet'].get('liveBroadcastContent', 'none')
    is_live = live_broadcast_content in ('live', 'upcoming')
    
    # Get duration like muse
    duration = 0 if is_live else parse_duration(video['contentDetails']['duration'])
    
    # Get thumbnail like muse - prefer medium, fallback to default
    thumbnail_url = None
    thumbnails = video['snippet'].get('thumbnails', {})
    if 'medium' in thumbnails:
        thumbnail_url = thumbnails['medium']['url']
    elif 'default' in thumbnails:
        thumbnail_url = thumbnails['default']['url']
    elif 'high' in thumbnails:
        thumbnail_url = thumbnails['high']['url']
    
    return {
        'title': title,
        'artist': channel,
        'url': video_id,  # Just the video ID like muse
        'length': duration,
        'offset': 0,
        'playlist': playlist,
        'is_live': is_live,
        'thumbnail_url': thumbnail_url,
        'source': 0  # MediaSource.YOUTUBE
    }

def parse_chapters_from_description(description: str, video_duration: int) -> List[Tuple[str, Dict[str, int]]]:
    """
    Parse chapter timestamps from a video description - improved to match muse's logic
    
    Returns:
        List of (chapter_title, {offset, length}) tuples
    """
    if not description or video_duration <= 0:
        return []
    
    # Look for chapter markers in the description like muse does
    lines = description.split('\n')
    timestamps = []
    found_first_timestamp = False
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Look for timestamp pattern like muse - handle various formats
        # Patterns: 0:00, 1:30, 01:45, 1:30:45, etc.
        timestamp_patterns = [
            r'(?:^|\s)(\d{1,2}:\d{2}:\d{2})(?:\s|$)',  # HH:MM:SS
            r'(?:^|\s)(\d{1,2}:\d{2})(?:\s|$)',        # MM:SS or HH:MM
        ]
        
        match = None
        for pattern in timestamp_patterns:
            match = re.search(pattern, line)
            if match:
                break
        
        if not match:
            continue
        
        # Parse the timestamp like muse
        timestamp_str = match.group(1)
        time_parts = timestamp_str.split(':')
        
        try:
            if len(time_parts) == 2:
                minutes, seconds = int(time_parts[0]), int(time_parts[1])
                timestamp = minutes * 60 + seconds
            elif len(time_parts) == 3:
                hours, minutes, seconds = int(time_parts[0]), int(time_parts[1]), int(time_parts[2])
                timestamp = hours * 3600 + minutes * 60 + seconds
            else:
                continue
        except ValueError:
            continue
        
        # Validate timestamp is within video duration
        if timestamp > video_duration:
            continue
        
        # Check if this might be the first chapter like muse
        if not found_first_timestamp:
            if timestamp <= 10:  # First timestamp should be near beginning
                found_first_timestamp = True
            else:
                continue
        
        # Get the chapter title (text after timestamp) like muse
        title_start = match.end()
        chapter_title = line[title_start:].strip()
        
        # Clean up the chapter title
        chapter_title = re.sub(r'^[-\s]+', '', chapter_title)  # Remove leading dashes/spaces
        chapter_title = re.sub(r'[-\s]+$', '', chapter_title)  # Remove trailing dashes/spaces
        
        if not chapter_title:
            chapter_title = f"Chapter {len(timestamps) + 1}"
        
        timestamps.append((timestamp, chapter_title))
    
    # Sort timestamps by time like muse
    timestamps.sort(key=lambda x: x[0])
    
    # Must have at least 2 timestamps for chapters like muse
    if len(timestamps) < 2:
        return []
    
    # First timestamp should be near the beginning like muse
    if timestamps[0][0] > 30:  # More lenient than muse's 10 seconds
        return []
    
    # Convert to chapter format like muse
    chapters = []
    
    for i, (timestamp, title) in enumerate(timestamps):
        # Chapter length is until next timestamp or end of video like muse
        if i < len(timestamps) - 1:
            length = timestamps[i+1][0] - timestamp
        else:
            length = video_duration - timestamp
        
        # Skip chapters that are too short (less than 10 seconds)
        if length < 10:
            continue
        
        chapters.append((
            title, 
            {'offset': timestamp, 'length': length}
        ))
    
    return chapters

def parse_duration(duration_str: str) -> int:
    """
    Parse ISO 8601 duration format used by YouTube API - improved error handling like muse
    
    Example: 'PT1H30M15S' -> 5415 seconds
    """
    if not duration_str:
        return 0
    
    try:
        # Remove PT prefix
        duration_str = duration_str.replace('PT', '')
        
        hours = 0
        minutes = 0
        seconds = 0
        
        # Extract hours
        h_match = re.search(r'(\d+)H', duration_str, re.IGNORECASE)
        if h_match:
            hours = int(h_match.group(1))
        
        # Extract minutes
        m_match = re.search(r'(\d+)M', duration_str, re.IGNORECASE)
        if m_match:
            minutes = int(m_match.group(1))
        
        # Extract seconds (may have decimal)
        s_match = re.search(r'(\d+(?:\.\d+)?)S', duration_str, re.IGNORECASE)
        if s_match:
            seconds = int(float(s_match.group(1)))
        
        total = hours * 3600 + minutes * 60 + seconds
        
        # Sanity check - YouTube videos shouldn't be longer than 12 hours like muse
        if total > 43200:
            logger.warning(f"Suspiciously long duration: {duration_str} -> {total}s")
            return min(total, 43200)
        
        return total
        
    except Exception as e:
        logger.error(f"Error parsing duration '{duration_str}': {e}")
        return 0

def extract_youtube_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from a URL like muse"""
    if not url:
        return None
    
    # Standard YouTube URL patterns like muse
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com/\?v=([a-zA-Z0-9_-]{11})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    # Check if the URL is just the ID like muse
    if re.match(r'^[a-zA-Z0-9_-]{11}$', url):
        return url
    
    return None

async def get_youtube_suggestions(query: str) -> List[str]:
    """Get search suggestions from YouTube for a query like muse"""
    if not query or len(query.strip()) < 2:
        return []
    
    max_retries = 3
            
    for attempt in range(max_retries):
        try:
            # Try to get from cache first
            cache_key = f"youtube_suggestions:{query}"
            cached = await key_value_cache.get(cache_key)
            if cached:
                return json.loads(cached)
            
            # Use Google's suggest API like muse does
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10, connect=5),
                connector=aiohttp.TCPConnector(limit=5, limit_per_host=2)
            ) as session:
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
                        if attempt == max_retries - 1:
                            return []
                        await asyncio.sleep(2 ** attempt)
                        continue
                    
                    # Get response as text first
                    text = await response.text()
                    
                    # Try to parse response as JSON like muse
                    try:
                        # Remove JavaScript callback if present
                        if text.startswith("window.google.ac.h("):
                            text = text[text.index("(")+1:text.rindex(")")]
                        
                        data = json.loads(text)
                        suggestions = []
                        if isinstance(data, list) and len(data) > 1:
                            suggestions = data[1]  # Second element contains suggestions array
                        
                        # Limit suggestions like muse
                        suggestions = suggestions[:25] if suggestions else []
                        
                        # Cache the suggestions with 10 minute TTL like muse
                        await key_value_cache.set(
                            cache_key,
                            json.dumps(suggestions),
                            TEN_MINUTES_IN_SECONDS
                        )
                        
                        return suggestions
                    except json.JSONDecodeError:
                        # Fallback: Try regex extraction like muse
                        suggestions = []
                        matches = re.findall(r'"([^"]+)"', text)
                        if matches and len(matches) > 1:
                            suggestions = matches[1:][:25]  # Skip the first match (query), limit to 25
                        
                        # Cache the suggestions
                        await key_value_cache.set(
                            cache_key,
                            json.dumps(suggestions),
                            TEN_MINUTES_IN_SECONDS
                        )
                        
                        return suggestions
                        
        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            logger.warning(f"Connection error getting YouTube suggestions on attempt {attempt + 1}: {e}")
            if attempt == max_retries - 1:
                return []
            await asyncio.sleep(2 ** attempt)
        except Exception as e:
            logger.error(f"Error getting YouTube suggestions: {e}")
            if attempt == max_retries - 1:
                return []
            await asyncio.sleep(2 ** attempt)
    
    return []

async def test_youtube_api(api_key: str):
    """Test connection to YouTube API like muse"""
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30, connect=10)
            ) as session:
                params = {
                    'part': 'snippet',
                    'q': 'test',
                    'maxResults': 1,
                    'type': 'video',
                    'key': api_key
                }
                
                async with session.get(
                    'https://www.googleapis.com/youtube/v3/search',
                    params=params
                ) as response:
                    if response.status == 403:
                        text = await response.text()
                        if "quotaExceeded" in text or "Daily Limit Exceeded" in text:
                            raise ValueError("YouTube API quota exceeded")
                        elif "invalid" in text.lower() or "key" in text.lower():
                            raise ValueError("Invalid YouTube API key")
                        else:
                            raise ValueError(f"YouTube API access denied: {text}")
                    
                    if response.status != 200:
                        text = await response.text()
                        if attempt == max_retries - 1:
                            raise ValueError(f"YouTube API test failed: {response.status} - {text}")
                        await asyncio.sleep(2 ** attempt)
                        continue
                    
                    data = await response.json()
                    
                    # Verify we got a valid response structure
                    if 'items' not in data:
                        raise ValueError("Invalid YouTube API response structure")
                    
                    logger.info("YouTube API test successful")
                    return True
                    
        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            if attempt == max_retries - 1:
                raise ValueError(f"YouTube API connection failed: {e}")
            await asyncio.sleep(2 ** attempt)
        except Exception as e:
            if attempt == max_retries - 1:
                raise ValueError(f"YouTube API test failed: {e}")
            await asyncio.sleep(2 ** attempt)
    
    return True

# Additional utility functions to match muse's capabilities

async def get_youtube_channel_videos(
    channel_id: str,
    max_results: int,
    api_key: str
) -> List[Dict[str, Any]]:
    """Get videos from a YouTube channel like muse might handle"""
    try:
        # Get uploads playlist ID
        async with aiohttp.ClientSession() as session:
            params = {
                'part': 'contentDetails',
                'id': channel_id,
                'key': api_key
            }
            
            async with session.get(
                'https://www.googleapis.com/youtube/v3/channels',
                params=params
            ) as response:
                if response.status != 200:
                    return []
                
                data = await response.json()
                
                if not data.get('items'):
                    return []
                
                uploads_playlist = data['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        
        # Get videos from uploads playlist
        return await get_youtube_playlist(uploads_playlist, False, api_key)
        
    except Exception as e:
        logger.error(f"Error getting channel videos: {e}")
        return []

def clean_youtube_url(url: str) -> str:
    """Clean a YouTube URL to remove tracking parameters like muse"""
    if not url:
        return url
    
    try:
        # Extract video ID and reconstruct clean URL
        video_id = extract_youtube_id(url)
        if video_id:
            return f"https://www.youtube.com/watch?v={video_id}"
    except Exception:
        pass
    
    return url

# Cache management functions
async def clear_youtube_cache():
    """Clear all YouTube-related cache entries"""
    try:
        # This would require a way to list cache keys by pattern
        # For now, we'll just let them expire naturally
        logger.info("YouTube cache clear requested - entries will expire naturally")
    except Exception as e:
        logger.error(f"Error clearing YouTube cache: {e}")

async def get_youtube_cache_stats() -> Dict[str, Any]:
    """Get statistics about YouTube cache usage"""
    # This would require implementing cache statistics in the key-value cache
    return {
        "note": "Cache statistics not yet implemented"
    }