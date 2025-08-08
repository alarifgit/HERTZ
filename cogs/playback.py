"""
Playback Control Cog - Volume, seek, and other playback controls
"""
import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional

logger = logging.getLogger('hertz.playback')

class Playback(commands.Cog):
    """Playback control commands"""
    
    def __init__(self, bot):
        self.bot = bot
    
    def get_player(self, guild_id: int):
        """Get player for guild"""
        music_cog = self.bot.get_cog('Music')
        if music_cog and guild_id in music_cog.players:
            return music_cog.players[guild_id]
        return None
    
    @app_commands.command(name="volume", description="Set playback volume")
    @app_commands.describe(level="Volume level (0-100)")
    async def volume(self, interaction: discord.Interaction, level: Optional[int] = None):
        """Set or display volume"""
        player = self.get_player(interaction.guild.id)
        
        if not player:
            embed = discord.Embed(
                title="❌ Not Playing",
                description="Nothing is currently playing!",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Display current volume
        if level is None:
            embed = discord.Embed(
                title="🔊 Volume",
                description=f"Current volume: **{int(player.volume * 100)}%**",
                color=0x00ff00
            )
            await interaction.response.send_message(embed=embed)
            return
        
        # Validate level
        if level < 0 or level > 100:
            embed = discord.Embed(
                title="❌ Invalid Volume",
                description="Volume must be between 0 and 100!",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Set volume
        player.volume = level / 100
        
        # Apply to current track if playing
        if player.current:
            player.current.volume = player.volume
        
        # Volume emoji based on level
        if level == 0:
            emoji = "🔇"
        elif level < 30:
            emoji = "🔈"
        elif level < 70:
            emoji = "🔉"
        else:
            emoji = "🔊"
        
        embed = discord.Embed(
            title=f"{emoji} Volume Set",
            description=f"Volume set to **{level}%**",
            color=0x00ff00
        )
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="bassboost", description="Toggle bass boost")
    async def bassboost(self, interaction: discord.Interaction):
        """Toggle bass boost effect"""
        player = self.get_player(interaction.guild.id)
        
        if not player:
            embed = discord.Embed(
                title="❌ Not Playing",
                description="Nothing is currently playing!",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # This would require modifying FFMPEG options
        # For now, just a placeholder
        embed = discord.Embed(
            title="🎵 Bass Boost",
            description="Bass boost feature coming soon!",
            color=0xffff00
        )
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="disconnect", description="Disconnect from voice channel")
    async def disconnect(self, interaction: discord.Interaction):
        """Disconnect bot from voice"""
        if not interaction.guild.voice_client:
            embed = discord.Embed(
                title="❌ Not Connected",
                description="I'm not connected to a voice channel!",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Clean up player
        if interaction.guild.id in self.bot.get_cog('Music').players:
            player = self.bot.get_cog('Music').players[interaction.guild.id]
            
            # Clear queue
            while not player.queue.empty():
                try:
                    player.queue.get_nowait()
                except:
                    break
            
            # Destroy player
            player.destroy()
            del self.bot.get_cog('Music').players[interaction.guild.id]
        
        # Disconnect
        await interaction.guild.voice_client.disconnect()
        
        embed = discord.Embed(
            title="👋 Disconnected",
            description="Disconnected from voice channel!",
            color=0x00ff00
        )
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="seek", description="Seek to a position in the current track")
    @app_commands.describe(position="Position in seconds")
    async def seek(self, interaction: discord.Interaction, position: int):
        """Seek to position (requires track restart with ffmpeg)"""
        player = self.get_player(interaction.guild.id)
        
        if not player or not player.current:
            embed = discord.Embed(
                title="❌ Not Playing",
                description="Nothing is currently playing!",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Validate position
        if player.current.duration and position > player.current.duration:
            embed = discord.Embed(
                title="❌ Invalid Position",
                description=f"Position cannot exceed track duration ({player.current.duration}s)!",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Note: Seeking requires restarting the track with ffmpeg -ss option
        # This is complex to implement properly, so for now just inform the user
        embed = discord.Embed(
            title="⏩ Seek",
            description="Seek functionality is coming soon! For now, use `/skip` to skip tracks.",
            color=0xffff00
        )
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Playback(bot))