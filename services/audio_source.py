"""
Simplified audio source handler for HERTZ bot
Based on working patterns from Dandelion Music Bot
"""

import asyncio
import logging
import tempfile
import os
from typing import Dict, Any, Optional, List
from pathlib import Path
import discord
import yt_dlp

logger = logging.getLogger(__name__)

# yt-dlp options (simplified and proven to work)
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

# FFmpeg options for Discord (proven to work)
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

class YTDLSource(discord.PCMVolumeTransformer):
    """Audio source using yt-dlp with volume control."""
    
    def __init__(self, source: discord.AudioSource, *, data: Dict[str, Any], volume: float = 0.5):
        super().__init__(source, volume=volume)
        
        self.data = data
        self.title = data.get('title', 'Unknown')
        self.url = data.get('url', '')
        self.duration = data.get('duration', 0)
        self.thumbnail = data.get('thumbnail', '')
        self.uploader = data.get('uploader', 'Unknown')
    
    @classmethod
    async def from_url(cls, url: str, *, loop: Optional[asyncio.AbstractEventLoop] = None, stream: bool = True, volume: float = 0.5, seek_time: int = 0):
        """Create audio source from URL."""
        loop = loop or asyncio.get_event_loop()
        
        try:
            data = await loop.run_in_executor(None, lambda: cls._extract_info(url))
            
            if not data:
                raise Exception("Could not extract video info")
            
            # Prepare FFmpeg options
            ffmpeg_opts = FFMPEG_OPTIONS.copy()
            
            # Add seek time if specified
            if seek_time > 0:
                ffmpeg_opts['before_options'] += f' -ss {seek_time}'
            
            # Get the audio URL
            if stream:
                # Stream directly
                filename = data['url']
            else:
                # Download first (for caching)
                filename = await loop.run_in_executor(None, lambda: cls._download(url))
            
            # Create Discord audio source
            source = discord.FFmpegPCMAudio(filename, **ffmpeg_opts)
            
            return cls(source, data=data, volume=volume)
            
        except Exception as e:
            logger.error(f"Error creating audio source from {url}: {e}")
            raise
    
    @staticmethod
    def _extract_info(url: str) -> Dict[str, Any]:
        """Extract video info using yt-dlp."""
        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ytdl:
            info = ytdl.extract_info(url, download=False)
            
            if not info:
                raise Exception("No video info found")
            
            # Handle playlist results
            if 'entries' in info:
                info = info['entries'][0]
            
            return info
    
    @staticmethod
    def _download(url: str) -> str:
        """Download audio file."""
        temp_dir = tempfile.gettempdir()
        
        download_opts = YTDL_OPTIONS.copy()
        download_opts.update({
            'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
        })
        
        with yt_dlp.YoutubeDL(download_opts) as ytdl:
            info = ytdl.extract_info(url, download=True)
            
            if 'entries' in info:
                info = info['entries'][0]
            
            filename = ytdl.prepare_filename(info)
            return filename

class AudioSource:
    """Simplified audio source handler."""
    
    @classmethod
    async def create(cls, track: Dict[str, Any], volume: float = 0.5, seek_position: int = 0) -> discord.AudioSource:
        """Create an audio source from track information."""
        try:
            logger.debug(f"Creating audio source for: {track.get('title', 'Unknown')}")
            
            # Create YTDLSource
            source = await YTDLSource.from_url(
                track['url'],
                stream=True,
                volume=volume,
                seek_time=seek_position
            )
            
            return source
            
        except Exception as e:
            logger.error(f"Failed to create audio source for {track.get('title', 'Unknown')}: {e}")
            raise
    
    @classmethod
    async def get_track_info(cls, url: str) -> Dict[str, Any]:
        """Get track information from URL."""
        loop = asyncio.get_event_loop()
        
        try:
            data = await loop.run_in_executor(None, lambda: cls._extract_info(url))
            
            # Format track info
            track_info = {
                'title': data.get('title', 'Unknown Title'),
                'artist': data.get('uploader', 'Unknown Artist'),
                'duration': data.get('duration'),
                'thumbnail_url': data.get('thumbnail'),
                'url': url,
                'source': 'youtube',
                'source_id': data.get('id'),
                'description': data.get('description', ''),
                'view_count': data.get('view_count'),
            }
            
            # Determine actual source from extractor
            extractor = data.get('extractor', '').lower()
            if 'youtube' in extractor:
                track_info['source'] = 'youtube'
            elif 'soundcloud' in extractor:
                track_info['source'] = 'soundcloud'
            elif 'bandcamp' in extractor:
                track_info['source'] = 'bandcamp'
            
            return track_info
            
        except Exception as e:
            logger.error(f"Failed to extract info for {url}: {e}")
            raise
    
    @classmethod
    async def search_tracks(cls, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """Search for tracks."""
        loop = asyncio.get_event_loop()
        
        def search():
            search_opts = YTDL_OPTIONS.copy()
            search_opts.update({
                'default_search': f'ytsearch{max_results}:',
                'quiet': True,
            })
            
            with yt_dlp.YoutubeDL(search_opts) as ytdl:
                try:
                    info = ytdl.extract_info(query, download=False)
                    
                    if 'entries' not in info:
                        return []
                    
                    results = []
                    for entry in info['entries']:
                        if entry:
                            track_info = {
                                'title': entry.get('title', 'Unknown Title'),
                                'artist': entry.get('uploader', 'Unknown Artist'),
                                'duration': entry.get('duration'),
                                'thumbnail_url': entry.get('thumbnail'),
                                'url': entry.get('webpage_url', entry.get('url')),
                                'source': 'youtube',
                                'source_id': entry.get('id'),
                                'view_count': entry.get('view_count'),
                            }
                            results.append(track_info)
                    
                    return results
                    
                except Exception as e:
                    logger.error(f"Search failed for query '{query}': {e}")
                    return []
        
        return await loop.run_in_executor(None, search)
    
    @classmethod
    async def is_url_supported(cls, url: str) -> bool:
        """Check if URL is supported."""
        try:
            # Simple check - try to extract info
            await cls.get_track_info(url)
            return True
        except Exception:
            return False
    
    @staticmethod
    def _extract_info(url: str) -> Dict[str, Any]:
        """Extract info using yt-dlp."""
        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ytdl:
            info = ytdl.extract_info(url, download=False)
            
            if not info:
                raise Exception("No info found")
            
            if 'entries' in info:
                info = info['entries'][0]
            
            return info