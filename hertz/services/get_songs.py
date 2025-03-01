# hertz/services/get_songs.py
import logging
import re
import asyncio
import urllib.parse
from typing import List, Dict, Any, Tuple, Optional, Union

from ..config import Config
from ..services.youtube import get_youtube_video, get_youtube_playlist, search_youtube
from ..services.player import MediaSource, SongMetadata

logger = logging.getLogger(__name__)

class GetSongs:
    """Service for retrieving songs from various sources"""
    
    YOUTUBE_HOSTS = [
        'www.youtube.com',
        'youtu.be',
        'youtube.com',
        'music.youtube.com',
        'www.music.youtube.com',
    ]
    
    def __init__(self, config: Config):
        self.config = config
    
    async def get_songs(
        self, 
        query: str, 
        playlist_limit: int,
        should_split_chapters: bool
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Get songs from a query string
        
        Returns:
            Tuple of (list of songs, extra message)
        """
        new_songs = []
        extra_msg = ""
        
        # Check if it's a URL
        is_url = False
        try:
            url_parts = urllib.parse.urlparse(query)
            is_url = all([url_parts.scheme, url_parts.netloc])
        except Exception:
            is_url = False
        
        if is_url:
            # Process URL
            url_host = url_parts.netloc
            
            if url_host in self.YOUTUBE_HOSTS:
                # YouTube URL
                query_params = urllib.parse.parse_qs(url_parts.query)
                
                if 'list' in query_params:
                    # YouTube playlist
                    playlist_id = query_params['list'][0]
                    new_songs = await get_youtube_playlist(
                        playlist_id, 
                        should_split_chapters,
                        self.config.YOUTUBE_API_KEY
                    )
                else:
                    # YouTube video
                    songs = await get_youtube_video(
                        query, 
                        should_split_chapters,
                        self.config.YOUTUBE_API_KEY
                    )
                    if songs:
                        new_songs = songs
                    else:
                        raise ValueError("that doesn't exist")
            elif 'spotify.com' in url_host or url_parts.scheme == 'spotify':
                # Spotify URL
                if not self.config.SPOTIFY_CLIENT_ID or not self.config.SPOTIFY_CLIENT_SECRET:
                    raise ValueError("Spotify support is not configured")
                
                # Import here to avoid circular imports
                from ..services.spotify import get_spotify_tracks
                
                converted_songs, n_songs_not_found, total_songs = await get_spotify_tracks(
                    query, 
                    playlist_limit,
                    should_split_chapters,
                    self.config
                )
                
                if total_songs > playlist_limit:
                    extra_msg = f"a random sample of {playlist_limit} songs was taken"
                
                if total_songs > playlist_limit and n_songs_not_found != 0:
                    extra_msg += " and "
                
                if n_songs_not_found != 0:
                    if n_songs_not_found == 1:
                        extra_msg += "1 song was not found"
                    else:
                        extra_msg += f"{n_songs_not_found} songs were not found"
                
                new_songs = converted_songs
            else:
                # Treat as HTTP livestream
                song = await self._get_http_stream(query)
                if song:
                    new_songs = [song]
                else:
                    raise ValueError("that doesn't exist")
        else:
            # Not a URL, search YouTube
            songs = await search_youtube(
                query, 
                should_split_chapters,
                self.config.YOUTUBE_API_KEY
            )
            
            if songs:
                new_songs = songs
            else:
                raise ValueError("no results found")
        
        return new_songs, extra_msg
    
    async def _get_http_stream(self, url: str) -> Optional[Dict[str, Any]]:
        """Try to get an HTTP livestream"""
        import subprocess
        
        try:
            # Use ffprobe to check if the URL is a valid media stream
            process = await asyncio.create_subprocess_exec(
                'ffprobe', '-v', 'quiet', '-print_format', 'json', 
                '-show_format', '-show_streams', url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, _ = await process.communicate()
            
            if process.returncode == 0:
                # Looks like a valid stream
                return {
                    "title": url,
                    "artist": url,
                    "url": url,
                    "length": 0,
                    "offset": 0,
                    "playlist": None,
                    "is_live": True,
                    "thumbnail_url": None,
                    "source": MediaSource.HLS.value
                }
        except Exception as e:
            logger.error(f"Error checking HTTP stream: {e}")
        
        return None