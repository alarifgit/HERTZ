"""
Queue Management Cog - Handle queue display, shuffle, loop modes
"""
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import random
import logging
from typing import Optional, List
from datetime import datetime, timezone

logger = logging.getLogger('hertz.queue')

class QueueView(discord.ui.View):
    """Interactive queue view with pagination"""
    
    def __init__(self, queue_data: List, current_page: int = 0):
        super().__init__(timeout=60)
        self.queue_data = queue_data
        self.current_page = current_page
        self.max_page = (len(queue_data) - 1) // 10
        
        # Update button states
        self.update_buttons()
    
    def update_buttons(self):
        """Update button states based on current page"""
        self.first_page.disabled = self.current_page == 0
        self.prev_page.disabled = self.current_page == 0
        self.next_page.disabled = self.current_page >= self.max_page
        self.last_page.disabled = self.current_page >= self.max_page
    
    def get_embed(self) -> discord.Embed:
        """Get embed for current page"""
        start = self.current_page * 10
        end = min(start + 10, len(self.queue_data))
        
        embed = discord.Embed(
            title="📜 Queue",
            color=0x00ff00
        )
        
        if not self.queue_data:
            embed.description = "Queue is empty! Use `/play` to add songs."
            return embed
        
        description = ""
        for i, track in enumerate(self.queue_data[start:end], start=start+1):
            title = track.get('title', 'Unknown')[:50]
            duration = track.get('duration', 0)
            if duration:
                duration_str = f"{duration // 60}:{duration % 60:02d}"
            else:
                duration_str = "Live"
            
            requester = track.get('requester')
            requester_str = f" - {requester.mention}" if requester else ""
            
            description += f"**{i}.** {title} [{duration_str}]{requester_str}\n"
        
        embed.description = description
        embed.set_footer(text=f"Page {self.current_page + 1}/{self.max_page + 1} • {len(self.queue_data)} tracks")
        
        return embed
    
    @discord.ui.button(label="⏮️", style=discord.ButtonStyle.secondary)
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to first page"""
        self.current_page = 0
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to previous page"""
        self.current_page = max(0, self.current_page - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to next page"""
        self.current_page = min(self.max_page, self.current_page + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)
    
    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.secondary)
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Go to last page"""
        self.current_page = self.max_page
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)


