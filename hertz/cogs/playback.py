# hertz/cogs/playback.py
import logging
from typing import Optional

import disnake
from disnake import ApplicationCommandInteraction
from disnake.ext import commands

from ..utils.embeds import create_playing_embed
from ..utils.time import parse_time, parse_duration, pretty_time
from ..utils.error_msg import error_msg
from ..utils.responses import Responses

logger = logging.getLogger(__name__)

class PlaybackCommands(commands.Cog):
    """Commands for controlling playback"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.slash_command(
        name="pause",
        description="Pause the current track"
    )
    async def pause(self, inter: ApplicationCommandInteraction):
        """Pause playback"""
        await inter.response.defer()
        
        # Check if user is in voice
        if not inter.author.voice:
            await inter.followup.send(error_msg("you need to be in a voice channel"))
            return
        
        player = self.bot.player_manager.get_player(inter.guild.id)
        
        try:
            logger.info(f"[COMMAND] {inter.author.display_name} paused playback")
            await player.pause()
            await inter.followup.send(Responses.PAUSED)
        except ValueError as e:
            await inter.followup.send(error_msg(str(e)))
    
    @commands.slash_command(
        name="resume",
        description="Resume playback"
    )
    async def resume(self, inter: ApplicationCommandInteraction):
        """Resume playing after being paused or disconnected"""
        await inter.response.defer()
        
        # Check if user is in voice
        if not inter.author.voice:
            await inter.followup.send(error_msg("you need to be in a voice channel"))
            return
        
        player = self.bot.player_manager.get_player(inter.guild.id)
        
        try:
            # Connect to voice channel if not already connected
            if not player.voice_client and inter.author.voice:
                await player.connect(inter.author.voice.channel)
            
            # If paused or has a current song, resume playback
            if player.status == player.Status.PAUSED or player.get_current():
                # If we have a current song, try to resume from the tracked position
                logger.info(f"[COMMAND] {inter.author.display_name} resumed playback")
                await player.play()
                
                await inter.followup.send(
                    content=Responses.RESUMED,
                    embed=create_playing_embed(player)
                )
            else:
                await inter.followup.send(error_msg("nothing to play"))
        except ValueError as e:
            await inter.followup.send(error_msg(str(e)))
    
    @commands.slash_command(
        name="skip",
        description="Skip the current track"
    )
    async def skip(
        self,
        inter: ApplicationCommandInteraction,
        number: int = commands.Param(
            description="Number of tracks to skip [default: 1]",
            default=1,
            ge=1
        )
    ):
        """Skip one or more songs"""
        await inter.response.defer()
        
        # Check if user is in voice
        if not inter.author.voice:
            await inter.followup.send(error_msg("you need to be in a voice channel"))
            return
        
        player = self.bot.player_manager.get_player(inter.guild.id)
        
        try:
            logger.info(f"[COMMAND] {inter.author.display_name} skipped {number} tracks")
            await player.forward(number)
            
            if player.get_current():
                await inter.followup.send(
                    content=Responses.SKIPPED,
                    embed=create_playing_embed(player)
                )
            else:
                await inter.followup.send("📻 Reached the end of the queue")
        except ValueError as e:
            await inter.followup.send(error_msg(str(e)))
    
    @commands.slash_command(
        name="next",
        description="Skip to the next track (alias for /skip)"
    )
    async def next(self, inter: ApplicationCommandInteraction):
        """Alias for /skip command"""
        # Reuse the skip command with default parameters
        await self.skip(inter, number=1)
    
    @commands.slash_command(
        name="unskip",
        description="Go back to the previous track"
    )
    async def unskip(self, inter: ApplicationCommandInteraction):
        """Go back to the previous song in queue"""
        await inter.response.defer()
        
        # Check if user is in voice
        if not inter.author.voice:
            await inter.followup.send(error_msg("you need to be in a voice channel"))
            return
        
        player = self.bot.player_manager.get_player(inter.guild.id)
        
        try:
            logger.info(f"[COMMAND] {inter.author.display_name} went back to previous track")
            await player.back()
            await inter.followup.send(
                content=Responses.PREVIOUS,
                embed=create_playing_embed(player)
            )
        except ValueError as e:
            await inter.followup.send(error_msg(str(e)))
    
    @commands.slash_command(
        name="seek",
        description="Seek to a position in the current track"
    )
    async def seek(
        self,
        inter: ApplicationCommandInteraction,
        time: str = commands.Param(
            description="Position to seek to (e.g. '1:30', '90s')"
        )
    ):
        """Seek to a specific position in the current song"""
        await inter.response.defer()
        
        # Check if user is in voice
        if not inter.author.voice:
            await inter.followup.send(error_msg("you need to be in a voice channel"))
            return
        
        player = self.bot.player_manager.get_player(inter.guild.id)
        current_song = player.get_current()
        
        if not current_song:
            await inter.followup.send(error_msg("nothing is playing"))
            return
        
        if current_song.is_live:
            await inter.followup.send(error_msg("can't seek in a livestream"))
            return
        
        try:
            # Parse time value (handle different formats)
            if ":" in time:
                # Format like "1:30"
                seek_time = parse_time(time)
            else:
                # Format like "90s" or "1m30s"
                seek_time = parse_duration(time)
            
            if seek_time > current_song.length:
                await inter.followup.send(error_msg("can't seek past the end of the track"))
                return
            
            logger.info(f"[COMMAND] {inter.author.display_name} seeked to {seek_time}s")
            await player.seek(seek_time)
            await inter.followup.send(Responses.SEEKED.format(pretty_time(player.get_position())))
            
        except ValueError as e:
            await inter.followup.send(error_msg(str(e)))
    
    @commands.slash_command(
        name="fseek",
        description="Seek forward in the current track"
    )
    async def fseek(
        self,
        inter: ApplicationCommandInteraction,
        time: str = commands.Param(
            description="Time to seek forward (e.g. '30', '30s', '1m')"
        )
    ):
        """Seek forward by a specific amount of time"""
        await inter.response.defer()
        
        # Check if user is in voice
        if not inter.author.voice:
            await inter.followup.send(error_msg("you need to be in a voice channel"))
            return
        
        player = self.bot.player_manager.get_player(inter.guild.id)
        current_song = player.get_current()
        
        if not current_song:
            await inter.followup.send(error_msg("nothing is playing"))
            return
        
        if current_song.is_live:
            await inter.followup.send(error_msg("can't seek in a livestream"))
            return
        
        try:
            # Parse time value
            if ":" in time:
                forward_time = parse_time(time)
            else:
                forward_time = parse_duration(time)
            
            current_position = player.get_position()
            if current_position + forward_time > current_song.length:
                await inter.followup.send(error_msg("can't seek past the end of the track"))
                return
            
            logger.info(f"[COMMAND] {inter.author.display_name} forward seeked by {forward_time}s")
            await player.forward_seek(forward_time)
            await inter.followup.send(Responses.SEEKED.format(pretty_time(player.get_position())))
            
        except ValueError as e:
            await inter.followup.send(error_msg(str(e)))
    
    @commands.slash_command(
        name="replay",
        description="Restart the current track"
    )
    async def replay(self, inter: ApplicationCommandInteraction):
        """Restart the current song from the beginning"""
        await inter.response.defer()
        
        # Check if user is in voice
        if not inter.author.voice:
            await inter.followup.send(error_msg("you need to be in a voice channel"))
            return
        
        player = self.bot.player_manager.get_player(inter.guild.id)
        current_song = player.get_current()
        
        if not current_song:
            await inter.followup.send(error_msg("nothing is playing"))
            return
        
        if current_song.is_live:
            await inter.followup.send(error_msg("can't replay a livestream"))
            return
        
        try:
            logger.info(f"[COMMAND] {inter.author.display_name} restarted current track")
            await player.seek(0)
            await inter.followup.send(Responses.REPLAYED)
        except ValueError as e:
            await inter.followup.send(error_msg(str(e)))
    
    @commands.slash_command(
        name="loop",
        description="Toggle looping the current track"
    )
    async def loop(self, inter: ApplicationCommandInteraction):
        """Toggle looping the current song"""
        await inter.response.defer()
        
        # Check if user is in voice
        if not inter.author.voice:
            await inter.followup.send(error_msg("you need to be in a voice channel"))
            return
        
        player = self.bot.player_manager.get_player(inter.guild.id)
        
        if player.status == player.Status.IDLE:
            await inter.followup.send(error_msg("no track to loop!"))
            return
        
        # Disable queue looping if enabled
        if player.loop_current_queue:
            player.loop_current_queue = False
        
        # Toggle song looping
        player.loop_current_song = not player.loop_current_song
        
        logger.info(f"[COMMAND] {inter.author.display_name} {'enabled' if player.loop_current_song else 'disabled'} track loop")
        await inter.followup.send(
            Responses.LOOPING if player.loop_current_song else Responses.LOOP_STOPPED
        )
    
    @commands.slash_command(
        name="volume",
        description="Set playback volume"
    )
    async def volume(
        self,
        inter: ApplicationCommandInteraction,
        level: int = commands.Param(
            description="Volume level (0-100)",
            ge=0,
            le=100
        )
    ):
        """Set the volume level"""
        await inter.response.defer()
        
        # Check if user is in voice
        if not inter.author.voice:
            await inter.followup.send(error_msg("you need to be in a voice channel"))
            return
        
        player = self.bot.player_manager.get_player(inter.guild.id)
        
        if not player.get_current():
            await inter.followup.send(error_msg("nothing is playing"))
            return
        
        logger.info(f"[COMMAND] {inter.author.display_name} set volume to {level}%")
        player.set_volume(level)
        await inter.followup.send(Responses.VOLUME_SET.format(level))
    
    @commands.slash_command(
        name="disconnect",
        description="Pause and disconnect from voice channel"
    )
    async def disconnect(self, inter: ApplicationCommandInteraction):
        """Disconnect the bot from the voice channel"""
        await inter.response.defer()
        
        # Check if user is in voice
        if not inter.author.voice:
            await inter.followup.send(error_msg("you need to be in a voice channel"))
            return
        
        player = self.bot.player_manager.get_player(inter.guild.id)
        
        if not player.voice_client:
            await inter.followup.send(error_msg("not connected"))
            return
        
        logger.info(f"[COMMAND] {inter.author.display_name} disconnected bot from voice")
        await player.disconnect()
        await inter.followup.send(Responses.DISCONNECTED)
    
    @commands.slash_command(
        name="stop",
        description="Stop playback, disconnect, and clear all tracks"
    )
    async def stop(self, inter: ApplicationCommandInteraction):
        """Stop playback, disconnect, and clear the queue"""
        await inter.response.defer()
        
        # Check if user is in voice
        if not inter.author.voice:
            await inter.followup.send(error_msg("you need to be in a voice channel"))
            return
        
        player = self.bot.player_manager.get_player(inter.guild.id)
        
        if not player.voice_client:
            await inter.followup.send(error_msg("not connected"))
            return
        
        if player.status != player.Status.PLAYING:
            await inter.followup.send(error_msg("not currently playing"))
            return
        
        logger.info(f"[COMMAND] {inter.author.display_name} stopped playback and cleared queue")
        await player.stop()
        await inter.followup.send(Responses.STOPPED)