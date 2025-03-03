# hertz/cogs/music.py
import logging
import re
from typing import List, Dict, Any, Optional

import disnake
from disnake import ApplicationCommandInteraction
from disnake.ext import commands

from ..utils.voice import get_member_voice_channel, get_most_popular_voice_channel
from ..utils.embeds import create_playing_embed

logger = logging.getLogger(__name__)

class MusicCommands(commands.Cog):
    """Commands for playing music"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.slash_command(
        name="play",
        description="Play music from YouTube, Spotify, or a direct URL"
    )
    async def play(
        self, 
        inter: ApplicationCommandInteraction,
        query: str = commands.Param(description="YouTube URL, Spotify URL, or search query"),
        immediate: bool = commands.Param(
            description="Add track to the front of the queue", 
            default=False
        ),
        shuffle: bool = commands.Param(
            description="Shuffle playlist if adding multiple tracks", 
            default=False
        ),
        split: bool = commands.Param(
            description="Split track into chapters if available", 
            default=False
        ),
        skip: bool = commands.Param(
            description="Skip the currently playing track", 
            default=False
        )
    ):
        """Play a song or playlist from various sources"""
        # Check if user is in a voice channel
        if not inter.author.voice:
            await inter.response.send_message("🚫 ope: you need to be in a voice channel", ephemeral=True)
            return
        
        # Defer response to allow time for processing
        await inter.response.defer()
        
        try:
            # Get guild settings
            from ..db.client import get_guild_settings
            settings = await get_guild_settings(str(inter.guild.id))
            
            # Get player
            player = self.bot.player_manager.get_player(inter.guild.id)
            was_playing = player.get_current() is not None
            
            # Get voice channel
            voice_channel = get_member_voice_channel(inter.author)
            if not voice_channel:
                voice_channel = get_most_popular_voice_channel(inter.guild)
                
            # Get songs from query
            from ..services.get_songs import GetSongs
            get_songs = GetSongs(self.bot.config)
            
            new_songs, extra_msg = await get_songs.get_songs(
                query=query.strip(),
                playlist_limit=settings.playlistLimit,
                should_split_chapters=split
            )
            
            if not new_songs:
                await inter.followup.send("🚫 ope: no songs found", ephemeral=True)
                return
                
            # Shuffle if requested
            if shuffle and len(new_songs) > 1:
                import random
                random.shuffle(new_songs)
                
            # Add songs to queue
            for song in new_songs:
                player.add({
                    **song,
                    "added_in_channel_id": inter.channel.id,
                    "requested_by": inter.author.id
                }, immediate=immediate)
                
            # Connect to voice if not connected
            if not player.voice_client:
                await player.connect(voice_channel)
                
                # Start playback
                await player.play()
                
                status_msg = "resuming playback" if was_playing else ""
                
                # Include embed with current playing song
                embed = create_playing_embed(player)
                await inter.followup.send(
                    content=status_msg, 
                    embed=embed,
                    ephemeral=settings.queueAddResponseEphemeral
                )
                return
                
            # If player is idle, start playback
            if player.status == player.Status.IDLE:
                await player.play()
                
            # Skip if requested
            if skip:
                try:
                    await player.forward(1)
                except Exception as e:
                    logger.error(f"Error skipping: {str(e)}")
                    await inter.followup.send("🚫 ope: no song to skip to", ephemeral=True)
                    return
                    
            # Build response message
            status_msg = ""
            if extra_msg:
                if status_msg:
                    extra_msg = f"{status_msg}, {extra_msg}"
                else:
                    extra_msg = f"({extra_msg})"
            elif status_msg:
                extra_msg = f"({status_msg})"
            else:
                extra_msg = ""
                
            # Format response based on number of songs added
            first_song = new_songs[0]
            if len(new_songs) == 1:
                await inter.followup.send(
                    f"u betcha, **{first_song['title']}** added to the{' front of the' if immediate else ''} queue{' and current track skipped' if skip else ''} {extra_msg}",
                    ephemeral=settings.queueAddResponseEphemeral
                )
            else:
                await inter.followup.send(
                    f"u betcha, **{first_song['title']}** and {len(new_songs) - 1} other songs were added to the queue{' and current track skipped' if skip else ''} {extra_msg}",
                    ephemeral=settings.queueAddResponseEphemeral
                )
                
        except Exception as e:
            logger.error(f"Error in play command: {str(e)}")
            await inter.followup.send(f"🚫 ope: {str(e)}", ephemeral=True)
    
    @play.autocomplete("query")
    async def query_autocomplete(self, inter: ApplicationCommandInteraction, query: str):
        """Provide autocomplete suggestions for queries"""
        if not query or len(query.strip()) < 2:
            return []
            
        # Check if query looks like a URL
        if re.match(r'^\w+://', query):
            # It's a URL, don't provide autocomplete
            return []
            
        # Get suggestions from YouTube
        try:
            from ..services.youtube import get_youtube_suggestions
            suggestions = await get_youtube_suggestions(query)
        
            # Just return simple strings, not dictionaries
            return suggestions[:25]  # Discord limits to 25 choices
        except Exception as e:
            logger.error(f"Error in autocomplete: {str(e)}")
            return []