# hertz/services/add_query_to_queue.py
import asyncio
import logging
import random
from typing import List, Dict, Any, Tuple, Optional

import disnake
from disnake import ApplicationCommandInteraction

from ..services.get_songs import GetSongs
from ..utils.voice import get_member_voice_channel, get_most_popular_voice_channel
from ..utils.embeds import create_playing_embed

logger = logging.getLogger(__name__)

class AddQueryToQueue:
    """Service for adding queries to the queue"""
    
    def __init__(self, bot):
        self.bot = bot
        self.get_songs = GetSongs(self.bot.config)
    
    async def add_to_queue(
        self, 
        query: str,
        add_to_front_of_queue: bool,
        shuffle_additions: bool,
        should_split_chapters: bool,
        skip_current_track: bool,
        interaction: ApplicationCommandInteraction
    ) -> Tuple[List[Dict[str, Any]], str, Optional[disnake.Embed]]:
        """Add songs to queue and return info for response"""
        guild_id = interaction.guild.id
        player = self.bot.player_manager.get_player(guild_id)
        was_playing_song = player.get_current() is not None
        
        # Get target voice channel
        voice_channel = get_member_voice_channel(interaction.author)
        if not voice_channel:
            voice_channel = get_most_popular_voice_channel(interaction.guild)
        
        # Get guild settings
        from ..db.client import get_guild_settings
        settings = await get_guild_settings(str(guild_id))
        
        # Get songs from query
        new_songs, extra_msg = await self.get_songs.get_songs(
            query,
            settings.playlistLimit,
            should_split_chapters
        )
        
        if not new_songs:
            raise ValueError("no songs found")
        
        # Shuffle if requested
        if shuffle_additions and len(new_songs) > 1:
            random.shuffle(new_songs)
        
        # Add songs to queue
        for song in new_songs:
            player.add({
                **song,
                "added_in_channel_id": interaction.channel.id,
                "requested_by": interaction.author.id
            }, immediate=add_to_front_of_queue)
        
        status_msg = ""
        embed = None
        
        # Connect to voice if not connected
        if not player.voice_client:
            await player.connect(voice_channel)
            
            # Resume / start playback
            await player.play()
            
            if was_playing_song:
                status_msg = "resuming playback"
            
            embed = create_playing_embed(player)
        elif player.status == player.Status.IDLE:
            # Player is idle, start playback
            await player.play()
        
        # Skip if requested
        if skip_current_track:
            try:
                await player.forward(1)
            except Exception as e:
                logger.error(f"Error skipping track: {e}")
                raise ValueError("no song to skip to")
        
        # Build response message components
        if status_msg and extra_msg:
            extra_msg = f"{status_msg}, {extra_msg}"
        elif status_msg:
            extra_msg = status_msg
        
        return new_songs, extra_msg, embed
    
    async def get_suggestions(self, query: str) -> List[Dict[str, str]]:
        """Get autocomplete suggestions for a query"""
        # Implement YouTube and Spotify suggestions
        from ..services.youtube import get_youtube_suggestions
        
        suggestions = []
        
        # Get YouTube suggestions
        try:
            youtube_results = await get_youtube_suggestions(query)
            for title in youtube_results[:10]:  # Limit to 10
                suggestions.append({
                    "name": f"YouTube: {title}",
                    "value": title
                })
        except Exception as e:
            logger.error(f"Error getting YouTube suggestions: {e}")
        
        # Get Spotify suggestions if credentials available
        if self.bot.config.SPOTIFY_CLIENT_ID and self.bot.config.SPOTIFY_CLIENT_SECRET:
            from ..services.spotify import get_spotify_suggestions
            try:
                spotify_results = await get_spotify_suggestions(query, self.bot.config)
                for item in spotify_results[:10]:  # Limit to 10
                    icon = "💿" if item["type"] == "album" else "🎵" 
                    suggestions.append({
                        "name": f"Spotify: {icon} {item['name']}",
                        "value": item["uri"]
                    })
            except Exception as e:
                logger.error(f"Error getting Spotify suggestions: {e}")
        
        return suggestions