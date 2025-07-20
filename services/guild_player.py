"""
Guild player service for HERTZ bot
Individual music player for each guild, inspired by muse architecture
"""

import asyncio
import logging
import time
from typing import Optional, List, Dict, Any
from enum import Enum
import discord
from discord.ext import commands

from services.music_queue import MusicQueue
from services.audio_source import AudioSource
from database.connection import db_manager
from database.models import PlayHistory, Guild

logger = logging.getLogger(__name__)

class PlayerStatus(Enum):
    """Player status enumeration."""
    IDLE = "idle"
    PLAYING = "playing"
    PAUSED = "paused"
    LOADING = "loading"

class GuildPlayer:
    """Music player for a single guild."""
    
    def __init__(self, guild: discord.Guild, bot: commands.Bot, player_manager):
        self.guild = guild
        self.bot = bot
        self.player_manager = player_manager
        
        # Player state
        self.status = PlayerStatus.IDLE
        self.voice_client: Optional[discord.VoiceClient] = None
        self.current_track: Optional[Dict[str, Any]] = None
        self.queue = MusicQueue(guild.id)
        
        # Audio settings
        self.volume = 50
        self.loop_current = False
        self.loop_queue = False
        
        # Timing
        self.start_time: Optional[float] = None
        self.pause_time: Optional[float] = None
        self.seek_position = 0  # seconds
        
        # Auto-disconnect
        self.last_activity = time.time()
        self.disconnect_timer: Optional[asyncio.Task] = None
        
        # Performance tracking
        self.tracks_played = 0
        self.total_play_time = 0
        
        logger.debug(f"Created guild player for {guild.name} ({guild.id})")
    
    async def connect(self, channel: discord.VoiceChannel) -> bool:
        """Connect to a voice channel."""
        try:
            if self.voice_client and self.voice_client.channel == channel:
                return True
            
            # Disconnect from current channel if connected
            if self.voice_client:
                await self.disconnect()
            
            # Connect to new channel
            self.voice_client = await channel.connect()
            self.last_activity = time.time()
            
            # Load guild settings
            guild_settings = await self.player_manager.get_guild_settings(self.guild.id)
            self.volume = guild_settings.default_volume
            
            logger.info(f"Connected to {channel.name} in {self.guild.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to {channel.name}: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from voice channel."""
        if self.voice_client:
            await self.voice_client.disconnect()
            self.voice_client = None
            
            # Stop current playback
            if self.status == PlayerStatus.PLAYING:
                await self.stop()
            
            self.status = PlayerStatus.IDLE
            logger.info(f"Disconnected from voice in {self.guild.name}")
    
    async def play(self, track: Optional[Dict[str, Any]] = None):
        """Play a track or resume playback."""
        if not self.voice_client:
            raise ValueError("Not connected to a voice channel")
        
        # If specific track provided, add to front of queue
        if track:
            await self.queue.add_to_front(track)
        
        # If already playing, stop current
        if self.status == PlayerStatus.PLAYING:
            self.voice_client.stop()
        
        # Get next track if no current track
        if not self.current_track:
            self.current_track = await self.queue.get_next()
            if not self.current_track:
                self.status = PlayerStatus.IDLE
                await self._schedule_disconnect()
                return
        
        try:
            self.status = PlayerStatus.LOADING
            
            # Create audio source using simplified approach
            audio_source = await AudioSource.create(
                self.current_track,
                volume=self.volume / 100.0,
                seek_position=self.seek_position
            )
            
            # Start playback
            self.voice_client.play(
                audio_source,
                after=lambda error: asyncio.create_task(self._playback_finished(error))
            )
            
            self.status = PlayerStatus.PLAYING
            self.start_time = time.time()
            self.last_activity = time.time()
            self.seek_position = 0
            
            # Cancel disconnect timer
            if self.disconnect_timer:
                self.disconnect_timer.cancel()
                self.disconnect_timer = None
            
            # Log to play history
            await self._add_to_history(self.current_track)
            
            logger.info(f"Now playing: {self.current_track['title']} in {self.guild.name}")
            
        except Exception as e:
            logger.error(f"Failed to play track: {e}")
            self.status = PlayerStatus.IDLE
            self.current_track = None
            await self._schedule_disconnect()
    
    async def pause(self):
        """Pause playback."""
        if self.status == PlayerStatus.PLAYING and self.voice_client:
            self.voice_client.pause()
            self.status = PlayerStatus.PAUSED
            self.pause_time = time.time()
            self.last_activity = time.time()
            
            logger.debug(f"Paused playback in {self.guild.name}")
    
    async def resume(self):
        """Resume playback."""
        if self.status == PlayerStatus.PAUSED and self.voice_client:
            self.voice_client.resume()
            self.status = PlayerStatus.PLAYING
            
            # Adjust start time for pause duration
            if self.pause_time and self.start_time:
                pause_duration = time.time() - self.pause_time
                self.start_time += pause_duration
            
            self.pause_time = None
            self.last_activity = time.time()
            
            logger.debug(f"Resumed playback in {self.guild.name}")
    
    async def stop(self):
        """Stop playback and clear current track."""
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.stop()
        
        self.status = PlayerStatus.IDLE
        self.current_track = None
        self.start_time = None
        self.pause_time = None
        self.seek_position = 0
        self.last_activity = time.time()
        
        await self._schedule_disconnect()
        logger.debug(f"Stopped playback in {self.guild.name}")
    
    async def skip(self, count: int = 1) -> Dict[str, Any]:
        """Skip tracks."""
        skipped_tracks = []
        
        # Skip current track
        if self.current_track:
            skipped_tracks.append(self.current_track)
            if self.voice_client and self.voice_client.is_playing():
                self.voice_client.stop()
        
        # Skip additional tracks from queue
        for _ in range(count - 1):
            next_track = await self.queue.get_next()
            if next_track:
                skipped_tracks.append(next_track)
            else:
                break
        
        # Start next track
        self.current_track = None
        await self.play()
        
        return {
            'skipped_count': len(skipped_tracks),
            'skipped_tracks': skipped_tracks
        }
    
    async def seek(self, position: int):
        """Seek to position in current track."""
        if not self.current_track:
            raise ValueError("No track currently playing")
        
        self.seek_position = position
        
        # Restart playback from new position
        if self.status in [PlayerStatus.PLAYING, PlayerStatus.PAUSED]:
            await self.play()
    
    def set_volume(self, volume: int):
        """Set playback volume (0-100)."""
        self.volume = max(0, min(100, volume))
        
        if self.voice_client and hasattr(self.voice_client.source, 'volume'):
            self.voice_client.source.volume = self.volume / 100.0
        
        logger.debug(f"Set volume to {self.volume}% in {self.guild.name}")
    
    def set_loop(self, loop_current: bool = False, loop_queue: bool = False):
        """Set loop modes."""
        self.loop_current = loop_current
        self.loop_queue = loop_queue
        
        logger.debug(f"Set loop modes - current: {loop_current}, queue: {loop_queue}")
    
    def get_position(self) -> int:
        """Get current position in track (seconds)."""
        if not self.start_time or self.status != PlayerStatus.PLAYING:
            return self.seek_position
        
        return int(time.time() - self.start_time) + self.seek_position
    
    def get_remaining(self) -> Optional[int]:
        """Get remaining time in current track (seconds)."""
        if not self.current_track or not self.current_track.get('duration'):
            return None
        
        position = self.get_position()
        duration = self.current_track['duration']
        
        return max(0, duration - position)
    
    def is_connected(self) -> bool:
        """Check if connected to voice channel."""
        return self.voice_client is not None and self.voice_client.is_connected()
    
    def is_playing(self) -> bool:
        """Check if currently playing."""
        return self.status == PlayerStatus.PLAYING
    
    def is_inactive(self) -> bool:
        """Check if player is inactive (for cleanup)."""
        if self.status == PlayerStatus.PLAYING:
            return False
        
        # Consider inactive if no activity for 10 minutes
        return time.time() - self.last_activity > 600
    
    async def _playback_finished(self, error):
        """Handle playback completion."""
        if error:
            logger.error(f"Playback error in {self.guild.name}: {error}")
        
        # Update statistics
        if self.current_track and self.start_time:
            play_duration = time.time() - self.start_time
            self.tracks_played += 1
            self.total_play_time += play_duration
        
        # Handle loop modes
        if self.loop_current and self.current_track:
            await self.play(self.current_track)
            return
        
        if self.loop_queue and self.current_track:
            await self.queue.add(self.current_track)
        
        # Play next track
        self.current_track = None
        await self.play()
    
    async def _add_to_history(self, track: Dict[str, Any]):
        """Add track to play history."""
        try:
            async with db_manager.get_session() as session:
                history_entry = PlayHistory(
                    guild_id=str(self.guild.id),
                    title=track['title'],
                    artist=track.get('artist'),
                    url=track['url'],
                    thumbnail_url=track.get('thumbnail_url'),
                    duration=track.get('duration'),
                    requested_by_id=track['requested_by_id'],
                    requested_by_name=track['requested_by_name'],
                    source=track['source'],
                    source_id=track.get('source_id')
                )
                
                session.add(history_entry)
                await session.commit()
                
        except Exception as e:
            logger.error(f"Failed to add track to history: {e}")
    
    async def _schedule_disconnect(self):
        """Schedule auto-disconnect if queue is empty."""
        if self.disconnect_timer:
            self.disconnect_timer.cancel()
        
        if await self.queue.is_empty():
            # Get auto-disconnect delay from guild settings
            guild_settings = await self.player_manager.get_guild_settings(self.guild.id)
            
            if guild_settings.auto_disconnect:
                delay = guild_settings.auto_disconnect_delay
                self.disconnect_timer = asyncio.create_task(self._auto_disconnect(delay))
    
    async def _auto_disconnect(self, delay: int):
        """Auto-disconnect after delay."""
        try:
            await asyncio.sleep(delay)
            
            # Check if still inactive
            if await self.queue.is_empty() and self.status == PlayerStatus.IDLE:
                await self.disconnect()
                logger.info(f"Auto-disconnected from {self.guild.name} after {delay}s")
                
        except asyncio.CancelledError:
            pass
    
    async def cleanup(self):
        """Cleanup player resources."""
        if self.disconnect_timer:
            self.disconnect_timer.cancel()
        
        await self.disconnect()
        await self.queue.clear()
        
        logger.debug(f"Cleaned up player for {self.guild.name}")
    
    def get_stats(self) -> dict:
        """Get player statistics."""
        return {
            'guild_id': str(self.guild.id),
            'guild_name': self.guild.name,
            'status': self.status.value,
            'connected': self.is_connected(),
            'current_track': self.current_track,
            'queue_size': self.queue.size(),
            'volume': self.volume,
            'loop_current': self.loop_current,
            'loop_queue': self.loop_queue,
            'tracks_played': self.tracks_played,
            'total_play_time': self.total_play_time,
            'position': self.get_position() if self.current_track else 0,
            'remaining': self.get_remaining()
        }