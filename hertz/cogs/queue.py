# hertz/cogs/queue.py
import logging
from typing import Optional

import disnake
from disnake import ApplicationCommandInteraction
from disnake.ext import commands

from ..utils.embeds import create_queue_embed, create_playing_embed

logger = logging.getLogger(__name__)

class QueueCommands(commands.Cog):
    """Commands for queue management"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.slash_command(
        name="queue",
        description="Show the current queue"
    )
    async def queue(
        self,
        inter: ApplicationCommandInteraction,
        page: int = commands.Param(
            description="Page of queue to show [default: 1]",
            default=1,
            ge=1
        ),
        page_size: int = commands.Param(
            description="Items per page [default: server setting, max: 30]",
            default=None,
            ge=1, 
            le=30
        )
    ):
        """Show the songs currently in the queue"""
        await inter.response.defer()
        
        try:
            guild_id = str(inter.guild.id)
            player = self.bot.player_manager.get_player(inter.guild.id)
            
            # Check if anything is playing
            if not player.get_current():
                await inter.followup.send("🚫 ope: queue is empty")
                return
            
            # Get default page size from settings if not specified
            if page_size is None:
                from ..db.client import get_guild_settings
                settings = await get_guild_settings(guild_id)
                page_size = settings.defaultQueuePageSize
            
            # Create and send embed
            embed = create_queue_embed(player, page, page_size)
            await inter.followup.send(embed=embed)
        
        except ValueError as e:
            await inter.followup.send(f"🚫 ope: {str(e)}")
        except Exception as e:
            logger.error(f"Error in queue command: {e}")
            await inter.followup.send("🚫 ope: an error occurred")
    
    @commands.slash_command(
        name="now-playing",
        description="Show the currently playing song"
    )
    async def now_playing(self, inter: ApplicationCommandInteraction):
        """Show only the currently playing song without the full queue"""
        await inter.response.defer()
        
        player = self.bot.player_manager.get_player(inter.guild.id)
        
        # Check if anything is playing
        if not player.get_current():
            await inter.followup.send("🚫 ope: nothing is currently playing")
            return
        
        # Create and send embed
        embed = create_playing_embed(player)
        await inter.followup.send(embed=embed)
    
    @commands.slash_command(
        name="clear",
        description="Clear all songs in queue except the currently playing song"
    )
    async def clear(self, inter: ApplicationCommandInteraction):
        """Clear the queue but keep the current song"""
        await inter.response.defer()
        
        # Check if user is in voice
        if not inter.author.voice:
            await inter.followup.send("🚫 ope: you need to be in a voice channel")
            return
        
        player = self.bot.player_manager.get_player(inter.guild.id)
        player.clear()
        
        await inter.followup.send("clearer than a field after a fresh harvest")
    
    @commands.slash_command(
        name="remove",
        description="Remove songs from the queue"
    )
    async def remove(
        self,
        inter: ApplicationCommandInteraction,
        position: int = commands.Param(
            description="Position of the song to remove [default: 1]",
            default=1,
            ge=1
        ),
        range: int = commands.Param(
            description="Number of songs to remove [default: 1]",
            default=1,
            ge=1
        )
    ):
        """Remove one or more songs from the queue"""
        await inter.response.defer()
        
        # Check if user is in voice
        if not inter.author.voice:
            await inter.followup.send("🚫 ope: you need to be in a voice channel")
            return
        
        player = self.bot.player_manager.get_player(inter.guild.id)
        
        try:
            player.remove_from_queue(position, range)
            await inter.followup.send(":wastebasket: removed")
        except IndexError:
            await inter.followup.send("🚫 ope: invalid queue position")
        except Exception as e:
            logger.error(f"Error in remove command: {e}")
            await inter.followup.send(f"🚫 ope: {str(e)}")
    
    @commands.slash_command(
        name="move",
        description="Move a song to a different position in the queue"
    )
    async def move(
        self,
        inter: ApplicationCommandInteraction,
        from_pos: int = commands.Param(
            name="from",
            description="Position of the song to move",
            ge=1
        ),
        to_pos: int = commands.Param(
            name="to",
            description="Position to move the song to",
            ge=1
        )
    ):
        """Move a song within the queue"""
        await inter.response.defer()
        
        # Check if user is in voice
        if not inter.author.voice:
            await inter.followup.send("🚫 ope: you need to be in a voice channel")
            return
        
        player = self.bot.player_manager.get_player(inter.guild.id)
        
        try:
            song = player.move(from_pos, to_pos)
            await inter.followup.send(f"moved **{song.title}** to position **{to_pos}**")
        except IndexError:
            await inter.followup.send("🚫 ope: invalid queue position")
        except ValueError as e:
            await inter.followup.send(f"🚫 ope: {str(e)}")
    
    @commands.slash_command(
        name="shuffle",
        description="Shuffle the current queue"
    )
    async def shuffle(self, inter: ApplicationCommandInteraction):
        """Randomly shuffle all upcoming songs in the queue"""
        await inter.response.defer()
        
        # Check if user is in voice
        if not inter.author.voice:
            await inter.followup.send("🚫 ope: you need to be in a voice channel")
            return
        
        player = self.bot.player_manager.get_player(inter.guild.id)
        
        if player.is_queue_empty():
            await inter.followup.send("🚫 ope: not enough songs to shuffle")
            return
        
        player.shuffle()
        await inter.followup.send("shuffled")
    
    @commands.slash_command(
        name="loop-queue",
        description="Toggle looping the entire queue"
    )
    async def loop_queue(self, inter: ApplicationCommandInteraction):
        """Toggle queue looping mode"""
        await inter.response.defer()
        
        # Check if user is in voice
        if not inter.author.voice:
            await inter.followup.send("🚫 ope: you need to be in a voice channel")
            return
        
        player = self.bot.player_manager.get_player(inter.guild.id)
        
        if player.status == player.Status.IDLE:
            await inter.followup.send("🚫 ope: no songs to loop!")
            return
        
        if player.queue_size() < 1:
            await inter.followup.send("🚫 ope: not enough songs to loop a queue!")
            return
        
        # Disable song looping if enabled
        if player.loop_current_song:
            player.loop_current_song = False
        
        # Toggle queue looping
        player.loop_current_queue = not player.loop_current_queue
        
        await inter.followup.send(
            "looped queue :)" if player.loop_current_queue else "stopped looping queue :("
        )