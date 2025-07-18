# hertz/services/player.py
import asyncio
import logging
import enum
import os
import hashlib
import shutil
import subprocess
import time
import json
from typing import Optional, List, Dict, Any, Union, Callable

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

class QueuedSong:
    """Represents a song in the queue with all necessary metadata"""
    
    def __init__(self, **kwargs):
        # Required fields
        self.title = kwargs.get('title', 'Unknown Title')
        self.artist = kwargs.get('artist', 'Unknown Artist')
        self.url = kwargs.get('url', '')
        self.length = kwargs.get('length', 0)
        self.added_in_channel_id = kwargs.get('added_in_channel_id', '')
        self.requested_by = kwargs.get('requested_by', '')
        
        # Optional fields with defaults
        self.offset = kwargs.get('offset', 0)
        self.playlist = kwargs.get('playlist', None)
        self.is_live = kwargs.get('is_live', False)
        self.thumbnail_url = kwargs.get('thumbnail_url', None)
        
        # Handle source conversion
        source = kwargs.get('source', 0)
        if isinstance(source, int):
            self.source = MediaSource(source)
        elif isinstance(source, MediaSource):
            self.source = source
        else:
            self.source = MediaSource.YOUTUBE
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'title': self.title,
            'artist': self.artist,
            'url': self.url,
            'length': self.length,
            'offset': self.offset,
            'playlist': self.playlist,
            'is_live': self.is_live,
            'thumbnail_url': self.thumbnail_url,
            'source': self.source.value,
            'added_in_channel_id': self.added_in_channel_id,
            'requested_by': self.requested_by
        }

