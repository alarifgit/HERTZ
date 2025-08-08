"""
Configuration Cog - Bot settings and server configuration
"""
import discord
from discord.ext import commands
from discord import app_commands
import logging
import json
import os
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger('hertz.config')

class Config(commands.Cog):
    """Configuration and settings commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.settings_file = "data/guild_settings.json"
        self.guild_settings = self.load_settings()
    
    def load_settings(self) -> dict:
        """Load guild settings from file"""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {}
    
    def save_settings(self):
        """Save guild settings to file"""
        os.makedirs(os.path.dirname(self.settings_file), exist_ok=True)
        with open(self.settings_file, 'w') as f:
            json.dump(self.guild_settings, f, indent=2)
    
    def get_guild_settings(self, guild_id: int) -> dict:
        """Get settings for a guild"""
        guild_id = str(guild_id)
        if guild_id not in self.guild_settings:
            self.guild_settings[guild_id] = {
                'dj_role': None,
                'prefix': '/',
                'volume': 50,
                'auto_disconnect': True,
                'announce_songs': True
            }
        return self.guild_settings[guild_id]
    
    @app_commands.command(name="settings", description="View current server settings")
    @app_commands.default_permissions(manage_guild=True)
    async def settings(self, interaction: discord.Interaction):
        """Display guild settings"""
        settings = self.get_guild_settings(interaction.guild.id)
        
        embed = discord.Embed(
            title="⚙️ Server Settings",
            color=0x00ff00
        )
        
        # DJ Role
        dj_role = "Not Set"
        if settings['dj_role']:
            role = interaction.guild.get_role(settings['dj_role'])
            if role:
                dj_role = role.mention
        embed.add_field(name="DJ Role", value=dj_role, inline=True)
        
        # Volume
        embed.add_field(name="Default Volume", value=f"{settings['volume']}%", inline=True)
        
        # Auto Disconnect
        embed.add_field(
            name="Auto Disconnect",
            value="✅ Enabled" if settings['auto_disconnect'] else "❌ Disabled",
            inline=True
        )
        
        # Announce Songs
        embed.add_field(
            name="Announce Songs",
            value="✅ Enabled" if settings['announce_songs'] else "❌ Disabled",
            inline=True
        )
        
        embed.set_footer(text=f"Guild ID: {interaction.guild.id}")
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="setdj", description="Set the DJ role")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(role="The role that can use DJ commands")
    async def setdj(self, interaction: discord.Interaction, role: Optional[discord.Role] = None):
        """Set DJ role for the guild"""
        settings = self.get_guild_settings(interaction.guild.id)
        
        if role:
            settings['dj_role'] = role.id
            self.save_settings()
            
            embed = discord.Embed(
                title="✅ DJ Role Set",
                description=f"DJ role set to {role.mention}",
                color=0x00ff00
            )
        else:
            settings['dj_role'] = None
            self.save_settings()
            
            embed = discord.Embed(
                title="✅ DJ Role Removed",
                description="DJ role requirement has been removed",
                color=0x00ff00
            )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="setvolume", description="Set default volume")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(level="Default volume level (0-100)")
    async def setvolume(self, interaction: discord.Interaction, level: int):
        """Set default volume for the guild"""
        if level < 0 or level > 100:
            embed = discord.Embed(
                title="❌ Invalid Volume",
                description="Volume must be between 0 and 100!",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        settings = self.get_guild_settings(interaction.guild.id)
        settings['volume'] = level
        self.save_settings()
        
        embed = discord.Embed(
            title="✅ Default Volume Set",
            description=f"Default volume set to **{level}%**",
            color=0x00ff00
        )
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="autodc", description="Toggle auto-disconnect when alone")
    @app_commands.default_permissions(manage_guild=True)
    async def autodc(self, interaction: discord.Interaction):
        """Toggle auto-disconnect feature"""
        settings = self.get_guild_settings(interaction.guild.id)
        settings['auto_disconnect'] = not settings['auto_disconnect']
        self.save_settings()
        
        status = "enabled" if settings['auto_disconnect'] else "disabled"
        embed = discord.Embed(
            title="✅ Auto-Disconnect Updated",
            description=f"Auto-disconnect is now **{status}**",
            color=0x00ff00
        )
        
        if settings['auto_disconnect']:
            embed.add_field(
                name="Info",
                value="Bot will disconnect after 30 seconds when alone in voice channel",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="announce", description="Toggle song announcements")
    @app_commands.default_permissions(manage_guild=True)
    async def announce(self, interaction: discord.Interaction):
        """Toggle song announcement messages"""
        settings = self.get_guild_settings(interaction.guild.id)
        settings['announce_songs'] = not settings['announce_songs']
        self.save_settings()
        
        status = "enabled" if settings['announce_songs'] else "disabled"
        embed = discord.Embed(
            title="✅ Announcements Updated",
            description=f"Song announcements are now **{status}**",
            color=0x00ff00
        )
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Config(bot))