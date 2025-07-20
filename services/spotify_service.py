"""
Spotify service for HERTZ bot
Handles Spotify API integration and playlist/track resolution
"""

import asyncio
import logging
import re
import base64
import json
import time
from typing import List, Dict, Any, Optional
import aiohttp
from urllib.parse import urlparse, parse_qs

from config.settings import get_config

logger = logging.getLogger(__name__)

class SpotifyService:
    """Service for Spotify operations."""
    
    def __init__(self):
        self.config = get_config()
        self.session: Optional[aiohttp.ClientSession] = None
        self.access_token: Optional[str] = None
        self.token_expires_at: float = 0
        self._token_lock = asyncio.Lock()
        
        # Compile regex patterns for URL matching
        self.track_pattern = re.compile(r'spotify\.com/track/([a-zA-Z0-9]+)')
        self.album_pattern = re.compile(r'spotify\.com/album/([a-zA-Z0-9]+)')
        self.playlist_pattern = re.compile(r'spotify\.com/playlist/([a-zA-Z0-9]+)')
        self.artist_pattern = re.compile(r'spotify\.com/artist/([a-zA-Z0-9]+)')
        
        self.is_available = self.config.has_spotify
        
        # API endpoints
        self.base_url = "https://api.spotify.com/v1"
        self.auth_url = "https://accounts.spotify.com/api/token"
        
        if self.is_available:
            logger.info("Spotify service initialized with credentials")
        else:
            logger.info("Spotify service initialized without credentials (disabled)")
    
    async def initialize(self, session: aiohttp.ClientSession):
        """Initialize the service with HTTP session."""
        self.session = session
        
        if self.is_available:
            try:
                await self._get_access_token()
                logger.info("Spotify service session initialized and authenticated")
            except Exception as e:
                logger.error(f"Failed to authenticate with Spotify: {e}")
                self.is_available = False
        else:
            logger.info("Spotify service session initialized (no credentials)")
    
    async def _get_access_token(self) -> str:
        """Get or refresh Spotify access token."""
        if not self.is_available:
            raise ValueError("Spotify credentials not configured")
        
        async with self._token_lock:
            # Check if current token is still valid
            if self.access_token and time.time() < self.token_expires_at - 60:
                return self.access_token
            
            # Get new token
            auth_string = f"{self.config.spotify_client_id}:{self.config.spotify_client_secret}"
            auth_bytes = auth_string.encode('ascii')
            auth_base64 = base64.b64encode(auth_bytes).decode('ascii')
            
            headers = {
                'Authorization': f'Basic {auth_base64}',
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            data = {
                'grant_type': 'client_credentials'
            }
            
            async with self.session.post(self.auth_url, headers=headers, data=data) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise ValueError(f"Failed to get Spotify token: {response.status} - {error_text}")
                
                token_data = await response.json()
                
                self.access_token = token_data['access_token']
                expires_in = token_data.get('expires_in', 3600)
                self.token_expires_at = time.time() + expires_in
                
                logger.debug("Obtained new Spotify access token")
                return self.access_token
    
    async def _make_api_request(self, endpoint: str, params: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """Make authenticated request to Spotify API."""
        if not self.is_available:
            return None
        
        try:
            token = await self._get_access_token()
            headers = {'Authorization': f'Bearer {token}'}
            
            url = f"{self.base_url}/{endpoint}"
            
            async with self.session.get(url, headers=headers, params=params or {}) as response:
                if response.status == 429:
                    # Rate limited
                    retry_after = int(response.headers.get('Retry-After', 1))
                    logger.warning(f"Spotify rate limited, waiting {retry_after}s")
                    await asyncio.sleep(retry_after)
                    return await self._make_api_request(endpoint, params)
                
                if response.status == 401:
                    # Token expired, clear it and retry once
                    self.access_token = None
                    token = await self._get_access_token()
                    headers = {'Authorization': f'Bearer {token}'}
                    
                    async with self.session.get(url, headers=headers, params=params or {}) as retry_response:
                        if retry_response.status == 200:
                            return await retry_response.json()
                        else:
                            logger.error(f"Spotify API request failed after retry: {retry_response.status}")
                            return None
                
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"Spotify API request failed: {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"Spotify API request error: {e}")
            return None
    
    def is_spotify_url(self, url: str) -> bool:
        """Check if URL is a Spotify URL."""
        return 'spotify.com' in url or url.startswith('spotify:')
    
    def _extract_id_from_url(self, url: str) -> tuple[Optional[str], Optional[str]]:
        """Extract Spotify ID and type from URL."""
        # Handle spotify: URIs
        if url.startswith('spotify:'):
            parts = url.split(':')
            if len(parts) >= 3:
                return parts[2], parts[1]  # id, type
        
        # Handle open.spotify.com URLs
        if 'track/' in url:
            match = self.track_pattern.search(url)
            if match:
                return match.group(1), 'track'
        
        if 'album/' in url:
            match = self.album_pattern.search(url)
            if match:
                return match.group(1), 'album'
        
        if 'playlist/' in url:
            match = self.playlist_pattern.search(url)
            if match:
                return match.group(1), 'playlist'
        
        if 'artist/' in url:
            match = self.artist_pattern.search(url)
            if match:
                return match.group(1), 'artist'
        
        return None, None
    
    async def get_track(self, track_id: str) -> Optional[Dict[str, Any]]:
        """Get track information by ID."""
        data = await self._make_api_request(f"tracks/{track_id}")
        
        if data:
            return self._format_track(data)
        
        return None
    
    async def get_album(self, album_id: str) -> Optional[Dict[str, Any]]:
        """Get album information and tracks."""
        data = await self._make_api_request(f"albums/{album_id}")
        
        if data:
            album_info = {
                'name': data['name'],
                'artist': ', '.join(artist['name'] for artist in data['artists']),
                'total_tracks': data['total_tracks'],
                'release_date': data['release_date'],
                'image_url': data['images'][0]['url'] if data['images'] else None,
                'tracks': []
            }
            
            # Get all tracks (handle pagination)
            tracks_data = data.get('tracks', {})
            while tracks_data:
                for track in tracks_data.get('items', []):
                    formatted_track = self._format_track(track, album_data=data)
                    album_info['tracks'].append(formatted_track)
                
                # Check for more tracks
                if tracks_data.get('next'):
                    next_url = tracks_data['next'].replace(self.base_url + '/', '')
                    tracks_data = await self._make_api_request(next_url)
                else:
                    break
            
            return album_info
        
        return None
    
    async def get_playlist(self, playlist_id: str) -> Optional[Dict[str, Any]]:
        """Get playlist information and tracks."""
        data = await self._make_api_request(f"playlists/{playlist_id}")
        
        if data:
            playlist_info = {
                'name': data['name'],
                'description': data['description'],
                'owner': data['owner']['display_name'],
                'total_tracks': data['tracks']['total'],
                'image_url': data['images'][0]['url'] if data['images'] else None,
                'tracks': []
            }
            
            # Get all tracks (handle pagination)
            tracks_url = f"playlists/{playlist_id}/tracks"
            tracks_data = await self._make_api_request(tracks_url)
            
            while tracks_data:
                for item in tracks_data.get('items', []):
                    if item['track'] and item['track']['type'] == 'track':
                        formatted_track = self._format_track(item['track'])
                        playlist_info['tracks'].append(formatted_track)
                
                # Check for more tracks
                if tracks_data.get('next'):
                    next_url = tracks_data['next'].replace(self.base_url + '/', '')
                    tracks_data = await self._make_api_request(next_url)
                else:
                    break
            
            return playlist_info
        
        return None
    
    async def get_artist_top_tracks(self, artist_id: str, market: str = 'US') -> List[Dict[str, Any]]:
        """Get artist's top tracks."""
        data = await self._make_api_request(f"artists/{artist_id}/top-tracks", {'market': market})
        
        if data and 'tracks' in data:
            return [self._format_track(track) for track in data['tracks']]
        
        return []
    
    async def search(self, query: str, search_type: str = 'track', limit: int = 10) -> List[Dict[str, Any]]:
        """Search Spotify catalog."""
        params = {
            'q': query,
            'type': search_type,
            'limit': limit,
            'market': 'US'
        }
        
        data = await self._make_api_request("search", params)
        
        if data and f"{search_type}s" in data:
            results = data[f"{search_type}s"]['items']
            
            if search_type == 'track':
                return [self._format_track(track) for track in results]
            elif search_type == 'album':
                return [self._format_album(album) for album in results]
            elif search_type == 'playlist':
                return [self._format_playlist(playlist) for playlist in results]
            elif search_type == 'artist':
                return [self._format_artist(artist) for artist in results]
        
        return []
    
    async def resolve_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Resolve Spotify URL to track(s) information."""
        if not self.is_spotify_url(url):
            return None
        
        spotify_id, content_type = self._extract_id_from_url(url)
        if not spotify_id or not content_type:
            return None
        
        try:
            if content_type == 'track':
                track = await self.get_track(spotify_id)
                if track:
                    return {
                        'type': 'track',
                        'tracks': [track]
                    }
            
            elif content_type == 'album':
                album = await self.get_album(spotify_id)
                if album:
                    return {
                        'type': 'album',
                        'name': album['name'],
                        'artist': album['artist'],
                        'tracks': album['tracks']
                    }
            
            elif content_type == 'playlist':
                playlist = await self.get_playlist(spotify_id)
                if playlist:
                    return {
                        'type': 'playlist',
                        'name': playlist['name'],
                        'owner': playlist['owner'],
                        'tracks': playlist['tracks']
                    }
            
            elif content_type == 'artist':
                tracks = await self.get_artist_top_tracks(spotify_id)
                if tracks:
                    return {
                        'type': 'artist_top_tracks',
                        'tracks': tracks
                    }
            
        except Exception as e:
            logger.error(f"Failed to resolve Spotify URL {url}: {e}")
        
        return None
    
    def _format_track(self, track_data: Dict[str, Any], album_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """Format Spotify track data to standard format."""
        artists = track_data.get('artists', [])
        artist_name = ', '.join(artist['name'] for artist in artists) if artists else 'Unknown Artist'
        
        # Use album data if provided, otherwise use track's album data
        album = album_data or track_data.get('album', {})
        
        return {
            'title': track_data.get('name', 'Unknown Title'),
            'artist': artist_name,
            'album': album.get('name'),
            'duration': track_data.get('duration_ms', 0) // 1000 if track_data.get('duration_ms') else None,
            'url': track_data.get('external_urls', {}).get('spotify', ''),
            'thumbnail_url': album.get('images', [{}])[0].get('url') if album.get('images') else None,
            'source': 'spotify',
            'source_id': track_data.get('id'),
            'explicit': track_data.get('explicit', False),
            'popularity': track_data.get('popularity', 0),
            'preview_url': track_data.get('preview_url'),
            'isrc': track_data.get('external_ids', {}).get('isrc'),
            'release_date': album.get('release_date'),
        }
    
    def _format_album(self, album_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format Spotify album data."""
        artists = album_data.get('artists', [])
        artist_name = ', '.join(artist['name'] for artist in artists) if artists else 'Unknown Artist'
        
        return {
            'name': album_data.get('name', 'Unknown Album'),
            'artist': artist_name,
            'total_tracks': album_data.get('total_tracks', 0),
            'release_date': album_data.get('release_date'),
            'url': album_data.get('external_urls', {}).get('spotify', ''),
            'image_url': album_data.get('images', [{}])[0].get('url') if album_data.get('images') else None,
            'type': album_data.get('album_type', 'album'),
        }
    
    def _format_playlist(self, playlist_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format Spotify playlist data."""
        return {
            'name': playlist_data.get('name', 'Unknown Playlist'),
            'description': playlist_data.get('description', ''),
            'owner': playlist_data.get('owner', {}).get('display_name', 'Unknown'),
            'total_tracks': playlist_data.get('tracks', {}).get('total', 0),
            'url': playlist_data.get('external_urls', {}).get('spotify', ''),
            'image_url': playlist_data.get('images', [{}])[0].get('url') if playlist_data.get('images') else None,
            'public': playlist_data.get('public', False),
        }
    
    def _format_artist(self, artist_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format Spotify artist data."""
        return {
            'name': artist_data.get('name', 'Unknown Artist'),
            'followers': artist_data.get('followers', {}).get('total', 0),
            'popularity': artist_data.get('popularity', 0),
            'url': artist_data.get('external_urls', {}).get('spotify', ''),
            'image_url': artist_data.get('images', [{}])[0].get('url') if artist_data.get('images') else None,
            'genres': artist_data.get('genres', []),
        }
    
    def create_search_query(self, spotify_track: Dict[str, Any]) -> str:
        """Create a search query for YouTube from Spotify track data."""
        title = spotify_track.get('title', '')
        artist = spotify_track.get('artist', '')
        
        # Create basic search query
        query = f"{artist} {title}".strip()
        
        # Remove common problematic strings
        query = re.sub(r'\([^)]*\bfeat\b[^)]*\)', '', query, flags=re.IGNORECASE)
        query = re.sub(r'\([^)]*\bft\b[^)]*\)', '', query, flags=re.IGNORECASE)
        query = re.sub(r'\([^)]*\bremix\b[^)]*\)', '', query, flags=re.IGNORECASE)
        query = re.sub(r'\s+', ' ', query).strip()
        
        return query
    
    async def validate_url(self, url: str) -> bool:
        """Validate if a Spotify URL is accessible."""
        if not self.is_available:
            return False
        
        try:
            spotify_id, content_type = self._extract_id_from_url(url)
            if not spotify_id or not content_type:
                return False
            
            # Try to get basic info
            if content_type == 'track':
                result = await self.get_track(spotify_id)
            elif content_type == 'album':
                result = await self._make_api_request(f"albums/{spotify_id}")
            elif content_type == 'playlist':
                result = await self._make_api_request(f"playlists/{spotify_id}")
            elif content_type == 'artist':
                result = await self._make_api_request(f"artists/{spotify_id}")
            else:
                return False
            
            return result is not None
        
        except Exception:
            return False
    
    async def cleanup(self):
        """Cleanup resources."""
        self.access_token = None
        logger.info("Spotify service cleanup completed")

# Global service instance
spotify_service = SpotifyService()