class Queue(commands.Cog):
    """Queue management commands"""
    
    def __init__(self, bot):
        self.bot = bot
    
    def get_player(self, guild_id: int):
        """Get player for guild"""
        music_cog = self.bot.get_cog('Music')
        if music_cog and guild_id in music_cog.players:
            return music_cog.players[guild_id]
        return None
    
    @app_commands.command(name="queue", description="Show the current queue")
    @app_commands.describe(page="Page number to display")
    async def queue(self, interaction: discord.Interaction, page: Optional[int] = 1):
        """Display queue with pagination"""
        player = self.get_player(interaction.guild.id)
        
        if not player:
            embed = discord.Embed(
                title="📜 Queue",
                description="Queue is empty! Use `/play` to add songs.",
                color=0x00ff00
            )
            await interaction.response.send_message(embed=embed)
            return
        
        # Get queue items
        queue_list = []
        temp_queue = []
        
        # Extract items from asyncio.Queue
        while not player.queue.empty():
            try:
                item = player.queue.get_nowait()
                queue_list.append(item)
                temp_queue.append(item)
            except:
                break
        
        # Put items back
        for item in temp_queue:
            await player.queue.put(item)
        
        # Add queue loop items if any
        if player.loop_mode == 'queue' and player.queue_list:
            queue_list.extend(player.queue_list)
        
        # Create view with pagination
        view = QueueView(queue_list, current_page=max(0, page - 1))
        embed = view.get_embed()
        
        # Add currently playing
        if player.current:
            now_playing = f"🎵 **Now Playing:** [{player.current.title}]({player.current.webpage_url})"
            if player.current.duration:
                duration = f"{player.current.duration // 60}:{player.current.duration % 60:02d}"
                now_playing += f" [{duration}]"
            
            embed.add_field(
                name="Current Track",
                value=now_playing,
                inline=False
            )
        
        # Add queue stats
        total_duration = sum(track.get('duration', 0) for track in queue_list if track.get('duration'))
        if total_duration:
            hours = total_duration // 3600
            minutes = (total_duration % 3600) // 60
            duration_str = f"{hours}h {minutes}m" if hours else f"{minutes}m"
            
            embed.add_field(
                name="Queue Duration",
                value=duration_str,
                inline=True
            )
        
        embed.add_field(
            name="Loop Mode",
            value=player.loop_mode.title(),
            inline=True
        )
        
        await interaction.response.send_message(embed=embed, view=view if queue_list else None)
    
    @app_commands.command(name="shuffle", description="Shuffle the queue")
    async def shuffle(self, interaction: discord.Interaction):
        """Shuffle the queue"""
        player = self.get_player(interaction.guild.id)
        
        if not player or player.queue.empty():
            embed = discord.Embed(
                title="❌ Empty Queue",
                description="There are no songs in the queue to shuffle!",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Extract queue items
        queue_items = []
        while not player.queue.empty():
            try:
                queue_items.append(player.queue.get_nowait())
            except:
                break
        
        # Shuffle
        random.shuffle(queue_items)
        
        # Put back
        for item in queue_items:
            await player.queue.put(item)
        
        embed = discord.Embed(
            title="🔀 Shuffled",
            description=f"Shuffled **{len(queue_items)}** tracks in the queue!",
            color=0x00ff00
        )
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="loop", description="Set loop mode")
    @app_commands.describe(mode="Loop mode: off, track, or queue")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Off", value="off"),
        app_commands.Choice(name="Track", value="track"),
        app_commands.Choice(name="Queue", value="queue")
    ])
    async def loop(self, interaction: discord.Interaction, mode: str = "off"):
        """Set loop mode"""
        player = self.get_player(interaction.guild.id)
        
        if not player:
            embed = discord.Embed(
                title="❌ Not Playing",
                description="Nothing is currently playing!",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        player.loop_mode = mode
        
        icons = {
            'off': '➡️',
            'track': '🔂',
            'queue': '🔁'
        }
        
        embed = discord.Embed(
            title=f"{icons[mode]} Loop Mode",
            description=f"Loop mode set to: **{mode.title()}**",
            color=0x00ff00
        )
        
        if mode == 'track':
            embed.add_field(
                name="Info",
                value="The current track will repeat after it ends.",
                inline=False
            )
        elif mode == 'queue':
            embed.add_field(
                name="Info",
                value="The entire queue will repeat after all tracks finish.",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="clear", description="Clear the queue")
    async def clear(self, interaction: discord.Interaction):
        """Clear the queue"""
        player = self.get_player(interaction.guild.id)
        
        if not player:
            embed = discord.Embed(
                title="❌ Empty Queue",
                description="The queue is already empty!",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Count items
        count = 0
        while not player.queue.empty():
            try:
                player.queue.get_nowait()
                count += 1
            except:
                break
        
        # Clear queue loop list
        player.queue_list.clear()
        
        embed = discord.Embed(
            title="🗑️ Queue Cleared",
            description=f"Removed **{count}** tracks from the queue!",
            color=0x00ff00
        )
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="remove", description="Remove a track from the queue")
    @app_commands.describe(position="Position of the track to remove")
    async def remove(self, interaction: discord.Interaction, position: int):
        """Remove track at position"""
        player = self.get_player(interaction.guild.id)
        
        if not player or player.queue.empty():
            embed = discord.Embed(
                title="❌ Empty Queue",
                description="The queue is empty!",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Extract queue items
        queue_items = []
        while not player.queue.empty():
            try:
                queue_items.append(player.queue.get_nowait())
            except:
                break
        
        # Check position
        if position < 1 or position > len(queue_items):
            # Put items back
            for item in queue_items:
                await player.queue.put(item)
            
            embed = discord.Embed(
                title="❌ Invalid Position",
                description=f"Position must be between 1 and {len(queue_items)}!",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Remove track
        removed = queue_items.pop(position - 1)
        
        # Put remaining items back
        for item in queue_items:
            await player.queue.put(item)
        
        embed = discord.Embed(
            title="✅ Track Removed",
            description=f"Removed **{removed.get('title', 'Unknown')}** from position {position}!",
            color=0x00ff00
        )
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="move", description="Move a track in the queue")
    @app_commands.describe(
        from_pos="Current position of the track",
        to_pos="New position for the track"
    )
    async def move(self, interaction: discord.Interaction, from_pos: int, to_pos: int):
        """Move track position in queue"""
        player = self.get_player(interaction.guild.id)
        
        if not player or player.queue.empty():
            embed = discord.Embed(
                title="❌ Empty Queue",
                description="The queue is empty!",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Extract queue items
        queue_items = []
        while not player.queue.empty():
            try:
                queue_items.append(player.queue.get_nowait())
            except:
                break
        
        # Check positions
        if (from_pos < 1 or from_pos > len(queue_items) or 
            to_pos < 1 or to_pos > len(queue_items)):
            # Put items back
            for item in queue_items:
                await player.queue.put(item)
            
            embed = discord.Embed(
                title="❌ Invalid Position",
                description=f"Positions must be between 1 and {len(queue_items)}!",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Move track
        track = queue_items.pop(from_pos - 1)
        queue_items.insert(to_pos - 1, track)
        
        # Put items back
        for item in queue_items:
            await player.queue.put(item)
        
        embed = discord.Embed(
            title="✅ Track Moved",
            description=f"Moved **{track.get('title', 'Unknown')}** from position {from_pos} to {to_pos}!",
            color=0x00ff00
        )
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="nowplaying", description="Show current track info")
    async def nowplaying(self, interaction: discord.Interaction):
        """Show detailed info about current track"""
        player = self.get_player(interaction.guild.id)
        
        if not player or not player.current:
            embed = discord.Embed(
                title="❌ Not Playing",
                description="Nothing is currently playing!",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        current = player.current
        
        # Create detailed embed
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"**[{current.title}]({current.webpage_url})**",
            color=0x00ff00
        )
        
        if current.thumbnail:
            embed.set_thumbnail(url=current.thumbnail)
        
        # Add fields
        if current.artist != 'Unknown Artist':
            embed.add_field(name="Artist", value=current.artist, inline=True)
        
        if current.duration:
            duration = f"{current.duration // 60}:{current.duration % 60:02d}"
            embed.add_field(name="Duration", value=duration, inline=True)
        else:
            embed.add_field(name="Duration", value="Live Stream", inline=True)
        
        embed.add_field(name="Volume", value=f"{int(player.volume * 100)}%", inline=True)
        embed.add_field(name="Loop Mode", value=player.loop_mode.title(), inline=True)
        
        # Queue size
        queue_size = player.queue.qsize()
        embed.add_field(name="Queue Size", value=f"{queue_size} tracks", inline=True)
        
        # Time playing
        time_playing = (datetime.now(datetime.UTC) - current.added_at).seconds
        embed.add_field(
            name="Playing For",
            value=f"{time_playing // 60}:{time_playing % 60:02d}",
            inline=True
        )
        
        if current.requester:
            embed.set_footer(
                text=f"Requested by {current.requester}",
                icon_url=current.requester.avatar.url if current.requester.avatar else None
            )
        
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Queue(bot))