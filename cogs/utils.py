"""
Utility Cog - Help, stats, and other utility commands
"""
import discord
from discord.ext import commands
from discord import app_commands
import logging
import platform
import psutil
from datetime import datetime
from typing import Optional

logger = logging.getLogger('hertz.utils')

class Utils(commands.Cog):
    """Utility commands"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="help", description="Show help information")
    @app_commands.describe(command="Specific command to get help for")
    async def help(self, interaction: discord.Interaction, command: Optional[str] = None):
        """Display help information"""
        
        if command:
            # Show specific command help
            cmd = self.bot.tree.get_command(command)
            if not cmd:
                embed = discord.Embed(
                    title="❌ Command Not Found",
                    description=f"Command `{command}` does not exist!",
                    color=0xff0000
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            embed = discord.Embed(
                title=f"Help: /{cmd.name}",
                description=cmd.description or "No description available",
                color=0x00ff00
            )
            
            # Add parameters
            if cmd.parameters:
                params = []
                for param in cmd.parameters:
                    required = "Required" if param.required else "Optional"
                    params.append(f"**{param.name}** ({required}): {param.description or 'No description'}")
                
                embed.add_field(
                    name="Parameters",
                    value="\n".join(params),
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed)
            return
        
        # Show general help
        embed = discord.Embed(
            title="🎵 Hertz Music Bot - Help",
            description="A feature-rich music bot for Discord with YouTube and Spotify support!",
            color=0x00ff00
        )
        
        # Music commands
        music_cmds = [
            "`/play` - Play a song or playlist",
            "`/skip` - Skip the current song",
            "`/pause` - Pause playback",
            "`/resume` - Resume playback",
            "`/stop` - Stop playback and clear queue",
            "`/disconnect` - Disconnect from voice"
        ]
        embed.add_field(
            name="🎵 Music",
            value="\n".join(music_cmds),
            inline=False
        )
        
        # Queue commands
        queue_cmds = [
            "`/queue` - Show the queue",
            "`/shuffle` - Shuffle the queue",
            "`/loop` - Set loop mode",
            "`/clear` - Clear the queue",
            "`/remove` - Remove a track",
            "`/move` - Move a track",
            "`/nowplaying` - Show current track"
        ]
        embed.add_field(
            name="📜 Queue",
            value="\n".join(queue_cmds),
            inline=False
        )
        
        # Control commands
        control_cmds = [
            "`/volume` - Set volume",
            "`/seek` - Seek to position",
            "`/bassboost` - Toggle bass boost"
        ]
        embed.add_field(
            name="🎛️ Controls",
            value="\n".join(control_cmds),
            inline=False
        )
        
        # Config commands
        config_cmds = [
            "`/settings` - View server settings",
            "`/setdj` - Set DJ role",
            "`/setvolume` - Set default volume",
            "`/autodc` - Toggle auto-disconnect",
            "`/announce` - Toggle announcements"
        ]
        embed.add_field(
            name="⚙️ Configuration",
            value="\n".join(config_cmds),
            inline=False
        )
        
        # Utility commands
        util_cmds = [
            "`/help` - Show this help",
            "`/stats` - Show bot statistics",
            "`/ping` - Check bot latency",
            "`/invite` - Get bot invite link"
        ]
        embed.add_field(
            name="🔧 Utility",
            value="\n".join(util_cmds),
            inline=False
        )
        
        embed.set_footer(text="Use /help <command> for detailed command help")
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="stats", description="Show bot statistics")
    async def stats(self, interaction: discord.Interaction):
        """Display bot statistics"""
        
        # Calculate uptime
        uptime = datetime.utcnow() - self.bot.start_time
        hours, remainder = divmod(int(uptime.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)
        
        if days:
            uptime_str = f"{days}d {hours}h {minutes}m"
        else:
            uptime_str = f"{hours}h {minutes}m {seconds}s"
        
        # Get memory usage
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        
        # Count voice connections
        voice_connections = len(self.bot.voice_clients)
        
        # Count active players
        music_cog = self.bot.get_cog('Music')
        active_players = len(music_cog.players) if music_cog else 0
        
        embed = discord.Embed(
            title="📊 Bot Statistics",
            color=0x00ff00
        )
        
        # Bot info
        embed.add_field(
            name="Bot Info",
            value=f"**Version:** {self.bot.version}\n"
                  f"**Uptime:** {uptime_str}\n"
                  f"**Latency:** {round(self.bot.latency * 1000)}ms",
            inline=True
        )
        
        # Server info
        embed.add_field(
            name="Server Info",
            value=f"**Guilds:** {len(self.bot.guilds)}\n"
                  f"**Users:** {sum(g.member_count for g in self.bot.guilds)}\n"
                  f"**Voice:** {voice_connections} connected",
            inline=True
        )
        
        # Music info
        embed.add_field(
            name="Music Info",
            value=f"**Active Players:** {active_players}\n"
                  f"**Cached Searches:** {len(music_cog.search_cache) if music_cog else 0}",
            inline=True
        )
        
        # System info
        embed.add_field(
            name="System Info",
            value=f"**Python:** {platform.python_version()}\n"
                  f"**discord.py:** {discord.__version__}\n"
                  f"**Memory:** {memory_mb:.1f} MB",
            inline=True
        )
        
        # Resources
        embed.add_field(
            name="Resources",
            value=f"**CPU:** {psutil.cpu_percent()}%\n"
                  f"**Threads:** {process.num_threads()}",
            inline=True
        )
        
        embed.set_footer(text=f"Hertz v{self.bot.version}")
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="ping", description="Check bot latency")
    async def ping(self, interaction: discord.Interaction):
        """Check bot latency"""
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"**Latency:** {round(self.bot.latency * 1000)}ms",
            color=0x00ff00
        )
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="invite", description="Get bot invite link")
    async def invite(self, interaction: discord.Interaction):
        """Get bot invite link"""
        invite_url = discord.utils.oauth_url(
            self.bot.user.id,
            permissions=discord.Permissions(
                # Voice permissions
                connect=True,
                speak=True,
                use_voice_activation=True,
                
                # Text permissions
                send_messages=True,
                embed_links=True,
                attach_files=True,
                read_message_history=True,
                add_reactions=True,
                use_external_emojis=True,
                
                # General permissions
                view_channel=True,
            )
        )
        
        embed = discord.Embed(
            title="🔗 Invite Hertz",
            description=f"[Click here to invite Hertz to your server]({invite_url})",
            color=0x00ff00
        )
        
        embed.add_field(
            name="Features",
            value="• YouTube and Spotify support\n"
                  "• Queue management\n"
                  "• Search with autocomplete\n"
                  "• Loop and shuffle modes\n"
                  "• Beautiful embeds\n"
                  "• And much more!",
            inline=False
        )
        
        embed.set_footer(text="Thank you for using Hertz! 🎵")
        
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Utils(bot))