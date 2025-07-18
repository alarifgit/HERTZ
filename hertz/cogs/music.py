# hertz/cogs/music.py
import logging
import re
import urllib.parse
from typing import List, Dict, Any, Optional

import disnake
from disnake import ApplicationCommandInteraction
from disnake.ext import commands

from ..utils.voice import get_member_voice_channel, get_most_popular_voice_channel
from ..utils.embeds import create_playing_embed
from ..utils.error_msg import error_msg
from ..utils.responses import Responses

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
            await inter.response.send_message(error_msg("you need to be in a voice channel"), ephemeral=True)
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
                
            # Get songs from query with error handling
            from ..services.get_songs import GetSongs
            get_songs = GetSongs(self.bot.config)
            
            logger.info(f"[COMMAND] Play request from {inter.author.display_name}: {query[:50]}...")
            
            try:
                new_songs, extra_msg = await get_songs.get_songs(
                    query=query.strip(),
                    playlist_limit=settings.playlistLimit,
                    should_split_chapters=split
                )
            except Exception as e:
                logger.error(f"[ERROR] Failed to get songs for query '{query}': {e}")
                # Provide more specific error messages
                if "not found" in str(e).lower() or "no" in str(e).lower():
                    await inter.followup.send(error_msg("no tracks found"), ephemeral=True)
                elif "spotify" in str(e).lower():
                    await inter.followup.send(error_msg("Spotify service temporarily unavailable"), ephemeral=True)
                elif "youtube" in str(e).lower():
                    await inter.followup.send(error_msg("YouTube service temporarily unavailable"), ephemeral=True)
                else:
                    await inter.followup.send(error_msg(f"Error processing request: {str(e)}"), ephemeral=True)
                return
            
            if not new_songs:
                await inter.followup.send(error_msg("no tracks found"), ephemeral=True)
                return
                
            # Shuffle if requested
            if shuffle and len(new_songs) > 1:
                import random
                random.shuffle(new_songs)
                logger.info(f"[COMMAND] Shuffled {len(new_songs)} tracks")
                
            # Add songs to queue
            for song in new_songs:
                player.add({
                    **song,
                    "added_in_channel_id": inter.channel.id,
                    "requested_by": inter.author.id
                }, immediate=immediate)
                
            # Handle playback with improved error handling
            try:
                # Connect to voice if not connected
                if not player.voice_client:
                    await player.connect(voice_channel)
                    
                    # Start playback
                    await player.play()
                    
                    # Send embed with currently playing track
                    embed = create_playing_embed(player)
                    
                    # Build status message
                    status_parts = []
                    if was_playing:
                        status_parts.append("resuming playback")
                    
                    # Add extra message if exists
                    if extra_msg:
                        status_parts.append(extra_msg)
                    
                    # Create content string
                    content = None
                    if status_parts:
                        content = f"📡 {', '.join(status_parts).capitalize()}"
                    
                    await inter.followup.send(
                        content=content,
                        embed=embed,
                        ephemeral=settings.queueAddResponseEphemeral
                    )
                    return
                    
                # If player is idle, start playback
                elif player.status == player.Status.IDLE:
                    await player.play()
                    
                    # Send embed with currently playing track
                    embed = create_playing_embed(player)
                    await inter.followup.send(
                        embed=embed,
                        ephemeral=settings.queueAddResponseEphemeral
                    )
                    return
                    
                # Skip if requested
                if skip:
                    try:
                        await player.forward(1)
                    except Exception as e:
                        logger.error(f"[ERROR] Skip failed: {str(e)}")
                        await inter.followup.send(error_msg("no track to skip to"), ephemeral=True)
                        return
                        
                # Format response based on number of songs added
                first_song = new_songs[0]
                position_str = "front" if immediate else ""
                
                if len(new_songs) == 1:
                    response = Responses.track_added(
                        first_song['title'], 
                        position_str, 
                        extra_msg, 
                        skip
                    )
                else:
                    response = Responses.tracks_added(
                        first_song['title'], 
                        len(new_songs) - 1, 
                        position_str, 
                        extra_msg, 
                        skip
                    )
                    
                await inter.followup.send(
                    response,
                    ephemeral=settings.queueAddResponseEphemeral
                )
                
            except Exception as playback_error:
                logger.error(f"[ERROR] Playback error: {playback_error}")
                
                # Try to provide helpful error message based on the error type
                error_message = "Failed to start playback"
                if "connection" in str(playback_error).lower():
                    error_message = "Connection issue - try again in a moment"
                elif "permission" in str(playback_error).lower():
                    error_message = "Missing voice permissions"
                elif "timeout" in str(playback_error).lower():
                    error_message = "Connection timeout - try again"
                
                # Still add the tracks to queue even if playback failed
                first_song = new_songs[0]
                if len(new_songs) == 1:
                    response = f"❌ {error_message}, but **{first_song['title']}** was added to queue"
                else:
                    response = f"❌ {error_message}, but **{first_song['title']}** and {len(new_songs) - 1} other tracks were added to queue"
                
                await inter.followup.send(response, ephemeral=True)
                
        except Exception as e:
            logger.error(f"[ERROR] Play command error: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            
            # Provide user-friendly error message
            if "permission" in str(e).lower():
                await inter.followup.send(error_msg("Missing permissions to join voice channel"), ephemeral=True)
            elif "connection" in str(e).lower() or "timeout" in str(e).lower():
                await inter.followup.send(error_msg("Connection issue - please try again"), ephemeral=True)
            elif "api" in str(e).lower():
                await inter.followup.send(error_msg("Service temporarily unavailable - try again later"), ephemeral=True)
            else:
                await inter.followup.send(error_msg("An unexpected error occurred"), ephemeral=True)
    
    @play.autocomplete("query")
    async def query_autocomplete(self, inter: ApplicationCommandInteraction, query: str):
        """Provide autocomplete suggestions for queries with better error handling"""
        if not query or len(query.strip()) < 2:
            return []
            
        # Check if query looks like a URL
        try:
            result = urllib.parse.urlparse(query)
            if all([result.scheme, result.netloc]):
                # It's a URL, don't provide autocomplete
                return []
        except Exception:
            pass
        
        # Get suggestions from YouTube with error handling
        try:
            from ..services.youtube import get_youtube_suggestions
            suggestions = await get_youtube_suggestions(query)
        
            # Just return simple strings, not dictionaries
            return suggestions[:25]  # Discord limits to 25 choices
        except Exception as e:
            logger.error(f"[ERROR] Autocomplete error: {str(e)}")
            # Return empty list if suggestions fail
            return []