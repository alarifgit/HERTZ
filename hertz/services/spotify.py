# hertz/services/spotify.py
import asyncio
import logging
import json
import base64
import time
import random
from typing import List, Dict, Any, Optional, Tuple, Union

import aiohttp
from urllib.parse import urlparse, parse_qs

from ..config import Config
from ..services.key_value_cache import KeyValueCache
from ..services.youtube import search_youtube

logger = logging.getLogger(__name__)

# Constants
ONE_HOUR_IN_SECONDS = 60 * 60
ONE_MINUTE_IN_SECONDS = 60

# Initialize cache
key_value_cache = KeyValueCache()

class SpotifyClient:
    """Simple Spotify API client with robust token refresh"""
    
    API_BASE = "https://api.spotify.com/v1"
    TOKEN_URL = "https://accounts.spotify.com/api/token"
    
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.token_expires = 0
    
    async def get_token(self) -> str:
        """Get or refresh Spotify access token with retry logic"""
        # Check if token is still valid (with 60s buffer)
        if self.access_token and time.time() < self.token_expires - 60:
            return self.access_token
        
        # Try to get new token with retries
        max_retries = 3
        retry_count = 0
        last_error = None
        
        while retry_count < max_retries:
            try:
                auth_string = f"{self.client_id}:{self.client_secret}"
                auth_bytes = auth_string.encode("ascii")
                auth_base64 = base64.b64encode(auth_bytes).decode("ascii")
                
                headers = {
                    "Authorization": f"Basic {auth_base64}",
                    "Content-Type": "application/x-www-form-urlencoded"
                }
                
                data = {"grant_type": "client_credentials"}
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        self.TOKEN_URL,
                        headers=headers,
                        data=data,
                        timeout=10  # Add timeout
                    ) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            logger.error(f"Spotify token error: {error_text}")
                            raise ValueError(f"Spotify API error: {response.status}")
                        
                        token_data = await response.json()
                        
                        self.access_token = token_data["access_token"]
                        self.token_expires = time.time() + token_data["expires_in"]
                        
                        # Successfully got token, exit retry loop
                        return self.access_token
                        
            except Exception as e:
                last_error = e
                retry_count += 1
                logger.warning(f"Spotify token retry {retry_count}/{max_retries}: {e}")
                await asyncio.sleep(2 ** retry_count)  # Exponential backoff
        
        # All retries failed
        logger.error(f"Failed to get Spotify token after {max_retries} retries: {last_error}")
        raise ValueError(f"Failed to get Spotify access token: {last_error}")
    
    async def make_request(
        self, 
        endpoint: str, 
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make an authenticated request to the Spotify API with retries"""
        max_retries = 3
        retry_count = 0
        last_error = None
        
        while retry_count < max_retries:
            try:
                token = await self.get_token()
                
                headers = {"Authorization": f"Bearer {token}"}
                url = f"{self.API_BASE}/{endpoint}"
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url,
                        headers=headers,
                        params=params,
                        timeout=10  # Add timeout
                    ) as response:
                        if response.status == 429:  # Rate limit
                            # Get retry-after header
                            retry_after = int(response.headers.get('Retry-After', '5'))
                            logger.warning(f"Spotify rate limit hit. Waiting {retry_after}s")
                            await asyncio.sleep(retry_after)
                            retry_count += 1
                            continue
                            
                        if response.status != 200:
                            error_text = await response.text()
                            logger.error(f"Spotify API error: {error_text}")
                            
                            # If token expired, retry with fresh token
                            if response.status == 401:
                                self.access_token = None
                                retry_count += 1
                                continue
                            
                            raise ValueError(f"Spotify API error: {response.status}")
                        
                        return await response.json()
            except Exception as e:
                last_error = e
                retry_count += 1
                logger.warning(f"Spotify API retry {retry_count}/{max_retries}: {e}")
                await asyncio.sleep(2 ** retry_count)  # Exponential backoff
        
        # All retries failed
        logger.error(f"Failed Spotify API request after {max_retries} retries: {last_error}")
        raise ValueError(f"Spotify API request failed: {last_error}")

# Module-level client instance
_spotify_client = None

def get_spotify_client(config: Config) -> Optional[SpotifyClient]:
    """Get or create Spotify client"""
    global _spotify_client
    
    if not config.SPOTIFY_CLIENT_ID or not config.SPOTIFY_CLIENT_SECRET:
        return None
    
    if _spotify_client is None:
        _spotify_client = SpotifyClient(
            config.SPOTIFY_CLIENT_ID,
            config.SPOTIFY_CLIENT_SECRET
        )
    
    return _spotify_client

async def get_spotify_tracks(
    url: str,
    playlist_limit: int,
    should_split_chapters: bool,
    config: Config
) -> Tuple[List[Dict[str, Any]], int, int]:
    """
    Get tracks from a Spotify URL
    
    Args:
        url: Spotify URL or URI
        playlist_limit: Maximum tracks to return from playlists
        should_split_chapters: Whether to split tracks into chapters
        config: Bot configuration
        
    Returns:
        Tuple of (tracks, not_found_count, total_count)
    """
    client = get_spotify_client(config)
    if not client:
        raise ValueError("Spotify is not configured")
    
    # Parse the Spotify URI/URL
    spotify_id, entity_type = parse_spotify_url(url)
    if not spotify_id or not entity_type:
        raise ValueError("Invalid Spotify URL")
    
    # Handle different entity types
    if entity_type == "track":
        track = await get_spotify_track(spotify_id, client)
        if not track:
            return [], 1, 1
        
        converted = await convert_spotify_track_to_youtube(
            track,
            should_split_chapters,
            config.YOUTUBE_API_KEY
        )
        
        if not converted:
            return [], 1, 1
        
        return [converted], 0, 1
    
    elif entity_type == "album":
        album_tracks, album_title = await get_spotify_album(
            spotify_id,
            client
        )
        
        return await process_spotify_tracks(
            album_tracks,
            {"title": album_title, "source": f"spotify:album:{spotify_id}"},
            playlist_limit,
            should_split_chapters,
            config.YOUTUBE_API_KEY
        )
    
    elif entity_type == "playlist":
        playlist_tracks, playlist_title = await get_spotify_playlist(
            spotify_id,
            client
        )
        
        return await process_spotify_tracks(
            playlist_tracks,
            {"title": playlist_title, "source": f"spotify:playlist:{spotify_id}"},
            playlist_limit,
            should_split_chapters,
            config.YOUTUBE_API_KEY
        )
    
    elif entity_type == "artist":
        artist_tracks, artist_name = await get_spotify_artist_top_tracks(
            spotify_id,
            client
        )
        
        return await process_spotify_tracks(
            artist_tracks,
            {"title": f"{artist_name} Top Tracks", "source": f"spotify:artist:{spotify_id}"},
            playlist_limit,
            should_split_chapters,
            config.YOUTUBE_API_KEY
        )
    
    else:
        raise ValueError("Unsupported Spotify entity type")

async def get_spotify_track(
    track_id: str,
    client: SpotifyClient
) -> Optional[Dict[str, Any]]:
    """Get details for a Spotify track"""
    try:
        track_data = await client.make_request(f"tracks/{track_id}")
        
        if not track_data:
            return None
        
        # Extract relevant information
        track_name = track_data["name"]
        
        artists = [artist["name"] for artist in track_data["artists"]]
        artist_names = ", ".join(artists)
        
        return {
            "name": track_name,
            "artist": artist_names
        }
    
    except Exception as e:
        logger.error(f"Error getting Spotify track: {str(e)}")
        return None

async def get_spotify_album(
    album_id: str,
    client: SpotifyClient
) -> Tuple[List[Dict[str, Any]], str]:
    """Get tracks from a Spotify album"""
    try:
        # Get album details
        album_data = await client.make_request(f"albums/{album_id}")
        album_name = album_data["name"]
        
        # Get album tracks with pagination
        tracks = []
        next_url = album_data["tracks"]["href"].replace(client.API_BASE + "/", "")
        
        while next_url:
            tracks_data = await client.make_request(next_url)
            
            for item in tracks_data["items"]:
                track_name = item["name"]
                
                artists = [artist["name"] for artist in item["artists"]]
                artist_names = ", ".join(artists)
                
                tracks.append({
                    "name": track_name,
                    "artist": artist_names
                })
            
            # Check if there are more tracks
            next_url = tracks_data.get("next")
            if next_url:
                # Extract the relative endpoint from the full URL
                next_url = next_url.replace(client.API_BASE + "/", "")
            
        return tracks, album_name
    
    except Exception as e:
        logger.error(f"Error getting Spotify album: {str(e)}")
        return [], "Unknown Album"

async def get_spotify_playlist(
    playlist_id: str,
    client: SpotifyClient
) -> Tuple[List[Dict[str, Any]], str]:
    """Get tracks from a Spotify playlist"""
    try:
        # Get playlist details
        playlist_data = await client.make_request(f"playlists/{playlist_id}")
        playlist_name = playlist_data["name"]
        
        # Get playlist tracks with pagination
        tracks = []
        next_url = playlist_data["tracks"]["href"].replace(client.API_BASE + "/", "")
        
        while next_url:
            tracks_data = await client.make_request(next_url)
            
            for item in tracks_data["items"]:
                # Skip null tracks
                if not item.get("track"):
                    continue
                
                track = item["track"]
                track_name = track["name"]
                
                artists = [artist["name"] for artist in track["artists"]]
                artist_names = ", ".join(artists)
                
                tracks.append({
                    "name": track_name,
                    "artist": artist_names
                })
            
            # Check if there are more tracks
            next_url = tracks_data.get("next")
            if next_url:
                # Extract the relative endpoint from the full URL
                next_url = next_url.replace(client.API_BASE + "/", "")
            
        return tracks, playlist_name
    
    except Exception as e:
        logger.error(f"Error getting Spotify playlist: {str(e)}")
        return [], "Unknown Playlist"

async def get_spotify_artist_top_tracks(
    artist_id: str,
    client: SpotifyClient
) -> Tuple[List[Dict[str, Any]], str]:
    """Get top tracks from a Spotify artist"""
    try:
        # Get artist details
        artist_data = await client.make_request(f"artists/{artist_id}")
        artist_name = artist_data["name"]
        
        # Get artist top tracks
        top_tracks_data = await client.make_request(f"artists/{artist_id}/top-tracks", {"market": "US"})
        
        tracks = []
        for track in top_tracks_data["tracks"]:
            track_name = track["name"]
            
            artists = [artist["name"] for artist in track["artists"]]
            artist_names = ", ".join(artists)
            
            tracks.append({
                "name": track_name,
                "artist": artist_names
            })
            
        return tracks, artist_name
    
    except Exception as e:
        logger.error(f"Error getting Spotify artist top tracks: {str(e)}")
        return [], "Unknown Artist"

async def process_spotify_tracks(
    tracks: List[Dict[str, Any]],
    playlist: Dict[str, str],
    playlist_limit: int,
    should_split_chapters: bool,
    youtube_api_key: str
) -> Tuple[List[Dict[str, Any]], int, int]:
    """
    Process Spotify tracks into YouTube videos
    
    Args:
        tracks: List of Spotify tracks
        playlist: Playlist metadata
        playlist_limit: Maximum tracks to process
        should_split_chapters: Whether to split videos into chapters
        youtube_api_key: YouTube API key
        
    Returns:
        Tuple of (tracks, not_found_count, total_count)
    """
    # Shuffle and limit if needed
    total_count = len(tracks)
    
    if total_count > playlist_limit:
        # Take a random sample
        tracks = random.sample(tracks, playlist_limit)
    
    # Convert each track - process in batches to avoid overwhelming system
    BATCH_SIZE = 5
    all_results = []
    
    for i in range(0, len(tracks), BATCH_SIZE):
        batch = tracks[i:i+BATCH_SIZE]
        batch_tasks = []
        
        for track in batch:
            batch_tasks.append(
                convert_spotify_track_to_youtube(
                    track,
                    should_split_chapters,
                    youtube_api_key,
                    playlist
                )
            )
        
        # Wait for batch to complete
        batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
        all_results.extend(batch_results)
        
        # Small delay between batches to prevent rate limiting
        if i + BATCH_SIZE < len(tracks):
            await asyncio.sleep(1)
    
    # Filter out failures
    converted_tracks = []
    not_found_count = 0
    
    for result in all_results:
        if isinstance(result, Exception) or result is None:
            not_found_count += 1
            logger.warning(f"Failed to convert track: {result if isinstance(result, Exception) else 'Not found'}")
        else:
            converted_tracks.append(result)
    
    return converted_tracks, not_found_count, total_count

async def convert_spotify_track_to_youtube(
    track: Dict[str, str],
    should_split_chapters: bool,
    youtube_api_key: str,
    playlist: Optional[Dict[str, str]] = None
) -> Optional[Dict[str, Any]]:
    """
    Convert a Spotify track to a YouTube video
    
    Args:
        track: Spotify track metadata
        should_split_chapters: Whether to split video into chapters
        youtube_api_key: YouTube API key
        playlist: Optional playlist metadata
        
    Returns:
        YouTube video metadata or None if not found
    """
    # Create search query with quotes for better matches
    search_query = f'"{track["name"]}" "{track["artist"]}"'
    
    # Try to find on YouTube
    results = await search_youtube(
        search_query,
        should_split_chapters,
        youtube_api_key
    )
    
    if not results:
        return None
    
    # If we have chapters and should split, return all
    if len(results) > 1 and should_split_chapters:
        # Add playlist to all results
        if playlist:
            for result in results:
                result["playlist"] = playlist
        
        return results[0]  # Return first chapter
    
    # Return the first result with playlist if provided
    result = results[0]
    if playlist:
        result["playlist"] = playlist
    
    return result

def parse_spotify_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse a Spotify URL or URI into ID and type
    
    Returns:
        Tuple of (id, type) or (None, None) if invalid
    """
    # Handle Spotify URIs (spotify:type:id)
    if url.startswith("spotify:"):
        parts = url.split(":")
        if len(parts) >= 3:
            return parts[2], parts[1]
    
    # Handle HTTP URLs
    if "open.spotify.com" in url:
        parsed = urlparse(url)
        path_parts = parsed.path.strip("/").split("/")
        
        if len(path_parts) >= 2:
            entity_type = path_parts[0]  # track, album, playlist, artist
            entity_id = path_parts[1]
            
            # Handle playlist URLs with additional ID in query string
            if entity_type == "playlist" and "?" in url:
                query_params = parse_qs(parsed.query)
                if "si" in query_params:
                    # Entity ID is still in the path
                    pass
            
            return entity_id, entity_type
    
    return None, None

async def get_spotify_suggestions(
    query: str,
    config: Config
) -> List[Dict[str, str]]:
    """
    Get search suggestions from Spotify
    
    Args:
        query: Search string
        config: Bot configuration
        
    Returns:
        List of suggestion objects with type, name, and uri
    """
    client = get_spotify_client(config)
    if not client:
        return []
    
    if not query or len(query) < 2:
        return []
    
    # Try to get from cache
    cache_key = f"spotify_suggestions:{query}"
    cached = await key_value_cache.get(cache_key)
    if cached:
        return json.loads(cached)
    
    try:
        # Search Spotify
        params = {
            "q": query,
            "type": "track,album",
            "limit": 10
        }
        
        results = await client.make_request("search", params)
        
        suggestions = []
        
        # Process tracks
        if "tracks" in results and "items" in results["tracks"]:
            for track in results["tracks"]["items"]:
                artist_name = track["artists"][0]["name"] if track["artists"] else "Unknown"
                
                suggestions.append({
                    "type": "track",
                    "name": f"{track['name']} - {artist_name}",
                    "uri": track["uri"]
                })
        
        # Process albums
        if "albums" in results and "items" in results["albums"]:
            for album in results["albums"]["items"]:
                artist_name = album["artists"][0]["name"] if album["artists"] else "Unknown"
                
                suggestions.append({
                    "type": "album",
                    "name": f"{album['name']} - {artist_name}",
                    "uri": album["uri"]
                })
        
        # Cache the result
        await key_value_cache.set(
            cache_key,
            json.dumps(suggestions),
            ONE_MINUTE_IN_SECONDS * 10  # Cache for 10 minutes
        )
        
        return suggestions
        
    except Exception as e:
        logger.error(f"Error getting Spotify suggestions: {str(e)}")
        return []

async def test_spotify_api(config: Config) -> bool:
    """Test Spotify API connectivity"""
    client = get_spotify_client(config)
    if not client:
        raise ValueError("Spotify is not configured")
    
    # Try to get a token
    try:
        await client.get_token()
        # Make a simple API request to verify token works
        await client.make_request("browse/new-releases", {"limit": 1})
        return True
    except Exception as e:
        raise ValueError(f"Spotify API test failed: {e}")