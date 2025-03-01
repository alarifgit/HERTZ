# hertz/services/player.py
import asyncio
import logging
import enum
import os
import hashlib
import shutil
import subprocess
from typing import Optional, List, Dict, Any, Union, Callable
import os
import hashlib

import disnake
from disnake.ext import commands

from ..services.file_cache import FileCacheProvider
from ..utils.time import pretty_time

logger = logging.getLogger(__name__)

class MediaSource(enum.Enum):
    YOUTUBE = 0
    HLS = 1

class Status(enum.Enum):
    PLAYING = 0
    PAUSED = 1
    IDLE = 2

class SongMetadata:
    def __init__(
        self, 
        title: str, 
        artist: str, 
        url: str, 
        length: int,
        offset: int = 0,
        playlist: Optional[Dict[str, str]] = None,
        is_live: bool = False,
        thumbnail_url: Optional[str] = None,
        source: MediaSource = MediaSource.YOUTUBE
    ):
        self.title = title
        self.artist = artist
        self.url = url
        self.length = length
        self.offset = offset
        self.playlist = playlist
        self.is_live = is_live
        self.thumbnail_url = thumbnail_url
        self.source = source

class QueuedSong(SongMetadata):
    def __init__(
        self, 
        added_in_channel_id: str, 
        requested_by: str, 
        **kwargs
    ):
        super().__init__(**kwargs)
        self.added_in_channel_id = added_in_channel_id
        self.requested_by = requested_by

