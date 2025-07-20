"""
Player commands for HERTZ bot
Handles music playback controls like play, pause, stop, skip
"""

import logging
import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional

from services.audio_source import AudioSource
from services.spotify_service import spotify_service
from utils.error_handler import require_voice_connection, require_same_voice_channel, require_playing

logger = logging.getLogger(__name__)

class PlayerCommands(commands.Cog):
    """Music player control commands."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @app_commands.command(name="play", description="Play a song or add it to the queue")
    @app_commands.describe(query="Song name, URL, or search query")
    @require_voice_connection
    async def play(self, interaction: discord.Interaction, query: str):
        """Play a song or add it to the queue."""
        await interaction.response.defer()
        
        try:
            # Get or create player
            player = self.bot.player_manager.get(interaction.guild.id)
            
            # Connect to voice channel if not connected
            if not player.is_connected():
                await player.connect(interaction.user.voice.channel)
            
            # Check if it's a Spotify URL
            if spotify_service.is_spotify_url(query):
                if not spotify_service.is_available:
                    embed = discord.Embed(
                        title="❌ Error",
                        description="Spotify integration is not configured.",
                        color=0xff6b6b
                    )
                    await interaction.followup.send(embed=embed)
                    return
                
                # Resolve Spotify URL
                spotify_data = await spotify_service.resolve_url(query)
                if not spotify_data:
                    embed = discord.Embed(
                        title="❌ Error",
                        description="Failed to resolve Spotify URL.",
                        color=0xff6b6b
                    )
                    await interaction.followup.send(embed=embed)
                    return
                
                tracks = spotify_data['tracks']
                if not tracks:
                    embed = discord.Embed(
                        title="❌ Error",
                        description="No tracks found in Spotify URL.",
                        color=0xff6b6b
                    )
                    await interaction.followup.send(embed=embed)
                    return
                
                # Add user info to tracks
                for track in tracks:
                    track['requested_by_id'] = str(interaction.user.id)
                    track['requested_by_name'] = interaction.user.display_name
                
                if len(tracks) == 1:
                    # Single track
                    track = tracks[0]
                    position = await player.queue.add(track)
                    
                    if player.is_playing():
                        embed = discord.Embed(
                            title="📄 Added to Queue",
                            description=f"**{track['title']}** by {track['artist']}",
                            color=0x3498db
                        )
                        embed.add_field(name="Position", value=f"#{position + 1}", inline=True)
                        if track.get('duration'):
                            embed.add_field(name="Duration", value=f"{track['duration'] // 60}:{track['duration'] % 60:02d}", inline=True)
                    else:
                        embed = discord.Embed(
                            title="🎵 Now Playing",
                            description=f"**{track['title']}** by {track['artist']}",
                            color=0x00ff00
                        )
                        if track.get('duration'):
                            embed.add_field(name="Duration", value=f"{track['duration'] // 60}:{track['duration'] % 60:02d}", inline=True)
                        await player.play()
                else:
                    # Multiple tracks (playlist/album)
                    positions = await player.queue.add_multiple(tracks)
                    
                    embed = discord.Embed(
                        title="📋 Added Playlist to Queue",
                        description=f"Added **{len(tracks)}** tracks from {spotify_data['type']}",
                        color=0x3498db
                    )
                    
                    if spotify_data.get('name'):
                        embed.add_field(name="Name", value=spotify_data['name'], inline=False)
                    
                    if not player.is_playing():
                        await player.play()
            
            else:
                # Direct URL or search query
                if query.startswith('http'):
                    # It's a URL, try to extract info
                    try:
                        track_info = await AudioSource.get_track_info(query)
                    except Exception as e:
                        embed = discord.Embed(
                            title="❌ Error",
                            description=f"Failed to process URL: {str(e)}",
                            color=0xff6b6b
                        )
                        await interaction.followup.send(embed=embed)
                        return
                else:
                    # It's a search query
                    try:
                        search_results = await AudioSource.search_tracks(query, max_results=1)
                        if not search_results:
                            embed = discord.Embed(
                                title="❌ Error",
                                description="No results found for your search.",
                                color=0xff6b6b
                            )
                            await interaction.followup.send(embed=embed)
                            return
                        
                        track_info = search_results[0]
                    except Exception as e:
                        embed = discord.Embed(
                            title="❌ Error",
                            description=f"Search failed: {str(e)}",
                            color=0xff6b6b
                        )
                        await interaction.followup.send(embed=embed)
                        return
                
                # Add user info
                track_info['requested_by_id'] = str(interaction.user.id)
                track_info['requested_by_name'] = interaction.user.display_name
                
                # Add to queue
                position = await player.queue.add(track_info)
                
                if player.is_playing():
                    embed = discord.Embed(
                        title="📄 Added to Queue",
                        description=f"**{track_info['title']}** by {track_info['artist']}",
                        color=0x3498db
                    )
                    embed.add_field(name="Position", value=f"#{position + 1}", inline=True)
                    if track_info.get('duration'):
                        embed.add_field(name="Duration", value=f"{track_info['duration'] // 60}:{track_info['duration'] % 60:02d}", inline=True)
                else:
                    embed = discord.Embed(
                        title="🎵 Now Playing",
                        description=f"**{track_info['title']}** by {track_info['artist']}",
                        color=0x00ff00
                    )
                    if track_info.get('duration'):
                        embed.add_field(name="Duration", value=f"{track_info['duration'] // 60}:{track_info['duration'] % 60:02d}", inline=True)
                    await player.play()
            
            # Add thumbnail if available
            if 'thumbnail_url' in locals() and embed:
                track = tracks[0] if 'tracks' in locals() else track_info
                if track.get('thumbnail_url'):
                    embed.set_thumbnail(url=track['thumbnail_url'])
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Play command error: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="An error occurred while processing your request.",
                color=0xff6b6b
            )
            await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="pause", description="Pause the current song")
    @require_same_voice_channel
    @require_playing
    async def pause(self, interaction: discord.Interaction):
        """Pause the current song."""
        player = self.bot.player_manager.get(interaction.guild.id)
        
        await player.pause()
        
        embed = discord.Embed(
            title="⏸️ Paused",
            description="Playback paused.",
            color=0xffa500
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="resume", description="Resume the current song")
    @require_same_voice_channel
    async def resume(self, interaction: discord.Interaction):
        """Resume the current song."""
        player = self.bot.player_manager.get_existing(interaction.guild.id)
        
        if not player or player.status.value != "paused":
            embed = discord.Embed(
                title="❌ Error",
                description="No paused music to resume.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        await player.resume()
        
        embed = discord.Embed(
            title="▶️ Resumed",
            description="Playback resumed.",
            color=0x00ff00
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="stop", description="Stop playback and clear the queue")
    @require_same_voice_channel
    @require_playing
    async def stop(self, interaction: discord.Interaction):
        """Stop playback and clear the queue."""
        player = self.bot.player_manager.get(interaction.guild.id)
        
        await player.stop()
        await player.queue.clear()
        
        embed = discord.Embed(
            title="⏹️ Stopped",
            description="Playback stopped and queue cleared.",
            color=0xff6b6b
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="skip", description="Skip the current song")
    @app_commands.describe(count="Number of songs to skip (default: 1)")
    @require_same_voice_channel
    @require_playing
    async def skip(self, interaction: discord.Interaction, count: int = 1):
        """Skip one or more songs."""
        if count < 1 or count > 10:
            embed = discord.Embed(
                title="❌ Error",
                description="Skip count must be between 1 and 10.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        player = self.bot.player_manager.get(interaction.guild.id)
        
        skip_result = await player.skip(count)
        
        if skip_result['skipped_count'] == 0:
            embed = discord.Embed(
                title="❌ Error",
                description="No songs to skip.",
                color=0xff6b6b
            )
        else:
            embed = discord.Embed(
                title="⏭️ Skipped",
                description=f"Skipped {skip_result['skipped_count']} song(s).",
                color=0x3498db
            )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="volume", description="Set the playback volume")
    @app_commands.describe(level="Volume level (0-100)")
    @require_same_voice_channel
    async def volume(self, interaction: discord.Interaction, level: int):
        """Set the playback volume."""
        if level < 0 or level > 100:
            embed = discord.Embed(
                title="❌ Error",
                description="Volume must be between 0 and 100.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        player = self.bot.player_manager.get_existing(interaction.guild.id)
        
        if not player:
            embed = discord.Embed(
                title="❌ Error",
                description="No active player found.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        player.set_volume(level)
        
        # Update guild settings
        await self.bot.player_manager.update_guild_settings(
            interaction.guild.id,
            default_volume=level
        )
        
        embed = discord.Embed(
            title="🔊 Volume Changed",
            description=f"Volume set to {level}%.",
            color=0x3498db
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="nowplaying", description="Show the currently playing song")
    async def nowplaying(self, interaction: discord.Interaction):
        """Show the currently playing song."""
        player = self.bot.player_manager.get_existing(interaction.guild.id)
        
        if not player or not player.current_track:
            embed = discord.Embed(
                title="❌ Nothing Playing",
                description="No music is currently playing.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        track = player.current_track
        
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"**{track['title']}**",
            color=0x00ff00
        )
        
        embed.add_field(name="Artist", value=track.get('artist', 'Unknown'), inline=True)
        embed.add_field(name="Volume", value=f"{player.volume}%", inline=True)
        
        if track.get('duration'):
            position = player.get_position()
            duration = track['duration']
            progress = f"{position // 60}:{position % 60:02d} / {duration // 60}:{duration % 60:02d}"
            embed.add_field(name="Progress", value=progress, inline=True)
        
        if track.get('requested_by_name'):
            embed.add_field(name="Requested by", value=track['requested_by_name'], inline=True)
        
        if track.get('thumbnail_url'):
            embed.set_thumbnail(url=track['thumbnail_url'])
        
        # Add loop status
        loop_status = []
        if player.loop_current:
            loop_status.append("🔂 Track")
        if player.loop_queue:
            loop_status.append("🔁 Queue")
        
        if loop_status:
            embed.add_field(name="Loop", value=" & ".join(loop_status), inline=True)
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="disconnect", description="Disconnect the bot from voice channel")
    @require_same_voice_channel
    async def disconnect(self, interaction: discord.Interaction):
        """Disconnect the bot from voice channel."""
        player = self.bot.player_manager.get_existing(interaction.guild.id)
        
        if not player or not player.is_connected():
            embed = discord.Embed(
                title="❌ Error",
                description="Bot is not connected to a voice channel.",
                color=0xff6b6b
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        await player.disconnect()
        
        embed = discord.Embed(
            title="👋 Disconnected",
            description="Disconnected from voice channel.",
            color=0x3498db
        )
        
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    """Setup function for the cog."""
    await bot.add_cog(PlayerCommands(bot))