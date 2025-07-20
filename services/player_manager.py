"""
Player manager service for HERTZ bot
Manages music players for each guild, following muse architecture patterns
"""

import asyncio
import logging
from typing import Dict, Optional
import discord
from discord.ext import commands

from services.guild_player import GuildPlayer
from database.connection import db_manager
from database.models import Guild

logger = logging.getLogger(__name__)

class PlayerManager:
    """Manages music players for all guilds."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players: Dict[str, GuildPlayer] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        
        logger.info("Player manager initialized")
    
    def get(self, guild_id: str) -> GuildPlayer:
        """Get or create a player for a guild."""
        guild_id = str(guild_id)
        
        if guild_id not in self.players:
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                raise ValueError(f"Guild {guild_id} not found")
            
            self.players[guild_id] = GuildPlayer(
                guild=guild,
                bot=self.bot,
                player_manager=self
            )
            
            logger.debug(f"Created new player for guild {guild_id}")
        
        return self.players[guild_id]
    
    def get_existing(self, guild_id: str) -> Optional[GuildPlayer]:
        """Get existing player for a guild (don't create new)."""
        return self.players.get(str(guild_id))
    
    async def remove(self, guild_id: str):
        """Remove and cleanup a guild player."""
        guild_id = str(guild_id)
        
        if guild_id in self.players:
            player = self.players[guild_id]
            await player.cleanup()
            del self.players[guild_id]
            
            logger.debug(f"Removed player for guild {guild_id}")
    
    async def cleanup_inactive_players(self):
        """Clean up inactive players to save memory."""
        to_remove = []
        
        for guild_id, player in self.players.items():
            if player.is_inactive():
                to_remove.append(guild_id)
        
        for guild_id in to_remove:
            await self.remove(guild_id)
        
        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} inactive players")
    
    async def get_guild_settings(self, guild_id: str) -> Guild:
        """Get or create guild settings from database."""
        guild_id = str(guild_id)
        
        async with db_manager.get_session() as session:
            # Try to get existing guild
            result = await session.get(Guild, guild_id)
            
            if result:
                return result
            
            # Create new guild settings
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                raise ValueError(f"Guild {guild_id} not found")
            
            new_guild = Guild(
                id=guild_id,
                name=guild.name
            )
            
            session.add(new_guild)
            await session.commit()
            await session.refresh(new_guild)
            
            logger.info(f"Created new guild settings for {guild.name} ({guild_id})")
            return new_guild
    
    async def update_guild_settings(self, guild_id: str, **settings):
        """Update guild settings."""
        guild_id = str(guild_id)
        
        async with db_manager.get_session() as session:
            guild = await session.get(Guild, guild_id)
            if not guild:
                raise ValueError(f"Guild {guild_id} not found in database")
            
            # Update settings
            for key, value in settings.items():
                if hasattr(guild, key):
                    setattr(guild, key, value)
            
            await session.commit()
            logger.debug(f"Updated settings for guild {guild_id}: {settings}")
    
    def get_all_players(self) -> Dict[str, GuildPlayer]:
        """Get all active players."""
        return self.players.copy()
    
    def get_player_count(self) -> int:
        """Get count of active players."""
        return len(self.players)
    
    def get_playing_count(self) -> int:
        """Get count of players currently playing."""
        return sum(1 for player in self.players.values() if player.is_playing())
    
    async def start_cleanup_task(self):
        """Start background cleanup task."""
        if self._cleanup_task and not self._cleanup_task.done():
            return
        
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Started player cleanup task")
    
    async def stop_cleanup_task(self):
        """Stop background cleanup task."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Stopped player cleanup task")
    
    async def _cleanup_loop(self):
        """Background cleanup loop."""
        while True:
            try:
                await asyncio.sleep(300)  # Clean up every 5 minutes
                await self.cleanup_inactive_players()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(60)  # Wait before retrying
    
    async def shutdown(self):
        """Shutdown all players and cleanup."""
        logger.info("Shutting down player manager...")
        
        # Stop cleanup task
        await self.stop_cleanup_task()
        
        # Cleanup all players
        tasks = []
        for guild_id in list(self.players.keys()):
            tasks.append(self.remove(guild_id))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        logger.info("Player manager shutdown complete")
    
    def get_stats(self) -> dict:
        """Get player manager statistics."""
        total_players = len(self.players)
        playing_players = sum(1 for p in self.players.values() if p.is_playing())
        connected_players = sum(1 for p in self.players.values() if p.is_connected())
        
        total_queue_size = sum(p.queue.size() for p in self.players.values())
        
        return {
            'total_players': total_players,
            'playing_players': playing_players,
            'connected_players': connected_players,
            'total_queue_size': total_queue_size,
            'average_queue_size': total_queue_size / max(total_players, 1)
        }