class Player:
    DEFAULT_VOLUME = 100
    
    # Add this line to reference the Status enum from the class
    Status = Status
    
    def __init__(self, file_cache: FileCacheProvider, guild_id: str):
        self.guild_id = guild_id
        self.file_cache = file_cache
        self.voice_client: Optional[disnake.VoiceClient] = None
        self.status = Status.IDLE
        self.queue: List[QueuedSong] = []
        self.queue_position = 0
        self.position_in_seconds = 0
        self.volume = None
        self.default_volume = self.DEFAULT_VOLUME
        self.loop_current_song = False
        self.loop_current_queue = False
        self.position_tracker_task = None
        self.disconnect_timer = None
        self.channel_to_speaking_users = {}
        self.last_song_url = ""
        self.current_channel = None
        self._playback_event_listeners = []
        
        # Store the event loop from the main thread
        self.main_loop = asyncio.get_event_loop()
        
    def add_playback_event_listener(self, callback: Callable):
        """Add a callback for playback events"""
        self._playback_event_listeners.append(callback)
        
    def _notify_playback_event(self, event_type: str, **kwargs):
        """Notify all listeners of a playback event"""
        for callback in self._playback_event_listeners:
            asyncio.create_task(callback(event_type, **kwargs))
        
    def get_current(self) -> Optional[QueuedSong]:
        """Get the currently playing song"""
        if 0 <= self.queue_position < len(self.queue):
            return self.queue[self.queue_position]
        return None
    
    def get_queue(self) -> List[QueuedSong]:
        """Get all songs in queue after the current one"""
        return self.queue[self.queue_position + 1:] if self.queue_position < len(self.queue) else []
    
    def queue_size(self) -> int:
        """Get number of songs in queue"""
        return len(self.get_queue())
    
    def is_queue_empty(self) -> bool:
        """Check if queue is empty"""
        return self.queue_size() == 0
    
    def add(self, song: Union[QueuedSong, Dict[str, Any]], immediate: bool = False) -> None:
        """Add a song to the queue"""
        # Convert dict to QueuedSong if necessary
        if isinstance(song, dict):
            if "source" in song and isinstance(song["source"], int):
                song["source"] = MediaSource(song["source"])
            song = QueuedSong(**song)
            
        if song.playlist or not immediate:
            # Add to end of queue
            self.queue.append(song)
        else:
            # Add as next song
            insert_at = self.queue_position + 1
            self.queue.insert(insert_at, song)
    
    def clear(self) -> None:
        """Clear the queue but keep current song"""
        current = self.get_current()
        if current:
            self.queue = [current]
            self.queue_position = 0
        else:
            self.queue = []
            self.queue_position = 0
    
    def shuffle(self) -> None:
        """Shuffle the queue (excluding current song)"""
        import random
        upcoming = self.get_queue()
        random.shuffle(upcoming)
        self.queue = self.queue[:self.queue_position + 1] + upcoming
    
    def remove_from_queue(self, index: int, amount: int = 1) -> None:
        """Remove songs from the queue"""
        actual_index = self.queue_position + index
        if 0 <= actual_index < len(self.queue):
            del self.queue[actual_index:actual_index + amount]
    
    def move(self, from_pos: int, to_pos: int) -> QueuedSong:
        """Move a song in the queue"""
        actual_from = self.queue_position + from_pos
        actual_to = self.queue_position + to_pos
        
        if not (0 <= actual_from < len(self.queue) and 0 <= actual_to < len(self.queue)):
            raise ValueError("Position out of bounds")
        
        song = self.queue.pop(actual_from)
        self.queue.insert(actual_to, song)
        return song
    
    def get_position(self) -> int:
        """Get current playback position in seconds"""
        return self.position_in_seconds
    
    def get_volume(self) -> int:
        """Get current volume (0-100)"""
        return self.volume if self.volume is not None else self.default_volume
    
    def set_volume(self, level: int) -> None:
        """Set volume level (0-100)"""
        self.volume = max(0, min(100, level))
        if self.voice_client and hasattr(self.voice_client, "source") and self.voice_client.source:
            self.voice_client.source.volume = self.get_volume() / 100.0
    
    async def connect(self, channel: disnake.VoiceChannel) -> None:
        """Connect to a voice channel"""
        # Get default volume from settings
        from ..db.client import get_guild_settings
        settings = await get_guild_settings(self.guild_id)
        self.default_volume = settings.defaultVolume
        
        # Connect to the voice channel
        if self.voice_client:
            if self.voice_client.channel.id != channel.id:
                await self.voice_client.move_to(channel)
        else:
            self.voice_client = await channel.connect(reconnect=True)
        
        # Store reference to the channel for auto-announce
        self.current_channel = channel
        
        # Register voice activity listener for volume reduction when people speak
        self._register_voice_activity_listeners(channel)
    
    async def disconnect(self) -> None:
        """Disconnect from voice channel"""
        self._stop_position_tracking()
        
        if self.disconnect_timer:
            self.disconnect_timer.cancel()
            self.disconnect_timer = None
            
        if self.voice_client:
            if self.status == Status.PLAYING:
                await self.pause()
                
            self.loop_current_song = False
            
            try:
                await self.voice_client.disconnect(force=True)
            except Exception as e:
                logger.warning(f"Error disconnecting: {e}")
                
            self.voice_client = None
            
        self.status = Status.IDLE
        self._notify_playback_event("disconnect")
    
    async def play(self) -> None:
        """Start or resume playback"""
        if not self.voice_client:
            raise ValueError("Not connected to a voice channel")
            
        current_song = self.get_current()
        if not current_song:
            raise ValueError("Queue is empty")
            
        # Cancel any pending disconnect
        if self.disconnect_timer:
            self.disconnect_timer.cancel()
            self.disconnect_timer = None
            
        # Resume from pause
        if (self.status == Status.PAUSED and 
            current_song.url == self.last_song_url and 
            self.voice_client.is_paused()):
            self.voice_client.resume()
            self.status = Status.PLAYING
            self._start_position_tracking()
            self._notify_playback_event("resume", song=current_song)
            return
            
        try:
            # Get offset and duration limits
            offset_seconds = None
            duration = None
            
            if current_song.offset > 0:
                offset_seconds = current_song.offset
                
            if not current_song.is_live:
                duration = current_song.length + current_song.offset
            
            # Get audio source
            source = await self._get_audio_source(
                current_song, 
                seek_position=offset_seconds, 
                duration=duration
            )
            
            # Set up after callback
            def after_playing(error):
                if error:
                    logger.error(f"Error in playback: {error}")
    
                # Queue the coroutine in the main event loop using the stored reference
                self.main_loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(self._handle_song_finished())
                )

            # Play the audio
            self.voice_client.play(source, after=after_playing)
            
            # Stop any current playback
            if self.voice_client.is_playing() or self.voice_client.is_paused():
                self.voice_client.stop()
            
            # Play the audio
            self.voice_client.play(source, after=after_playing)
            self.status = Status.PLAYING
            self.last_song_url = current_song.url
            
            # Initialize or reset position tracking
            if current_song.url == self.last_song_url:
                self._start_position_tracking()
            else:
                self._start_position_tracking(0)
                
            # Notify listeners
            self._notify_playback_event("play", song=current_song)
            
        except Exception as e:
            logger.error(f"Error playing track: {str(e)}")
            await self.forward(1)
            raise
    
    async def pause(self) -> None:
        """Pause playback"""
        if self.status != Status.PLAYING:
            raise ValueError("Not currently playing")
            
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()
            
        self.status = Status.PAUSED
        self._stop_position_tracking()
        self._notify_playback_event("pause", song=self.get_current())
    
    async def seek(self, position_seconds: int) -> None:
        """Seek to a specific position in the track"""
        if not self.voice_client:
            raise ValueError("Not connected to a voice channel")
            
        current_song = self.get_current()
        if not current_song:
            raise ValueError("No song currently playing")
            
        if current_song.is_live:
            raise ValueError("Cannot seek in a livestream")
            
        if position_seconds > current_song.length:
            raise ValueError("Cannot seek past the end of the song")
            
        real_position = position_seconds + current_song.offset
        
        # Stop current playback
        if self.voice_client.is_playing() or self.voice_client.is_paused():
            self.voice_client.stop()
            
        # Get new source with proper position
        source = await self._get_audio_source(
            current_song, 
            seek_position=real_position,
            duration=current_song.length + current_song.offset
        )
        
        # Set up after callback
        def after_playing(error):
            if error:
                logger.error(f"Error in playback: {error}")
            asyncio.run_coroutine_threadsafe(
                self._handle_song_finished(), 
                asyncio.get_event_loop()
            )
        
        # Play from new position
        self.voice_client.play(source, after=after_playing)
        self.status = Status.PLAYING
        self._start_position_tracking(position_seconds)
        self._notify_playback_event("seek", song=current_song, position=position_seconds)
    
    async def forward_seek(self, seconds: int) -> None:
        """Seek forward by a certain number of seconds"""
        return await self.seek(self.position_in_seconds + seconds)
    
    async def forward(self, skip: int) -> None:
        """Skip forward in the queue"""
        self._stop_position_tracking()
        
        if self.queue_position + skip < len(self.queue):
            old_position = self.queue_position
            self.queue_position += skip
            self.position_in_seconds = 0
            
            # Notify about the skip
            self._notify_playback_event("skip", 
                                       old_position=old_position, 
                                       new_position=self.queue_position)
            
            if self.status != Status.PAUSED:
                await self.play()
        else:
            # Reached end of queue
            if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
                self.voice_client.stop()
                
            self.status = Status.IDLE
                
            # Schedule disconnection if queue is empty
            from ..db.client import get_guild_settings
            
            settings = await get_guild_settings(self.guild_id)
            disconnect_delay = settings.secondsToWaitAfterQueueEmpties
            
            if disconnect_delay > 0:
                async def disconnect_callback():
                    if self.status == Status.IDLE:
                        await self.disconnect()
                
                self.disconnect_timer = asyncio.get_event_loop().call_later(
                    disconnect_delay, 
                    lambda: asyncio.create_task(disconnect_callback())
                )
                
            self._notify_playback_event("queue_end")
    
    async def back(self) -> None:
        """Go back to the previous song"""
        if self.queue_position > 0:
            old_position = self.queue_position
            self.queue_position -= 1
            self.position_in_seconds = 0
            self._stop_position_tracking()
            
            # Notify about going back
            self._notify_playback_event("back", 
                                       old_position=old_position, 
                                       new_position=self.queue_position)
            
            if self.status != Status.PAUSED:
                await self.play()
        else:
            raise ValueError("No songs to go back to")
    
    async def stop(self) -> None:
        """Stop playback, disconnect and clear queue"""
        if not self.voice_client:
            raise ValueError("Not connected")
            
        if self.status != Status.PLAYING:
            raise ValueError("Not currently playing")
            
        await self.disconnect()
        self.queue = []
        self.queue_position = 0
        self._notify_playback_event("stop")
    
    # Private helper methods
    async def _get_audio_source(
        self, 
        song: QueuedSong, 
        seek_position: Optional[int] = None,
        duration: Optional[int] = None
    ) -> disnake.PCMVolumeTransformer:
        """Get an audio source for the given song"""
        import yt_dlp
        
        # Generate cache key
        cache_key = hashlib.md5(song.url.encode()).hexdigest()
        cache_path = await self.file_cache.get_path_for(cache_key)
        
        # Prepare ffmpeg options
        ffmpeg_options = {
            'options': '-vn -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
        }
        
        before_options = []
        
        if seek_position is not None:
            before_options.append(f'-ss {seek_position}')
        
        if duration is not None:
            before_options.append(f'-to {duration}')
            
        if before_options:
            ffmpeg_options['before_options'] = ' '.join(before_options)
        
        # Use cached file if available
        if cache_path:
            source = disnake.FFmpegPCMAudio(cache_path, **ffmpeg_options)
            
            # Apply volume transformer
            volume_transformer = disnake.PCMVolumeTransformer(
                source, 
                volume=self.get_volume() / 100.0
            )
            return volume_transformer
        
        # Handle different sources
        if song.source == MediaSource.HLS:
            # Direct stream for HLS
            source = disnake.FFmpegPCMAudio(song.url, **ffmpeg_options)
        else:
            # YouTube source
            ydl_opts = {
                'format': 'bestaudio/best',
                'quiet': True,
                'no_warnings': True,
                'noplaylist': True,
                'ignoreerrors': True,
            }
            
            loop = asyncio.get_event_loop()
            
            # Extract media info
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await loop.run_in_executor(
                    None, 
                    lambda: ydl.extract_info(
                        f"https://www.youtube.com/watch?v={song.url}", 
                        download=False
                    )
                )
                
                if not info:
                    raise ValueError(f"Could not extract info for {song.url}")
                
                url = info.get('url')
                
                if not url:
                    raise ValueError(f"Could not get stream URL for {song.url}")
                
                # Try to cache if it's not a livestream and not too long and not seeking
                should_cache = (
                    not info.get('is_live', False) and 
                    info.get('duration', 0) < 30 * 60 and
                    seek_position is None
                )
                
                source = disnake.FFmpegPCMAudio(url, **ffmpeg_options)
                
                if should_cache:
                    # We schedule caching asynchronously to not block playback
                    asyncio.create_task(self._cache_song(song, url, cache_key))
        
        # Apply volume transformer
        volume_transformer = disnake.PCMVolumeTransformer(
            source, 
            volume=self.get_volume() / 100.0
        )
        return volume_transformer
    
    async def _cache_song(self, song: QueuedSong, url: str, cache_key: str) -> None:
        """Cache a song for future use"""
        try:
            # Create temp path for download
            tmp_dir = os.path.join(self.file_cache.cache_dir, 'tmp')
            os.makedirs(tmp_dir, exist_ok=True)
            
            tmp_path = os.path.join(tmp_dir, f"{cache_key}.tmp")
            final_path = os.path.join(self.file_cache.cache_dir, cache_key)
            
            # Skip if already cached
            if os.path.exists(final_path):
                return
            
            logger.info(f"Caching song {song.title} to {cache_key}")
            
            # Use ffmpeg to download and convert
            process = await asyncio.create_subprocess_exec(
                'ffmpeg', 
                '-y',                # Overwrite output files
                '-i', url,           # Input URL
                '-c:a', 'libopus',   # Audio codec
                '-vn',               # No video
                '-f', 'opus',        # Output format
                tmp_path,            # Output file
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE
            )
            
            _, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"Error caching song: {stderr.decode()}")
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                return
            
            # Move temporary file to final location
            if os.path.exists(tmp_path):
                shutil.move(tmp_path, final_path)
                file_size = os.path.getsize(final_path)
                
                # Register in database
                await self.file_cache.cache_file(cache_key, final_path)
                
                logger.info(f"Successfully cached song {song.title} ({file_size} bytes)")
                
                # Trigger eviction if we've gone over limit
                await self.file_cache.evict_if_needed()
        except Exception as e:
            logger.error(f"Error caching song {song.title}: {e}")
            # Clean up tmp file if it exists
            if 'tmp_path' in locals() and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception as cleanup_error:
                    logger.error(f"Error cleaning up tmp file: {cleanup_error}")
    
    def _start_position_tracking(self, initial_position: Optional[int] = None) -> None:
        """Start tracking playback position"""
        self._stop_position_tracking()
        
        if initial_position is not None:
            self.position_in_seconds = initial_position
        
        async def update_position():
            try:
                while True:
                    await asyncio.sleep(1)
                    self.position_in_seconds += 1
            except asyncio.CancelledError:
                pass  # Task was cancelled, that's fine
        
        self.position_tracker_task = asyncio.create_task(update_position())
    
    def _stop_position_tracking(self) -> None:
        """Stop tracking playback position"""
        if self.position_tracker_task:
            self.position_tracker_task.cancel()
            self.position_tracker_task = None
    
    def _register_voice_activity_listeners(self, channel: disnake.VoiceChannel) -> None:
        """Register listeners for voice activity to adjust volume"""
        from ..db.client import get_guild_settings
        
        async def setup_voice_listener():
            settings = await get_guild_settings(self.guild_id)
            if not settings.turnDownVolumeWhenPeopleSpeak:
                return
            
            # Store reference to the channel
            self.current_channel = channel
            self.channel_to_speaking_users[channel.id] = set()
            
            # Create speaking event handlers
            if not self.voice_client or not hasattr(self.voice_client, 'ws'):
                return
                
            # This is a hacky way to detect speaking, proper implementation 
            # would use the Discord voice WebSocket API
            @self.voice_client.listen('speaking_start')
            async def on_speaking_start(user_id: int):
                channel_id = self.current_channel.id
                self.channel_to_speaking_users.setdefault(channel_id, set())
                self.channel_to_speaking_users[channel_id].add(user_id)
                
                # Reduce volume when someone is speaking
                if self.channel_to_speaking_users[channel_id]:
                    self.set_volume(settings.turnDownVolumeWhenPeopleSpeakTarget)
            
            @self.voice_client.listen('speaking_stop')
            async def on_speaking_stop(user_id: int):
                channel_id = self.current_channel.id
                if channel_id in self.channel_to_speaking_users:
                    self.channel_to_speaking_users[channel_id].discard(user_id)
                    
                    # Restore volume when nobody is speaking
                    if not self.channel_to_speaking_users[channel_id]:
                        self.set_volume(self.default_volume)
        
        # We need to run this in the event loop
        asyncio.create_task(setup_voice_listener())
    
    async def _handle_song_finished(self) -> None:
        """Handle a song finishing playback"""
        if self.status != Status.PLAYING:
            return
            
        if self.loop_current_song:
            await self.seek(0)
            return
            
        if self.loop_current_queue:
            current_song = self.get_current()
            if current_song:
                self.add(current_song)
                
        await self.forward(1)
        
        # Auto-announce next song if configured
        current = self.get_current()
        if not current:
            return
            
        from ..db.client import get_guild_settings
        from ..utils.embeds import create_playing_embed
        
        settings = await get_guild_settings(self.guild_id)
        
        if settings.autoAnnounceNextSong and self.current_channel:
            embed = create_playing_embed(self)
            try:
                await self.current_channel.send(embed=embed)
            except Exception as e:
                logger.error(f"Failed to auto-announce: {e}")