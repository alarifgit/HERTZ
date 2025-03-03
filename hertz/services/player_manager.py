# hertz/services/player_manager.py
import logging
from typing import Dict

import disnake

from .player import Player
from .file_cache import FileCacheProvider

logger = logging.getLogger(__name__)

class PlayerManager:
    """Manages Player instances for each guild"""
    
    def __init__(self, file_cache: FileCacheProvider):
        self.file_cache = file_cache
        self.players: Dict[int, Player] = {}
    
    def get_player(self, guild_id: int) -> Player:
        """Get or create a Player instance for a guild"""
        if guild_id not in self.players:
            logger.debug(f"Creating new player for guild {guild_id}")
            self.players[guild_id] = Player(self.file_cache, str(guild_id))
        
        return self.players[guild_id]
    
    def remove_player(self, guild_id: int) -> None:
        """Remove a Player instance for a guild"""
        if guild_id in self.players:
            logger.debug(f"Removing player for guild {guild_id}")
            
            # Ensure disconnection
            player = self.players[guild_id]
            if player.voice_client and player.voice_client.is_connected():
                async def disconnect():
                    try:
                        await player.disconnect()
                    except Exception as e:
                        logger.error(f"Error disconnecting during player removal: {e}")
                
                # Schedule disconnect - can't await here directly
                import asyncio
                asyncio.create_task(disconnect())
            
            # Remove from dictionary
            del self.players[guild_id]