class VoiceConnectionManager:
    """Manages voice connection with automatic recovery - similar to muse"""
    
    def __init__(self, player: 'Player'):
        self.player = player
        self.last_connection_attempt = 0
        self.connection_failures = 0
        self.max_failures = 3
        self.reconnect_delay = 5
        self.recovery_task = None
        self.is_recovering = False
        
    async def connect_with_retry(self, channel: disnake.VoiceChannel, max_retries: int = 3) -> bool:
        """Connect to voice channel with retry logic like muse"""
        for attempt in range(max_retries):
            try:
                logger.info(f"[VOICE] Connection attempt {attempt + 1}/{max_retries} to '{channel.name}'")
                
                # Disconnect existing connection if any
                if self.player.voice_client:
                    try:
                        await self.player.voice_client.disconnect(force=True)
                        await asyncio.sleep(1)
                    except Exception as e:
                        logger.warning(f"[VOICE] Error disconnecting old connection: {e}")
                
                # Connect to new channel with timeout
                self.player.voice_client = await channel.connect(
                    timeout=30.0,
                    reconnect=True,
                    self_deaf=True
                )
                
                # Wait to ensure connection is stable
                await asyncio.sleep(2)
                
                if self.player.voice_client.is_connected():
                    logger.info(f"[VOICE] Successfully connected to '{channel.name}'")
                    self.connection_failures = 0
                    self.player.current_channel = channel
                    
                    # Set up event handlers like muse
                    self._setup_voice_events()
                    
                    return True
                else:
                    raise ConnectionError("Voice client not connected after join")
                    
            except Exception as e:
                logger.warning(f"[VOICE] Connection attempt {attempt + 1} failed: {e}")
                self.connection_failures += 1
                
                if attempt < max_retries - 1:
                    delay = (attempt + 1) * 2
                    logger.info(f"[VOICE] Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
        
        logger.error(f"[VOICE] Failed to connect after {max_retries} attempts")
        return False
    
    def _setup_voice_events(self):
        """Set up voice client event handlers"""
        if not self.player.voice_client:
            return
            
        # Remove existing listeners to avoid duplicates
        self.player.voice_client.remove_all_listeners()
    
    async def _handle_disconnect(self):
        """Handle unexpected disconnection like muse does"""
        if self.is_recovering:
            return
            
        logger.warning("[VOICE] Handling unexpected disconnection")
        self.is_recovering = True
        
        try:
            # Cancel any ongoing playback tasks
            self.player._stop_position_tracking()
            
            # Mark as disconnected
            self.player.voice_client = None
            
            # If we have a current song and we're supposed to be playing, try to recover
            if (self.player.get_current() and 
                self.player.status == self.player.Status.PLAYING and 
                self.player.current_channel):
                
                logger.info("[VOICE] Attempting to recover playbook...")
                
                # Try to reconnect
                if await self.connect_with_retry(self.player.current_channel):
                    # Resume playback from current position
                    try:
                        await self.player.play()
                        logger.info("[VOICE] Successfully recovered playback")
                    except Exception as e:
                        logger.error(f"[VOICE] Failed to resume playback after reconnect: {e}")
                        self.player.status = self.player.Status.IDLE
                else:
                    logger.error("[VOICE] Failed to reconnect, setting status to idle")
                    self.player.status = self.player.Status.IDLE
            
        finally:
            self.is_recovering = False

class Player:
    DEFAULT_VOLUME = 100
    
    # Reference the Status enum from the class
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
        
        # Voice connection management
        self.voice_manager = VoiceConnectionManager(self)
        self._connection_health_task = None
        self._last_playback_check = time.time()
        
        # Store the event loop from the main thread
        try:
            self.main_loop = asyncio.get_running_loop()
        except RuntimeError:
            self.main_loop = asyncio.new_event_loop()
        
        # Track state for better debugging
        self._last_queue_change = time.time()
        self._playback_lock = asyncio.Lock()
        
        logger.debug(f"[INIT] Player created for guild {guild_id}")
        
    def add_playbook_event_listener(self, callback: Callable):
        """Add a callback for playback events"""
        self._playbook_event_listeners.append(callback)
        
    def _notify_playbook_event(self, event_type: str, **kwargs):
        """Notify all listeners of a playback event"""
        for callback in self._playbook_event_listeners:
            try:
                asyncio.create_task(callback(event_type, **kwargs))
            except Exception as e:
                logger.error(f"Error in playback event callback: {e}")
    
    def get_current(self) -> Optional[QueuedSong]:
        """Get the currently playing song with bounds checking"""
        if not self.queue:
            return None
        
        # Ensure position is within bounds
        if self.queue_position < 0:
            self.queue_position = 0
        elif self.queue_position >= len(self.queue):
            self.queue_position = len(self.queue) - 1 if self.queue else 0
            
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
        """Add a song to the queue with improved state management like muse"""
        # Convert dict to QueuedSong if necessary
        if isinstance(song, dict):
            if "source" in song and isinstance(song["source"], int):
                song["source"] = MediaSource(song["source"])
            song = QueuedSong(**song)
        
        # Handle empty queue case
        if not self.queue:
            self.queue = [song]
            self.queue_position = 0
            logger.debug(f"[QUEUE] Added '{song.title}' to empty queue")
            self._last_queue_change = time.time()
            return
        
        # Add to queue based on immediate flag and playlist status - like muse logic
        if song.playlist or not immediate:
            # Add to end of queue
            self.queue.append(song)
            logger.debug(f"[QUEUE] Added '{song.title}' to end of queue (position {len(self.queue) - 1})")
        else:
            # Add as next song to be played
            insert_at = min(self.queue_position + 1, len(self.queue))
            self.queue.insert(insert_at, song)
            logger.debug(f"[QUEUE] Added '{song.title}' to front of queue at position {insert_at}")
        
        self._last_queue_change = time.time()
    
    def clear(self) -> None:
        """Clear the queue but keep current song with proper state management"""
        current = self.get_current()
        if current:
            self.queue = [current]
            self.queue_position = 0
            logger.info(f"[QUEUE] Cleared all tracks except current '{current.title}'")
        else:
            self.queue = []
            self.queue_position = 0
            logger.info("[QUEUE] Cleared all tracks (queue was empty)")
        
        self._last_queue_change = time.time()
    
    def shuffle(self) -> None:
        """Shuffle the queue with proper state preservation like muse"""
        if not self.queue:
            logger.debug("[QUEUE] Shuffle requested but queue is empty")
            return
        
        # Get upcoming songs only
        upcoming = self.get_queue()
        
        if len(upcoming) < 2:
            logger.debug("[QUEUE] Shuffle requested but not enough upcoming tracks")
            return
        
        import random
        random.shuffle(upcoming)
        
        # Rebuild queue: current song + shuffled upcoming songs
        current_song = self.get_current()
        if current_song:
            self.queue = [current_song] + upcoming
        else:
            self.queue = upcoming
            
        # Ensure position is still valid
        self.queue_position = 0 if current_song else 0
        
        logger.info(f"[QUEUE] Shuffled {len(upcoming)} upcoming tracks")
        self._last_queue_change = time.time()
    
    def remove_from_queue(self, index: int, amount: int = 1) -> None:
        """Remove songs from the queue with proper bounds checking like muse"""
        if not self.queue or index < 1:
            logger.warning(f"[QUEUE] Invalid remove request: index={index}, queue_size={len(self.queue)}")
            raise IndexError("Invalid queue position")
        
        # Convert 1-based index to 0-based array index
        actual_index = self.queue_position + index
        
        # Bounds checking
        if actual_index >= len(self.queue):
            logger.warning(f"[QUEUE] Remove index out of bounds: {actual_index} >= {len(self.queue)}")
            raise IndexError("Queue position out of bounds")
        
        # Ensure we don't remove more than available
        actual_amount = min(amount, len(self.queue) - actual_index)
        
        # Don't allow removing the currently playing song
        if actual_index <= self.queue_position:
            raise ValueError("Cannot remove currently playing song")
        
        # Remove the songs
        removed_songs = self.queue[actual_index:actual_index + actual_amount]
        del self.queue[actual_index:actual_index + actual_amount]
        
        logger.info(f"[QUEUE] Removed {len(removed_songs)} tracks starting at queue position {index}")
        
        # Update state
        self._last_queue_change = time.time()
        
        # If we removed all remaining songs, update status
        if self.queue_position >= len(self.queue) - 1 and self.status == Status.IDLE:
            self.queue_position = len(self.queue) - 1 if self.queue else 0
    
    def move(self, from_pos: int, to_pos: int) -> QueuedSong:
        """Move a song in the queue with proper validation like muse"""
        if not self.queue or from_pos < 1 or to_pos < 1:
            raise ValueError("Invalid position")
        
        # Convert to actual array indices (skip current song)
        actual_from = self.queue_position + from_pos
        actual_to = self.queue_position + to_pos
        
        # Bounds checking
        queue_end = len(self.queue)
        if actual_from >= queue_end or actual_to >= queue_end:
            raise ValueError("Position out of bounds")
        
        # Can't move the currently playing song
        if actual_from <= self.queue_position or actual_to <= self.queue_position:
            raise ValueError("Cannot move currently playing song")
        
        # Perform the move
        song = self.queue.pop(actual_from)
        
        # Adjust target position if we removed an item before it
        if actual_from < actual_to:
            actual_to -= 1
        
        self.queue.insert(actual_to, song)
        
        logger.info(f"[QUEUE] Moved '{song.title}' from position {from_pos} to {to_pos}")
        self._last_queue_change = time.time()
        
        return song
    
    def get_position(self) -> int:
        """Get current playback position in seconds"""
        return self.position_in_seconds
    
    def get_volume(self) -> int:
        """Get current volume (0-100)"""
        return self.volume if self.volume is not None else self.default_volume
    
    def set_volume(self, level: int) -> None:
        """Set volume level (0-100) like muse"""
        self.volume = max(0, min(100, level))
        if self.voice_client and hasattr(self.voice_client, "source") and self.voice_client.source:
            self.voice_client.source.volume = self.get_volume() / 100.0
        logger.info(f"[VOLUME] Set to {self.volume}%")
    
    async def connect(self, channel: disnake.VoiceChannel) -> None:
        """Connect to a voice channel with improved reliability like muse"""
        # Get default volume from settings
        from ..db.client import get_guild_settings
        settings = await get_guild_settings(self.guild_id)
        self.default_volume = settings.defaultVolume
        
        # Use voice manager for connection
        success = await self.voice_manager.connect_with_retry(channel)
        if not success:
            raise ConnectionError(f"Failed to connect to voice channel '{channel.name}'")
        
        # Start connection health monitoring
        self._start_connection_health_monitor()
        
        # Register voice activity listeners for volume reduction
        self._register_voice_activity_listeners(channel)
    
    def _start_connection_health_monitor(self):
        """Start monitoring connection health like muse"""
        if self._connection_health_task:
            self._connection_health_task.cancel()
        
        async def monitor_connection():
            """Monitor voice connection health"""
            while self.voice_client:
                try:
                    await asyncio.sleep(30)  # Check every 30 seconds
                    
                    if not self.voice_client or not self.voice_client.is_connected():
                        logger.warning("[HEALTH] Voice connection lost during health check")
                        await self.voice_manager._handle_disconnect()
                        break
                    
                    # Check for stuck playback
                    current_time = time.time()
                    if (self.status == Status.PLAYING and 
                        current_time - self._last_playback_check > 60):
                        
                        current_song = self.get_current()
                        if current_song and not current_song.is_live:
                            logger.warning("[HEALTH] Playback appears stuck, attempting recovery")
                            try:
                                # Try to resume from current position
                                await self.seek(self.position_in_seconds)
                            except Exception as e:
                                logger.error(f"[HEALTH] Recovery failed: {e}")
                    
                    self._last_playback_check = current_time
                    
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"[HEALTH] Error in connection monitor: {e}")
                    await asyncio.sleep(5)
        
        self._connection_health_task = asyncio.create_task(monitor_connection())
    
    async def disconnect(self) -> None:
        """Enhanced disconnect with proper cleanup like muse"""
        self._stop_position_tracking()
        
        # Cancel health monitoring
        if self._connection_health_task:
            self._connection_health_task.cancel()
            self._connection_health_task = None
        
        # Cancel disconnect timer
        if self.disconnect_timer:
            self.disconnect_timer.cancel()
            self.disconnect_timer = None
        
        # Stop playback
        if self.voice_client:
            if self.status == Status.PLAYING:
                await self.pause()
            
            self.loop_current_song = False
            
            try:
                logger.info("[VOICE] Disconnecting from voice channel")
                await self.voice_client.disconnect(force=True)
                
                # Wait for disconnect to complete
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.warning(f"[VOICE] Error during disconnect: {e}")
            finally:
                self.voice_client = None
        
        self.status = Status.IDLE
        self.current_channel = None
        self.voice_manager.is_recovering = False
        self._notify_playbook_event("disconnect")
    
    async def play(self) -> None:
        """Enhanced play method with better error recovery like muse"""
        async with self._playback_lock:
            if not self.voice_client:
                raise ValueError("Not connected to a voice channel")
            
            # Check connection health before starting
            if not self.voice_client.is_connected():
                logger.warning("[PLAYBACK] Voice client not connected, attempting recovery")
                if self.current_channel:
                    success = await self.voice_manager.connect_with_retry(self.current_channel)
                    if not success:
                        raise ConnectionError("Failed to recover voice connection")
                else:
                    raise ConnectionError("No channel to reconnect to")
            
            current_song = self.get_current()
            if not current_song:
                raise ValueError("Queue is empty")
            
            # Cancel any pending disconnect
            if self.disconnect_timer:
                self.disconnect_timer.cancel()
                self.disconnect_timer = None
            
            # Enhanced resume logic like muse
            same_song = current_song.url == self.last_song_url
            
            logger.info(f"[PLAYBACK] Starting playback of '{current_song.title}' (same_song: {same_song}, status: {self.status.name})")
            
            # Case 1: Simple resume from pause
            if (same_song and self.status == Status.PAUSED and 
                self.voice_client.is_paused() and not self.voice_client.is_playing()):
                
                logger.info(f"[PLAYBACK] Resuming paused track")
                self.voice_client.resume()
                self.status = Status.PLAYING
                self._start_position_tracking()
                self._last_playback_check = time.time()
                self._notify_playbook_event("resume", song=current_song)
                return
            
            # Case 2: Resume from disconnection with seek
            if (same_song and self.position_in_seconds > 5 and not current_song.is_live):
                logger.info(f"[PLAYBACK] Resuming from position {self.position_in_seconds}s after reconnection")
                try:
                    await self.seek(self.position_in_seconds)
                    return
                except Exception as e:
                    logger.error(f"[ERROR] Seek failed during resume: {e}")
                    # Fall through to normal playback
            
            # Case 3: Fresh playback
            logger.info(f"[PLAYBACK] Starting fresh playback")
            
            try:
                # Get audio source with retries like muse does
                source = await self._get_audio_source_with_retry(
                    current_song,
                    seek_position=current_song.offset if current_song.offset > 0 else None,
                    duration=current_song.length + current_song.offset if not current_song.is_live else None
                )
                
                # Enhanced after callback like muse
                def after_playing(error):
                    self._last_playback_check = time.time()
                    
                    if error:
                        logger.error(f"[ERROR] Playback error: {error}")
                        
                    # Schedule the coroutine in the main event loop
                    try:
                        if self.main_loop.is_running():
                            self.main_loop.call_soon_threadsafe(
                                lambda: asyncio.create_task(self._handle_song_finished())
                            )
                    except Exception as e:
                        logger.error(f"[ERROR] After-playing callback error: {e}")
                
                # Stop any existing playback
                if self.voice_client.is_playing() or self.voice_client.is_paused():
                    self.voice_client.stop()
                    await asyncio.sleep(0.3)
                
                # Start playback
                self.voice_client.play(source, after=after_playing)
                
                # Verify playback started
                await asyncio.sleep(0.5)
                if not self.voice_client.is_playing():
                    raise RuntimeError("Playback failed to start")
                
                self.status = Status.PLAYING
                self.last_song_url = current_song.url
                self._start_position_tracking(0)
                self._last_playback_check = time.time()
                
                logger.info(f"[PLAYBACK] Successfully started '{current_song.title}'")
                self._notify_playbook_event("play", song=current_song)
                
            except Exception as e:
                logger.error(f"[ERROR] Critical error in playback: {e}")
                # Try to recover by skipping to next song like muse
                try:
                    await self.forward(1)
                except Exception:
                    # If we can't skip, set to idle
                    self.status = Status.IDLE
                raise ValueError(f"Failed to start playback: {e}")
    
    async def pause(self) -> None:
        """Pause playback"""
        if self.status != Status.PLAYING:
            raise ValueError("Not currently playing")
            
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()
            
        self.status = Status.PAUSED
        self._stop_position_tracking()
        logger.info("[PLAYBACK] Paused")
        self._notify_playbook_event("pause", song=self.get_current())
    
    async def seek(self, position_seconds: int) -> None:
        """Seek to a specific position in the track like muse"""
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
        source = await self._get_audio_source_with_retry(
            current_song, 
            seek_position=real_position,
            duration=current_song.length + current_song.offset
        )
        
        # Set up after callback
        def after_playing(error):
            if error:
                logger.error(f"[ERROR] Playback error after seek: {error}")
            if self.main_loop.is_running():
                self.main_loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(self._handle_song_finished())
                )
        
        # Play from new position
        self.voice_client.play(source, after=after_playing)
        self.status = Status.PLAYING
        self._start_position_tracking(position_seconds)
        self._notify_playbook_event("seek", song=current_song, position=position_seconds)
    
    async def forward_seek(self, seconds: int) -> None:
        """Seek forward by a certain number of seconds"""
        current_position = self.position_in_seconds
        target_position = current_position + seconds
        logger.info(f"[PLAYBACK] Forward seeking {seconds}s from {current_position}s to {target_position}s")
        return await self.seek(target_position)
    
    async def forward(self, skip: int) -> None:
        """Skip forward in the queue with improved error handling like muse"""
        if skip < 1:
            raise ValueError("Skip amount must be positive")
        
        # Stop position tracking
        self._stop_position_tracking()
        
        # Calculate new position
        new_position = self.queue_position + skip
        
        # Check if we can advance
        if new_position >= len(self.queue):
            logger.info(f"[QUEUE] Skip of {skip} would go past end of queue")
            
            # Stop current playback
            if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
                self.voice_client.stop()
            
            # Handle end of queue
            await self._handle_queue_end()
            return
        
        # Save loop state 
        was_looping_song = self.loop_current_song
        was_looping_queue = self.loop_current_queue
        
        # Temporarily disable song looping for manual skip
        self.loop_current_song = False
        
        # Update position
        old_position = self.queue_position
        self.queue_position = new_position
        self.position_in_seconds = 0
        self._last_queue_change = time.time()
        
        current_song = self.get_current()
        song_title = current_song.title if current_song else "unknown"
        logger.info(f"[QUEUE] Skipped {skip} tracks from position {old_position} to {self.queue_position} ('{song_title}')")
        
        # Restore queue looping (but not song looping since we manually skipped)
        self.loop_current_queue = was_looping_queue
        
        # Notify about the skip
        self._notify_playbook_event("skip", old_position=old_position, new_position=self.queue_position)
        
        # Start playing the new song if not paused
        if self.status != Status.PAUSED:
            await self.play()
    
    async def back(self) -> None:
        """Go back to the previous song with proper validation"""
        if self.queue_position <= 0:
            logger.warning("[QUEUE] Cannot go back: Already at first track")
            raise ValueError("No songs to go back to")
        
        old_position = self.queue_position
        self.queue_position -= 1
        self.position_in_seconds = 0
        self._stop_position_tracking()
        self._last_queue_change = time.time()
        
        current_song = self.get_current()
        song_title = current_song.title if current_song else "unknown"
        logger.info(f"[QUEUE] Moved back from position {old_position} to {self.queue_position} ('{song_title}')")
        
        # Notify about going back
        self._notify_playbook_event("back", old_position=old_position, new_position=self.queue_position)
        
        if self.status != Status.PAUSED:
            await self.play()
    
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
        self._last_queue_change = time.time()
        self._notify_playbook_event("stop")
    
    # Private helper methods
    async def _get_audio_source_with_retry(
        self, 
        song: QueuedSong, 
        seek_position: Optional[int] = None,
        duration: Optional[int] = None,
        max_retries: int = 3
    ) -> disnake.PCMVolumeTransformer:
        """Get audio source with retry logic for connection issues"""
        for attempt in range(max_retries):
            try:
                return await self._get_audio_source(song, seek_position, duration)
            except Exception as e:
                logger.warning(f"[RETRY] Audio source attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)
    
    async def _get_audio_source(
        self, 
        song: QueuedSong, 
        seek_position: Optional[int] = None,
        duration: Optional[int] = None
    ) -> disnake.PCMVolumeTransformer:
        """Get an audio source for the given song - improved to match muse's logic"""
        import yt_dlp
        
        # Generate cache key
        cache_key = hashlib.md5(f"{song.url}_{seek_position or 0}".encode()).hexdigest()
        cache_path = await self.file_cache.get_path_for(cache_key)
        
        # Prepare ffmpeg options with better audio handling like muse
        ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn -filter:a "volume=0.8"'
        }
        
        if seek_position is not None:
            ffmpeg_options['before_options'] += f' -ss {seek_position}'
        
        if duration is not None:
            ffmpeg_options['before_options'] += f' -to {duration}'
        
        # Use cached file if available and valid
        if cache_path and os.path.exists(cache_path):
            try:
                logger.debug(f"[CACHE] Using cached file for '{song.title}'")
                source = disnake.FFmpegPCMAudio(cache_path, **ffmpeg_options)
                return disnake.PCMVolumeTransformer(source, volume=self.get_volume() / 100.0)
            except Exception as e:
                logger.warning(f"[CACHE] Cached file invalid, re-downloading: {e}")
                # Remove invalid cache file
                try:
                    os.remove(cache_path)
                    from ..db.client import remove_file_cache
                    await remove_file_cache(cache_key)
                except Exception:
                    pass
        
        # Handle different sources
        if song.source == MediaSource.HLS:
            logger.debug(f"[STREAM] Setting up HLS stream for '{song.title}'")
            source = disnake.FFmpegPCMAudio(song.url, **ffmpeg_options)
            return disnake.PCMVolumeTransformer(source, volume=self.get_volume() / 100.0)
        
        # YouTube source with improved format selection like muse
        ydl_opts = {
            # Format selection similar to muse's logic
            'format': (
                'bestaudio[ext=webm][acodec=opus]/bestaudio[ext=webm]/bestaudio[ext=m4a]'
                '/bestaudio[container=webm]/bestaudio'
            ),
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'extract_flat': False,
            'writethumbnail': False,
            'writeinfojson': False,
            'ignoreerrors': False,
            'retries': 3,
            'fragment_retries': 3,
            'socket_timeout': 30,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        }
        
        try:
            loop = asyncio.get_event_loop()
            
            # Extract media info
            logger.debug(f"[YOUTUBE] Extracting info for video '{song.url}'")
            
            def extract_info():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(
                        f"https://www.youtube.com/watch?v={song.url}", 
                        download=False
                    )
            
            info = await loop.run_in_executor(None, extract_info)
            
            if not info:
                raise ValueError(f"Could not extract info for {song.url}")
            
            # Get the best audio URL - like muse's format selection
            url = info.get('url')
            if not url:
                # Try to get from requested_formats or formats
                formats = info.get('requested_formats') or info.get('formats', [])
                
                # Filter for audio-only formats like muse does
                audio_formats = []
                for f in formats:
                    if f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                        audio_formats.append(f)
                
                # If no audio-only, get formats with audio
                if not audio_formats:
                    audio_formats = [f for f in formats if f.get('acodec') != 'none']
                
                if audio_formats:
                    # Prefer opus in webm like muse
                    opus_formats = [f for f in audio_formats if f.get('acodec') == 'opus' and f.get('ext') == 'webm']
                    if opus_formats:
                        url = opus_formats[0]['url']
                    else:
                        # Sort by quality and pick best
                        audio_formats.sort(key=lambda x: x.get('abr', 0), reverse=True)
                        url = audio_formats[0]['url']
                else:
                    raise ValueError(f"Could not get stream URL for {song.url}")
            
            logger.debug(f"[AUDIO] Using format: {info.get('ext', 'unknown')} - {info.get('acodec', 'unknown')}")
            
            # Check if we should cache (like muse does)
            should_cache = (
                not info.get('is_live', False) and 
                (info.get('duration') or 0) < 30 * 60 and  # Less than 30 minutes like muse
                seek_position is None and
                not song.is_live
            )
            
            if should_cache:
                logger.debug(f"[CACHE] Will cache '{song.title}' after playback starts")
                # Schedule caching in background (don't await)
                asyncio.create_task(self._cache_song_from_url(song, url, cache_key))
            
            # Create audio source
            source = disnake.FFmpegPCMAudio(url, **ffmpeg_options)
            
            return disnake.PCMVolumeTransformer(source, volume=self.get_volume() / 100.0)
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to get audio source for '{song.title}': {e}")
            raise ValueError(f"Could not get audio for {song.title}: {str(e)}")
    
    async def _cache_song_from_url(self, song: QueuedSong, url: str, cache_key: str) -> None:
        """Cache a song from its stream URL like muse does"""
        try:
            cache_path = os.path.join(self.file_cache.cache_dir, cache_key)
            if os.path.exists(cache_path):
                return  # Already cached
            
            tmp_path = os.path.join(self.file_cache.cache_dir, 'tmp', f"{cache_key}.tmp")
            os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
            
            logger.debug(f"[CACHE] Downloading '{song.title}' to cache")
            
            # Use ffmpeg to download with opus encoding for better compatibility like muse
            cmd = [
                'ffmpeg', '-y',
                '-i', url,
                '-c:a', 'libopus',
                '-b:a', '128k',
                '-vn',
                '-f', 'opus',
                tmp_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE
            )
            
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=300)  # 5 min timeout
            
            if process.returncode == 0 and os.path.exists(tmp_path):
                # Move to final location and register
                shutil.move(tmp_path, cache_path)
                await self.file_cache.cache_file(cache_key, cache_path)
                logger.info(f"[CACHE] Successfully cached '{song.title}'")
            else:
                logger.warning(f"[CACHE] Failed to cache '{song.title}': {stderr.decode() if stderr else 'Unknown error'}")
                
        except asyncio.TimeoutError:
            logger.warning(f"[CACHE] Cache download timeout for '{song.title}'")
        except Exception as e:
            logger.error(f"[ERROR] Error caching song: {e}")
        finally:
            # Clean up tmp file
            try:
                if 'tmp_path' in locals() and os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
    
    def _start_position_tracking(self, initial_position: Optional[int] = None) -> None:
        """Enhanced position tracking with health updates"""
        self._stop_position_tracking()
        
        if initial_position is not None:
            self.position_in_seconds = initial_position
        
        async def update_position():
            try:
                while True:
                    await asyncio.sleep(1)
                    self.position_in_seconds += 1
                    self._last_playback_check = time.time()  # Update health check
            except asyncio.CancelledError:
                pass
        
        self.position_tracker_task = asyncio.create_task(update_position())
        logger.debug(f"[PLAYBACK] Started position tracking at {self.position_in_seconds}s")
    
    def _stop_position_tracking(self) -> None:
        """Stop tracking playback position"""
        if self.position_tracker_task:
            self.position_tracker_task.cancel()
            self.position_tracker_task = None
            logger.debug("[PLAYBACK] Stopped position tracking")
    
    def _register_voice_activity_listeners(self, channel: disnake.VoiceChannel) -> None:
        """Register listeners for voice activity to adjust volume like muse"""
        from ..db.client import get_guild_settings
        
        async def setup_voice_listener():
            settings = await get_guild_settings(self.guild_id)
            if not settings.turnDownVolumeWhenPeopleSpeak:
                return
            
            # Store reference to the channel
            self.current_channel = channel
            self.channel_to_speaking_users[channel.id] = set()
            
            # Note: Proper voice activity detection would require
            # access to Discord's voice WebSocket API which is not
            # directly available in disnake like it is in Discord.js
            
        # Run in event loop
        asyncio.create_task(setup_voice_listener())
    
    async def _handle_song_finished(self) -> None:
        """Handle a song finishing playback - like muse's logic"""
        # Use lock to prevent race conditions
        async with self._playback_lock:
            if self.status != Status.PLAYING:
                logger.debug(f"[PLAYBACK] Song finished but status is {self.status.name}, ignoring")
                return
                
            current_song = self.get_current()
            if not current_song:
                logger.warning("[PLAYBACK] Song finished but no current song found")
                return
                
            logger.debug(f"[PLAYBACK] Song finished: '{current_song.title}'")
                
            # Handle looping current song like muse
            if self.loop_current_song:
                logger.info("[PLAYBACK] Song finished - Looping current song")
                await self.seek(0)
                return
                
            # Handle looping queue - add current song to end like muse
            if self.loop_current_queue:
                logger.debug("[PLAYBACK] Adding current song to end of queue (queue loop enabled)")
                self.add(current_song)
            
            # Check if we have a next song
            next_position = self.queue_position + 1
            has_next_song = next_position < len(self.queue)
            
            if has_next_song:
                logger.info("[QUEUE] Auto-advancing to next track")
                # Move to next song
                self.queue_position = next_position
                self.position_in_seconds = 0
                self._last_queue_change = time.time()
                
                # Start playing next song
                await self.play()
                
                # Auto-announce if configured like muse
                await self._auto_announce_if_needed()
            else:
                # End of queue reached
                await self._handle_queue_end()
    
    async def _handle_queue_end(self) -> None:
        """Handle reaching the end of the queue like muse"""
        logger.info("[QUEUE] Reached end of queue")
        self.status = Status.IDLE
        
        # Reset queue state completely like muse
        self.queue_position = 0
        self.position_in_seconds = 0
        self.last_song_url = ""
        self._stop_position_tracking()
        
        # Clear the queue completely when it's finished like muse
        self.queue = []
        self._last_queue_change = time.time()
            
        # Schedule auto-disconnect if enabled like muse
        from ..db.client import get_guild_settings
        settings = await get_guild_settings(self.guild_id)
        disconnect_delay = settings.secondsToWaitAfterQueueEmpties
        
        if disconnect_delay > 0:
            logger.info(f"[VOICE] Scheduling disconnect in {disconnect_delay}s due to empty queue")
            
            async def disconnect_callback():
                if self.status == Status.IDLE:
                    await self.disconnect()
            
            # Use asyncio.call_later instead of threading timer like muse
            if hasattr(self.main_loop, 'call_later'):
                self.disconnect_timer = self.main_loop.call_later(
                    disconnect_delay, 
                    lambda: asyncio.create_task(disconnect_callback())
                )
            else:
                # Fallback
                async def delayed_disconnect():
                    await asyncio.sleep(disconnect_delay)
                    await disconnect_callback()
                
                self.disconnect_timer = asyncio.create_task(delayed_disconnect())
            
        self._notify_playbook_event("queue_end")
    
    async def _auto_announce_if_needed(self) -> None:
        """Auto-announce the current song if enabled like muse"""
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