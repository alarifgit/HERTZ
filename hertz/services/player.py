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
from ..utils.responses import Responses

# Configure logger
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
        self.just_skipped = False  # Flag to track manual skips
        
        # Store the event loop from the main thread
        self.main_loop = asyncio.get_event_loop()
        
        logger.debug(f"[INIT] Player created for guild {guild_id}")
        
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
            logger.debug(f"[QUEUE] Added '{song.title}' to end of queue")
        else:
            # Add as next song
            insert_at = self.queue_position + 1
            self.queue.insert(insert_at, song)
            logger.debug(f"[QUEUE] Added '{song.title}' to position {insert_at}")
    
    def clear(self) -> None:
        """Clear the queue but keep current song"""
        current = self.get_current()
        if current:
            self.queue = [current]
            self.queue_position = 0
            logger.info(f"[QUEUE] Cleared all tracks except current '{current.title}'")
        else:
            self.queue = []
            self.queue_position = 0
            logger.info("[QUEUE] Cleared all tracks (queue was empty)")
    
    def shuffle(self) -> None:
        """Shuffle the queue (excluding current song)"""
        import random
        upcoming = self.get_queue()
        
        if not upcoming:
            logger.debug("[QUEUE] Shuffle requested but queue is empty")
            return
            
        random.shuffle(upcoming)
        self.queue = self.queue[:self.queue_position + 1] + upcoming
        logger.info(f"[QUEUE] Shuffled {len(upcoming)} tracks")
    
    def remove_from_queue(self, index: int, amount: int = 1) -> None:
        """Remove songs from the queue"""
        actual_index = self.queue_position + index
        if 0 <= actual_index < len(self.queue):
            removed = self.queue[actual_index:actual_index + amount]
            del self.queue[actual_index:actual_index + amount]
            logger.info(f"[QUEUE] Removed {amount} tracks starting at position {index}")
        else:
            logger.warning(f"[QUEUE] Failed to remove tracks: Invalid position {index}")
    
    def move(self, from_pos: int, to_pos: int) -> QueuedSong:
        """Move a song in the queue"""
        actual_from = self.queue_position + from_pos
        actual_to = self.queue_position + to_pos
        
        if not (0 <= actual_from < len(self.queue) and 0 <= actual_to < len(self.queue)):
            logger.warning(f"[QUEUE] Failed to move: Position out of bounds {from_pos}->{to_pos}")
            raise ValueError("Position out of bounds")
        
        song = self.queue.pop(actual_from)
        self.queue.insert(actual_to, song)
        logger.info(f"[QUEUE] Moved '{song.title}' from position {from_pos} to {to_pos}")
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
        logger.info(f"[VOLUME] Set to {self.volume}%")
    
    async def connect(self, channel: disnake.VoiceChannel) -> None:
        """Connect to a voice channel"""
        # Get default volume from settings
        from ..db.client import get_guild_settings
        settings = await get_guild_settings(self.guild_id)
        self.default_volume = settings.defaultVolume
        
        # Connect to the voice channel
        if self.voice_client:
            if self.voice_client.channel.id != channel.id:
                logger.info(f"[VOICE] Moving to channel '{channel.name}' ({channel.id})")
                await self.voice_client.move_to(channel)
        else:
            logger.info(f"[VOICE] Connecting to channel '{channel.name}' ({channel.id})")
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
                logger.info("[VOICE] Disconnecting from voice channel")
                await self.voice_client.disconnect(force=True)
            except Exception as e:
                logger.warning(f"[VOICE] Error disconnecting: {e}")
                
            self.voice_client = None
            
        self.status = Status.IDLE
        self._notify_playback_event("disconnect")
    
    async def play(self) -> None:
        """Start or resume playback with proper position restoration"""
        if not self.voice_client:
            raise ValueError("Not connected to a voice channel")
                
        current_song = self.get_current()
        if not current_song:
            raise ValueError("Queue is empty")
                
        # Cancel any pending disconnect
        if self.disconnect_timer:
            self.disconnect_timer.cancel()
            self.disconnect_timer = None
                
        # Determine if we're resuming the same song
        same_song = current_song.url == self.last_song_url
        has_position = self.position_in_seconds > 0
        
        if same_song and has_position:
            current_position = self.position_in_seconds
            logger.info(f"[PLAYBACK] Resuming '{current_song.title}' from position {current_position}s")
            
            # Case 1: Just paused, can directly resume
            if self.status == Status.PAUSED and self.voice_client.is_paused():
                logger.debug("[PLAYBACK] Direct resume from pause")
                self.voice_client.resume()
                self.status = Status.PLAYING
                self._start_position_tracking()
                self._notify_playback_event("resume", song=current_song)
                return
                
            # Case 2: Reconnecting or any other state
            if not current_song.is_live:  # Can't seek in livestreams
                logger.debug(f"[PLAYBACK] Seeking to position {current_position}s after reconnection")
                # Store status temporarily to prevent position reset in seek
                temp_status = self.status
                try:
                    await self.seek(current_position)
                    self.status = Status.PLAYING
                    return
                except Exception as e:
                    logger.error(f"[ERROR] Resuming with seek failed: {e}")
                    # Continue with normal playback as fallback
                    self.status = temp_status
        else:
            # New song playback
            logger.info(f"[PLAYBACK] Starting '{current_song.title}'")
        
        # Normal playback logic for new songs or fallback
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
                
            # Set up after callback with extra error handling
            def after_playing(error):
                if error:
                    logger.error(f"[ERROR] Playback callback error: {error}")
                    # Try to log more detailed information
                    import traceback
                    logger.error(traceback.format_exc())
        
                # Try-except block to handle callback errors
                try:
                    # Queue the coroutine in the main event loop using the stored reference
                    self.main_loop.call_soon_threadsafe(
                        lambda: asyncio.create_task(self._handle_song_finished())
                    )
                except Exception as e:
                    logger.error(f"[ERROR] After-playing callback error: {e}")

            # Make sure any existing playback is stopped properly
            if self.voice_client.is_playing() or self.voice_client.is_paused():
                logger.debug("[PLAYBACK] Stopping existing playback before starting new song")
                self.voice_client.stop()
                # Small delay to ensure cleanup is complete
                await asyncio.sleep(0.2)
                
            # Play the audio
            try:
                self.voice_client.play(source, after=after_playing)
                logger.info(f"[PLAYBACK] Started '{current_song.title}'")
                self.status = Status.PLAYING
                self.last_song_url = current_song.url
                    
                # Initialize or reset position tracking for new song
                if not same_song:
                    self._start_position_tracking(0)
                else:
                    # Continue position tracking for resumed song
                    self._start_position_tracking()
                        
                # Notify listeners
                self._notify_playback_event("play", song=current_song)
            except Exception as e:
                logger.error(f"[ERROR] Critical error in voice_client.play: {e}")
                # Detailed error information
                import traceback
                logger.error(traceback.format_exc())
                raise ValueError(f"Failed to start playback: {e}")
                    
        except Exception as e:
            logger.error(f"[ERROR] Error playing track: {e}")
            # Try to recover by skipping to next song
            await self.forward(1)
            raise ValueError(f"Error playing track: {str(e)}")
    
    async def pause(self) -> None:
        """Pause playback"""
        if self.status != Status.PLAYING:
            raise ValueError("Not currently playing")
            
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()
            
        self.status = Status.PAUSED
        self._stop_position_tracking()
        logger.info("[PLAYBACK] Paused")
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
        logger.info(f"[PLAYBACK] Seeking to {position_seconds}s in '{current_song.title}'")
        
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
                logger.error(f"[ERROR] Playback error after seek: {error}")
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
        current_position = self.position_in_seconds
        target_position = current_position + seconds
        logger.info(f"[PLAYBACK] Forward seeking {seconds}s from {current_position}s to {target_position}s")
        return await self.seek(target_position)
    
    async def forward(self, skip: int) -> None:
        """Skip forward in the queue with improved handling"""
        self._stop_position_tracking()
        
        # Save current loop settings
        was_looping_song = self.loop_current_song
        was_looping_queue = self.loop_current_queue
        
        # Temporarily disable looping to prevent auto-replay
        self.loop_current_song = False 
        
        if self.queue_position + skip < len(self.queue):
            old_position = self.queue_position
            self.queue_position += skip
            self.position_in_seconds = 0
            
            # Set the skip flag - this is important for handling song finishing
            self.just_skipped = True
            
            current_song = self.get_current()
            song_title = current_song.title if current_song else "unknown"
            logger.info(f"[QUEUE] Skipped {skip} tracks to '{song_title}'")
            
            # Notify about the skip
            self._notify_playback_event("skip", 
                                       old_position=old_position, 
                                       new_position=self.queue_position)
            
            # Restore loop queue setting, but not loop song setting (since we skipped)
            self.loop_current_queue = was_looping_queue
            
            if self.status != Status.PAUSED:
                await self.play()
        else:
            # Reached end of queue
            logger.info("[QUEUE] Skip requested but reached end of queue")
            if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
                self.voice_client.stop()
                
            self.status = Status.IDLE
                
            # Schedule disconnection if queue is empty
            from ..db.client import get_guild_settings
            
            settings = await get_guild_settings(self.guild_id)
            disconnect_delay = settings.secondsToWaitAfterQueueEmpties
            
            if disconnect_delay > 0:
                logger.info(f"[VOICE] Scheduling disconnect in {disconnect_delay}s due to empty queue")
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
            
            # Set the skip flag here too as we're manually changing position
            self.just_skipped = True
            
            current_song = self.get_current()
            song_title = current_song.title if current_song else "unknown"
            logger.info(f"[QUEUE] Moved back to previous track '{song_title}'")
            
            # Notify about going back
            self._notify_playback_event("back", 
                                       old_position=old_position, 
                                       new_position=self.queue_position)
            
            if self.status != Status.PAUSED:
                await self.play()
        else:
            logger.warning("[QUEUE] Cannot go back: Already at first track")
            raise ValueError("No songs to go back to")
    
    async def stop(self) -> None:
        """Stop playback, disconnect and clear queue"""
        if not self.voice_client:
            raise ValueError("Not connected")
            
        if self.status != Status.PLAYING:
            raise ValueError("Not currently playing")
            
        logger.info("[PLAYBACK] Stopping playback, disconnecting, and clearing queue")
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
        """Get an audio source for the given song with better error handling"""
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
            logger.debug(f"[CACHE] Using cached file for '{song.title}'")
            try:
                source = disnake.FFmpegPCMAudio(cache_path, **ffmpeg_options)
                
                # Apply volume transformer
                volume_transformer = disnake.PCMVolumeTransformer(
                    source, 
                    volume=self.get_volume() / 100.0
                )
                return volume_transformer
            except Exception as e:
                logger.error(f"[ERROR] Error using cached file: {e}")
                # Fall through to re-download if cache file is invalid
        
        # Handle different sources
        try:
            if song.source == MediaSource.HLS:
                # Direct stream for HLS
                logger.debug(f"[STREAM] Setting up HLS stream for '{song.title}'")
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
                logger.debug(f"[YOUTUBE] Extracting info for video '{song.url}'")
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
                    
                    # Apply volume normalization if loudness data is available
                    volume_adjustment = ""
                    if 'loudnessDb' in info:
                        # Normalize based on YouTube's loudness data
                        loudness_db = -float(info['loudnessDb'])
                        volume_adjustment = f",volume={loudness_db}dB"
                        logger.debug(f"[AUDIO] Applying volume normalization of {loudness_db}dB")
                    
                    # Add volume adjustment to ffmpeg options if needed
                    if volume_adjustment:
                        if 'options' in ffmpeg_options:
                            ffmpeg_options['options'] += f" -af {volume_adjustment}"
                        else:
                            ffmpeg_options['options'] = f"-vn -af {volume_adjustment}"
                    
                    # Try to cache if it's not a livestream and not too long and not seeking
                    should_cache = (
                        not info.get('is_live', False) and 
                        info.get('duration', 0) < 30 * 60 and
                        seek_position is None
                    )
                    
                    logger.debug(f"[AUDIO] Creating audio source")
                    source = disnake.FFmpegPCMAudio(url, **ffmpeg_options)
                    
                    if should_cache:
                        # We schedule caching asynchronously to not block playback
                        # Don't try to cache immediately to avoid race conditions
                        def start_cache_task():
                            asyncio.create_task(self._cache_song(song, url, cache_key))
                        
                        # Delay the cache task slightly to avoid interfering with playback start
                        self.main_loop.call_later(2, start_cache_task)
        except Exception as e:
            logger.error(f"[ERROR] Error in _get_audio_source: {e}")
            raise
            
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
            
            logger.debug(f"[CACHE] Downloading '{song.title}' to cache")
            
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
                logger.error(f"[ERROR] Cache download failed: {stderr.decode()}")
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                return
            
            # Move temporary file to final location
            if os.path.exists(tmp_path):
                # Get file size for database
                file_size = os.path.getsize(tmp_path)
                
                # Move to final location
                shutil.move(tmp_path, final_path)
                
                # Register in database
                await self.file_cache.cache_file(cache_key, final_path)
                
                logger.debug(f"[CACHE] Cached '{song.title}' ({file_size} bytes)")
                
                # Trigger eviction if we've gone over limit
                await self.file_cache.evict_if_needed()
        except Exception as e:
            logger.error(f"[ERROR] Error caching song: {e}")
            # Clean up tmp file if it exists
            if 'tmp_path' in locals() and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception as cleanup_error:
                    logger.error(f"[ERROR] Error cleaning up tmp file: {cleanup_error}")
    
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
        logger.debug(f"[PLAYBACK] Started position tracking at {self.position_in_seconds}s")
    
    def _stop_position_tracking(self) -> None:
        """Stop tracking playback position"""
        if self.position_tracker_task:
            self.position_tracker_task.cancel()
            self.position_tracker_task = None
            logger.debug("[PLAYBACK] Stopped position tracking")
    
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
                    logger.debug(f"[VOICE] Reducing volume to {settings.turnDownVolumeWhenPeopleSpeakTarget}% because someone is speaking")
                    self.set_volume(settings.turnDownVolumeWhenPeopleSpeakTarget)
            
            @self.voice_client.listen('speaking_stop')
            async def on_speaking_stop(user_id: int):
                channel_id = self.current_channel.id
                if channel_id in self.channel_to_speaking_users:
                    self.channel_to_speaking_users[channel_id].discard(user_id)
                    
                    # Restore volume when nobody is speaking
                    if not self.channel_to_speaking_users[channel_id]:
                        logger.debug(f"[VOICE] Restoring volume to {self.default_volume}% as no one is speaking")
                        self.set_volume(self.default_volume)
        
        # We need to run this in the event loop
        asyncio.create_task(setup_voice_listener())
    
    async def _handle_song_finished(self) -> None:
        """Handle a song finishing playback"""
        if self.status != Status.PLAYING:
            return
            
        if self.loop_current_song:
            logger.info("[PLAYBACK] Song finished - Looping current song")
            await self.seek(0)
            return
            
        if self.loop_current_queue:
            current_song = self.get_current()
            if current_song:
                logger.debug("[PLAYBACK] Adding current song to end of queue (queue loop enabled)")
                self.add(current_song)
        
        # Check if this was a manual skip that just finished playing
        if self.just_skipped:
            # If we just manually skipped, don't auto-advance
            # Just reset the flag for next time
            logger.debug("[PLAYBACK] Skipping auto-advancement due to recent manual skip")
            self.just_skipped = False
            
            # Auto-announce only if configured
            await self._auto_announce_if_needed()
        else:
            # Normal case - auto-advance to next song
            logger.debug("[PLAYBACK] Song finished naturally - auto-advancing")
            
            # Check if we have a next song
            next_position = self.queue_position + 1
            has_next_song = next_position < len(self.queue)
            
            if has_next_song:
                logger.info("[QUEUE] Auto-advancing to next track")
                await self.forward(1)
            else:
                # End of queue reached
                logger.info("[QUEUE] Reached end of queue")
                self.status = Status.IDLE
                
                # Schedule auto-disconnect if enabled
                from ..db.client import get_guild_settings
                settings = await get_guild_settings(self.guild_id)
                disconnect_delay = settings.secondsToWaitAfterQueueEmpties
                
                if disconnect_delay > 0:
                    logger.info(f"[VOICE] Scheduling disconnect in {disconnect_delay}s due to empty queue")
                    async def disconnect_callback():
                        if self.status == Status.IDLE:
                            await self.disconnect()
                    
                    self.disconnect_timer = asyncio.get_event_loop().call_later(
                        disconnect_delay, 
                        lambda: asyncio.create_task(disconnect_callback())
                    )
                
                self._notify_playback_event("queue_end")
    
    async def _auto_announce_if_needed(self) -> None:
        """Auto-announce the current song if enabled"""
        current = self.get_current()
        if not current:
            return
            
        from ..db.client import get_guild_settings
        from ..utils.embeds import create_playing_embed
        
        settings = await get_guild_settings(self.guild_id)
        
        if settings.autoAnnounceNextSong and self.current_channel:
            logger.debug(f"[ANNOUNCE] Auto-announcing current track '{current.title}'")
            embed = create_playing_embed(self)
            try:
                await self.current_channel.send(embed=embed)
            except Exception as e:
                logger.error(f"[ERROR] Failed to auto-announce: {e}")