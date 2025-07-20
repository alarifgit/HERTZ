"""
Queue management commands for HERTZ bot
Handles queue operations like show, clear, shuffle, etc.
"""

import logging
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

from utils.error_handler import require_same_voice_channel

logger = logging.getLogger(__name__)

class QueueCommands(commands.Cog):
    """Queue management commands."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(name="queue", description="Show the current music queue")
    @app_commands.describe(page="Page number to display (default: 1)")
    async def queue(self, interaction: discord.Interaction, page: int = 1):
        """Show the current music queue."""
        player = self.bot.player_manager.get_existing(interaction.guild.id)
        
        if not player:
            embed = discord.Embed(
                title="📄 Queue Empty",
                description="No music in queue.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Get queue tracks with pagination
        tracks_per_page = 10
        start_index = (page - 1) * tracks_per_page
        
        try:
            tracks = await player.queue.get_tracks(start_index, tracks_per_page)
            total_tracks = player.queue.size()
            
            if not tracks and total_tracks == 0:
                embed = discord.Embed(
                    title="📄 Queue Empty",
                    description="No music in queue.",
                    color=0xff6b6b
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            if not tracks:
                embed = discord.Embed(
                    title="❌ Error",
                    description=f"Page {page} not found. Queue has {total_tracks} tracks.",
                    color=0xff6b6b
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Calculate total pages
            total_pages = (total_tracks + tracks_per_page - 1) // tracks_per_page
            
            # Create embed
            embed = discord.Embed(
                title=f"📄 Music Queue - Page {page}/{total_pages}",
                color=0x3498db
            )
            
            # Add currently playing track
            if player.current_track:
                current = player.current_track
                embed.add_field(
                    name="🎵 Now Playing",
                    value=f"**{current['title']}** by {current.get('artist', 'Unknown')}\nRequested by {current.get('requested_by_name', 'Unknown')}",
                    inline=False
                )
            
            # Add queued tracks
            if tracks:
                queue_text = ""
                for i, track in enumerate(tracks):
                    position = start_index + i + 1
                    duration_str = ""
                    if track.get('duration'):
                        duration_str = f" [{track['duration'] // 60}:{track['duration'] % 60:02d}]"
                    
                    queue_text += f"`{position}.` **{track['title']}** by {track.get('artist', 'Unknown')}{duration_str}\n"
                
                embed.add_field(
                    name=f"📋 Up Next ({total_tracks} tracks)",
                    value=queue_text or "No tracks",
                    inline=False
                )
            
            # Add queue stats
            total_duration = player.queue.get_total_duration()
            if total_duration > 0:
                hours = total_duration // 3600
                minutes = (total_duration % 3600) // 60
                duration_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
                embed.add_field(name="⏱️ Total Duration", value=duration_str, inline=True)
            
            embed.add_field(name="📊 Total Tracks", value=str(total_tracks), inline=True)
            
            # Add loop status
            loop_status = []
            if player.loop_current:
                loop_status.append("🔂 Track")
            if player.loop_queue:
                loop_status.append("🔁 Queue")
            
            if loop_status:
                embed.add_field(name="🔄 Loop", value=" & ".join(loop_status), inline=True)
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            logger.error(f"Queue command error: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="Failed to retrieve queue information.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="clear", description="Clear the music queue")
    @app_commands.describe(keep_current="Keep the currently playing track")
    @require_same_voice_channel
    async def clear(self, interaction: discord.Interaction, keep_current: bool = True):
        """Clear the music queue."""
        player = self.bot.player_manager.get_existing(interaction.guild.id)
        
        if not player:
            embed = discord.Embed(
                title="❌ Error",
                description="No active player found.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        queue_size = player.queue.size()
        
        if queue_size == 0:
            embed = discord.Embed(
                title="📄 Queue Already Empty",
                description="The queue is already empty.",
                color=0xffa500
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        await player.queue.clear()
        
        if not keep_current and player.current_track:
            await player.stop()
        
        embed = discord.Embed(
            title="🗑️ Queue Cleared",
            description=f"Removed {queue_size} tracks from the queue.",
            color=0x3498db
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="shuffle", description="Shuffle the music queue")
    @require_same_voice_channel
    async def shuffle(self, interaction: discord.Interaction):
        """Shuffle the music queue."""
        player = self.bot.player_manager.get_existing(interaction.guild.id)
        
        if not player:
            embed = discord.Embed(
                title="❌ Error",
                description="No active player found.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        queue_size = player.queue.size()
        
        if queue_size < 2:
            embed = discord.Embed(
                title="❌ Error",
                description="Need at least 2 tracks in queue to shuffle.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        await player.queue.shuffle()
        
        embed = discord.Embed(
            title="🔀 Queue Shuffled",
            description=f"Shuffled {queue_size} tracks in the queue.",
            color=0x3498db
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="remove", description="Remove a track from the queue")
    @app_commands.describe(position="Position of the track to remove")
    @require_same_voice_channel
    async def remove(self, interaction: discord.Interaction, position: int):
        """Remove a track from the queue by position."""
        player = self.bot.player_manager.get_existing(interaction.guild.id)
        
        if not player:
            embed = discord.Embed(
                title="❌ Error",
                description="No active player found.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if position < 1:
            embed = discord.Embed(
                title="❌ Error",
                description="Position must be 1 or greater.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Convert to 0-based index
        index = position - 1
        
        removed_track = await player.queue.remove(index)
        
        if not removed_track:
            embed = discord.Embed(
                title="❌ Error",
                description=f"No track found at position {position}.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(
            title="🗑️ Track Removed",
            description=f"Removed **{removed_track['title']}** by {removed_track.get('artist', 'Unknown')} from position {position}.",
            color=0x3498db
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="move", description="Move a track to a different position in the queue")
    @app_commands.describe(
        from_position="Current position of the track",
        to_position="New position for the track"
    )
    @require_same_voice_channel
    async def move(self, interaction: discord.Interaction, from_position: int, to_position: int):
        """Move a track to a different position in the queue."""
        player = self.bot.player_manager.get_existing(interaction.guild.id)
        
        if not player:
            embed = discord.Embed(
                title="❌ Error",
                description="No active player found.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if from_position < 1 or to_position < 1:
            embed = discord.Embed(
                title="❌ Error",
                description="Positions must be 1 or greater.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if from_position == to_position:
            embed = discord.Embed(
                title="❌ Error",
                description="Source and destination positions are the same.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Convert to 0-based indices
        from_index = from_position - 1
        to_index = to_position - 1
        
        success = await player.queue.move(from_index, to_index)
        
        if not success:
            embed = discord.Embed(
                title="❌ Error",
                description=f"Failed to move track. Check that positions {from_position} and {to_position} are valid.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        embed = discord.Embed(
            title="📋 Track Moved",
            description=f"Moved track from position {from_position} to position {to_position}.",
            color=0x3498db
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="loop", description="Set loop mode for current track or queue")
    @app_commands.describe(
        mode="Loop mode: 'off', 'track', 'queue'"
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="Off", value="off"),
        app_commands.Choice(name="Track", value="track"),
        app_commands.Choice(name="Queue", value="queue"),
    ])
    @require_same_voice_channel
    async def loop(self, interaction: discord.Interaction, mode: str):
        """Set loop mode for current track or queue."""
        player = self.bot.player_manager.get_existing(interaction.guild.id)
        
        if not player:
            embed = discord.Embed(
                title="❌ Error",
                description="No active player found.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if mode == "off":
            player.set_loop(loop_current=False, loop_queue=False)
            embed = discord.Embed(
                title="🔄 Loop Disabled",
                description="Loop mode turned off.",
                color=0x3498db
            )
        elif mode == "track":
            player.set_loop(loop_current=True, loop_queue=False)
            embed = discord.Embed(
                title="🔂 Track Loop Enabled",
                description="Current track will loop.",
                color=0x3498db
            )
        elif mode == "queue":
            player.set_loop(loop_current=False, loop_queue=True)
            embed = discord.Embed(
                title="🔁 Queue Loop Enabled",
                description="Queue will loop when it reaches the end.",
                color=0x3498db
            )
        
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    """Setup function for the cog."""
    await bot.add_cog(QueueCommands(bot))