"""
Music Cog - Core playback functionality using yt-dlp
"""
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import yt_dlp
import logging
from typing import Optional, List, Dict, Any
import re
from datetime import datetime
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import os

logger = logging.getLogger('hertz.music')

# YT-DLP options optimized for Discord playback
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'logtostderr': False,
    'ignoreerrors': False,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'extract_flat': 'in_playlist',
    'age_limit': None,
    'cookiefile': None,  # Add cookie file path if needed
    'nocheckcertificate': True
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

class SpotifyHandler:
    """Handle Spotify URL parsing and track search"""
    
    def __init__(self):
        client_id = os.getenv('SPOTIFY_CLIENT_ID')
        client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
        
        if client_id and client_secret:
            auth_manager = SpotifyClientCredentials(
                client_id=client_id,
                client_secret=client_secret
            )
            self.sp = spotipy.Spotify(auth_manager=auth_manager)
            self.enabled = True
        else:
            self.sp = None
            self.enabled = False
            logger.warning("⚠️ Spotify credentials not configured")
    
    def is_spotify_url(self, url: str) -> bool:
        """Check if URL is a Spotify link"""
        return 'spotify.com' in url or 'spotify:' in url
    
    def extract_spotify_id(self, url: str) -> tuple[str, str]:
        """Extract Spotify ID and type from URL"""
        patterns = {
            'track': r'spotify(?:\.com)?[:/]track[:/]([a-zA-Z0-9]+)',
            'playlist': r'spotify(?:\.com)?[:/]playlist[:/]([a-zA-Z0-9]+)',
            'album': r'spotify(?:\.com)?[:/]album[:/]([a-zA-Z0-9]+)'
        }
        
        for type_, pattern in patterns.items():
            match = re.search(pattern, url)
            if match:
                return match.group(1), type_
        
        return None, None
    
    async def get_tracks(self, url: str) -> List[str]:
        """Get track search queries from Spotify URL"""
        if not self.enabled:
            return []
        
        spotify_id, content_type = self.extract_spotify_id(url)
        if not spotify_id:
            return []
        
        queries = []
        
        try:
            if content_type == 'track':
                track = self.sp.track(spotify_id)
                artist = track['artists'][0]['name']
                title = track['name']
                queries.append(f"{artist} {title}")
                
            elif content_type == 'playlist':
                playlist = self.sp.playlist_tracks(spotify_id, limit=100)
                for item in playlist['items']:
                    if item['track']:
                        artist = item['track']['artists'][0]['name']
                        title = item['track']['name']
                        queries.append(f"{artist} {title}")
                
            elif content_type == 'album':
                album = self.sp.album_tracks(spotify_id, limit=50)
                for track in album['items']:
                    artist = track['artists'][0]['name']
                    title = track['name']
                    queries.append(f"{artist} {title}")
                    
        except Exception as e:
            logger.error(f"Spotify API error: {e}")
        
        return queries


class YTDLSource(discord.PCMVolumeTransformer):
    """Audio source for Discord voice using yt-dlp"""
    
    def __init__(self, source, *, data, volume=1.0):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.webpage_url = data.get('webpage_url')
        self.duration = data.get('duration')
        self.thumbnail = data.get('thumbnail')
        self.artist = data.get('artist', 'Unknown Artist')
        self.requester = data.get('requester')
        self.added_at = datetime.utcnow()
    
    @classmethod
    async def from_url(cls, url: str, *, loop=None, stream=True, requester=None):
        """Create audio source from URL"""
        loop = loop or asyncio.get_event_loop()
        
        # Extract info
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            try:
                data = await loop.run_in_executor(
                    None, 
                    lambda: ydl.extract_info(url, download=not stream)
                )
            except Exception as e:
                logger.error(f"yt-dlp extraction error: {e}")
                raise
        
        # Handle playlists
        if 'entries' in data and data['entries']:
            data = data['entries'][0]
        
        # Get stream URL
        filename = data['url'] if stream else ydl.prepare_filename(data)
        
        # Store requester info
        if requester:
            data['requester'] = requester
        
        # Create FFmpeg audio source
        source = discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS)
        return cls(source, data=data)
    
    @classmethod
    async def search(cls, query: str, *, loop=None, requester=None):
        """Search YouTube and return first result"""
        loop = loop or asyncio.get_event_loop()
        
        # Add ytsearch if not a URL
        if not query.startswith(('http://', 'https://')):
            query = f'ytsearch:{query}'
        
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            try:
                data = await loop.run_in_executor(
                    None,
                    lambda: ydl.extract_info(query, download=False)
                )
            except Exception as e:
                logger.error(f"Search error: {e}")
                return None
        
        if 'entries' in data and data['entries']:
            # Return first search result
            source_data = data['entries'][0]
            source_data['requester'] = requester
            return source_data
        
        return None


class GuildMusicPlayer:
    """Music player for a specific guild"""
    
    def __init__(self, ctx):
        self.bot = ctx.bot
        self.guild = ctx.guild
        self.channel = ctx.channel
        self.cog = ctx.cog
        
        self.queue = asyncio.Queue()
        self.next = asyncio.Event()
        
        self.current = None
        self.voice_client = None
        self.volume = 0.5
        
        self.loop_mode = 'off'  # off, track, queue
        self.queue_list = []  # For queue loop mode
        
        self.task = self.bot.loop.create_task(self.player_loop())
    
    async def player_loop(self):
        """Main player loop"""
        await self.bot.wait_until_ready()
        
        while not self.bot.is_closed():
            self.next.clear()
            
            try:
                # Wait for next track with timeout
                async with asyncio.timeout(300):  # 5 minute timeout
                    source = await self.queue.get()
            except asyncio.TimeoutError:
                # Disconnect after timeout
                if self.voice_client and self.voice_client.is_connected():
                    await self.voice_client.disconnect()
                    break
            
            # Create audio source
            if not isinstance(source, YTDLSource):
                try:
                    source = await YTDLSource.from_url(
                        source['webpage_url'],
                        loop=self.bot.loop,
                        stream=True,
                        requester=source.get('requester')
                    )
                except Exception as e:
                    logger.error(f"Error creating audio source: {e}")
                    continue
            
            source.volume = self.volume
            self.current = source
            
            # Play the track
            if self.voice_client and self.voice_client.is_connected():
                self.voice_client.play(
                    source,
                    after=lambda e: self.bot.loop.call_soon_threadsafe(self.next.set)
                )
                
                # Send now playing embed
                await self.send_now_playing()
                
                # Wait for track to finish
                await self.next.wait()
                
                # Handle loop modes
                if self.loop_mode == 'track' and self.current:
                    # Re-add current track
                    await self.queue.put(self.current.data)
                elif self.loop_mode == 'queue' and self.current:
                    # Add to back of queue list
                    self.queue_list.append(self.current.data)
                    
                    # If queue is empty, refill from queue_list
                    if self.queue.empty() and self.queue_list:
                        for track in self.queue_list:
                            await self.queue.put(track)
                        self.queue_list.clear()
                
                self.current = None
    
    async def send_now_playing(self):
        """Send now playing embed"""
        if not self.current:
            return
        
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"**[{self.current.title}]({self.current.webpage_url})**",
            color=0x00ff00
        )
        
        if self.current.thumbnail:
            embed.set_thumbnail(url=self.current.thumbnail)
        
        if self.current.duration:
            duration = f"{self.current.duration // 60}:{self.current.duration % 60:02d}"
            embed.add_field(name="Duration", value=duration, inline=True)
        
        embed.add_field(name="Volume", value=f"{int(self.volume * 100)}%", inline=True)
        embed.add_field(name="Loop", value=self.loop_mode.title(), inline=True)
        
        if self.current.requester:
            embed.set_footer(
                text=f"Requested by {self.current.requester}",
                icon_url=self.current.requester.avatar.url if self.current.requester.avatar else None
            )
        
        await self.channel.send(embed=embed)
    
    def destroy(self):
        """Clean up player"""
        return self.bot.loop.create_task(self.cleanup())
    
    async def cleanup(self):
        """Disconnect and cleanup"""
        if self.voice_client:
            await self.voice_client.disconnect()
        
        try:
            self.task.cancel()
        except:
            pass


class Music(commands.Cog):
    """Music commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.players = {}
        self.spotify = SpotifyHandler()
        
        # Search cache for autocomplete
        self.search_cache = {}
        self.cache_ttl = 3600  # 1 hour
    
    def get_player(self, ctx) -> GuildMusicPlayer:
        """Get or create player for guild"""
        try:
            player = self.players[ctx.guild.id]
        except KeyError:
            player = GuildMusicPlayer(ctx)
            self.players[ctx.guild.id] = player
        
        return player
    
    async def search_youtube(self, query: str, limit: int = 5) -> List[Dict]:
        """Search YouTube and return results"""
        # Check cache
        cache_key = f"{query}:{limit}"
        if cache_key in self.search_cache:
            cached_time, results = self.search_cache[cache_key]
            if (datetime.utcnow() - cached_time).seconds < self.cache_ttl:
                return results
        
        # Search YouTube
        with yt_dlp.YoutubeDL({**YDL_OPTIONS, 'quiet': True}) as ydl:
            try:
                data = await self.bot.loop.run_in_executor(
                    None,
                    lambda: ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
                )
            except Exception as e:
                logger.error(f"YouTube search error: {e}")
                return []
        
        results = []
        if 'entries' in data:
            for entry in data['entries'][:limit]:
                results.append({
                    'title': entry.get('title', 'Unknown'),
                    'url': entry.get('webpage_url', ''),
                    'duration': entry.get('duration', 0),
                    'channel': entry.get('channel', 'Unknown')
                })
        
        # Cache results
        self.search_cache[cache_key] = (datetime.utcnow(), results)
        
        return results
    
    @app_commands.command(name="play", description="Play a song or playlist")
    @app_commands.describe(query="Song name, YouTube URL, or Spotify URL")
    async def play(self, interaction: discord.Interaction, query: str):
        """Play command with autocomplete"""
        # Defer response
        await interaction.response.defer()
        
        # Check if user is in voice channel
        if not interaction.user.voice:
            embed = discord.Embed(
                title="❌ Not in Voice Channel",
                description="You need to be in a voice channel to use this command!",
                color=0xff0000
            )
            await interaction.followup.send(embed=embed)
            return
        
        # Get or create player
        ctx = await self.bot.get_context(interaction)
        ctx.voice_client = interaction.guild.voice_client
        player = self.get_player(ctx)
        
        # Connect to voice if not connected
        if not ctx.voice_client:
            channel = interaction.user.voice.channel
            try:
                ctx.voice_client = await channel.connect()
                player.voice_client = ctx.voice_client
                logger.info(f"🔊 Connected to voice channel: {channel.name}")
            except Exception as e:
                logger.error(f"Failed to connect to voice: {e}")
                embed = discord.Embed(
                    title="❌ Connection Failed",
                    description=f"Could not connect to voice channel: {e}",
                    color=0xff0000
                )
                await interaction.followup.send(embed=embed)
                return
        
        # Handle Spotify URLs
        tracks_to_add = []
        
        if self.spotify.is_spotify_url(query):
            if not self.spotify.enabled:
                embed = discord.Embed(
                    title="❌ Spotify Not Configured",
                    description="Spotify support is not enabled. Please configure Spotify credentials.",
                    color=0xff0000
                )
                await interaction.followup.send(embed=embed)
                return
            
            # Get track queries from Spotify
            queries = await self.spotify.get_tracks(query)
            if not queries:
                embed = discord.Embed(
                    title="❌ Invalid Spotify URL",
                    description="Could not extract tracks from the Spotify URL.",
                    color=0xff0000
                )
                await interaction.followup.send(embed=embed)
                return
            
            # Search for each track on YouTube
            embed = discord.Embed(
                title="🎵 Processing Spotify Playlist",
                description=f"Searching for {len(queries)} tracks on YouTube...",
                color=0x1db954
            )
            msg = await interaction.followup.send(embed=embed)
            
            for i, search_query in enumerate(queries):
                track = await YTDLSource.search(
                    search_query,
                    loop=self.bot.loop,
                    requester=interaction.user
                )
                if track:
                    tracks_to_add.append(track)
                
                # Update progress every 5 tracks
                if (i + 1) % 5 == 0:
                    embed.description = f"Found {len(tracks_to_add)}/{i+1} tracks..."
                    await msg.edit(embed=embed)
        else:
            # Regular YouTube search or URL
            track = await YTDLSource.search(
                query,
                loop=self.bot.loop,
                requester=interaction.user
            )
            if track:
                tracks_to_add.append(track)
        
        # Add tracks to queue
        if not tracks_to_add:
            embed = discord.Embed(
                title="❌ No Results",
                description="Could not find any tracks for your query.",
                color=0xff0000
            )
            await interaction.followup.send(embed=embed)
            return
        
        # Add to queue
        for track in tracks_to_add:
            await player.queue.put(track)
        
        # Send confirmation
        if len(tracks_to_add) == 1:
            track = tracks_to_add[0]
            embed = discord.Embed(
                title="✅ Added to Queue",
                description=f"**[{track.get('title', 'Unknown')}]({track.get('webpage_url', '')})**",
                color=0x00ff00
            )
            if track.get('thumbnail'):
                embed.set_thumbnail(url=track['thumbnail'])
        else:
            embed = discord.Embed(
                title="✅ Added to Queue",
                description=f"Added **{len(tracks_to_add)}** tracks to the queue!",
                color=0x00ff00
            )
        
        await interaction.followup.send(embed=embed)
    
    @play.autocomplete('query')
    async def play_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice]:
        """Autocomplete for play command"""
        if not current or len(current) < 2:
            return []
        
        # Search YouTube
        results = await self.search_youtube(current, limit=5)
        
        choices = []
        for result in results:
            # Format duration
            duration = result['duration']
            if duration:
                duration_str = f"{duration // 60}:{duration % 60:02d}"
            else:
                duration_str = "Live"
            
            # Create choice with title and duration
            name = f"{result['title'][:50]} [{duration_str}]"
            value = result['url']
            
            choices.append(app_commands.Choice(name=name, value=value))
        
        return choices
    
    @app_commands.command(name="skip", description="Skip the current song")
    async def skip(self, interaction: discord.Interaction):
        """Skip current track"""
        if not interaction.guild.voice_client:
            embed = discord.Embed(
                title="❌ Not Playing",
                description="Nothing is currently playing!",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        interaction.guild.voice_client.stop()
        
        embed = discord.Embed(
            title="⏭️ Skipped",
            description="Skipped to the next track!",
            color=0x00ff00
        )
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="pause", description="Pause playback")
    async def pause(self, interaction: discord.Interaction):
        """Pause playback"""
        vc = interaction.guild.voice_client
        
        if not vc or not vc.is_playing():
            embed = discord.Embed(
                title="❌ Not Playing",
                description="Nothing is currently playing!",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if vc.is_paused():
            embed = discord.Embed(
                title="⏸️ Already Paused",
                description="Playback is already paused!",
                color=0xffff00
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        vc.pause()
        embed = discord.Embed(
            title="⏸️ Paused",
            description="Playback has been paused!",
            color=0xffff00
        )
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="resume", description="Resume playback")
    async def resume(self, interaction: discord.Interaction):
        """Resume playback"""
        vc = interaction.guild.voice_client
        
        if not vc:
            embed = discord.Embed(
                title="❌ Not Connected",
                description="Bot is not connected to a voice channel!",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if not vc.is_paused():
            embed = discord.Embed(
                title="▶️ Not Paused",
                description="Playback is not paused!",
                color=0xffff00
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        vc.resume()
        embed = discord.Embed(
            title="▶️ Resumed",
            description="Playback has been resumed!",
            color=0x00ff00
        )
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="stop", description="Stop playback and clear queue")
    async def stop(self, interaction: discord.Interaction):
        """Stop playback and disconnect"""
        if interaction.guild.id in self.players:
            player = self.players[interaction.guild.id]
            
            # Clear queue
            while not player.queue.empty():
                try:
                    player.queue.get_nowait()
                except:
                    break
            
            # Stop current track
            if interaction.guild.voice_client:
                interaction.guild.voice_client.stop()
                await interaction.guild.voice_client.disconnect()
            
            # Destroy player
            player.destroy()
            del self.players[interaction.guild.id]
            
            embed = discord.Embed(
                title="⏹️ Stopped",
                description="Playback stopped and queue cleared!",
                color=0x00ff00
            )
            await interaction.response.send_message(embed=embed)
        else:
            embed = discord.Embed(
                title="❌ Not Playing",
                description="Nothing is currently playing!",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Clean up player when bot disconnects"""
        if member == self.bot.user and before.channel and not after.channel:
            # Bot disconnected from voice
            if member.guild.id in self.players:
                player = self.players[member.guild.id]
                player.destroy()
                del self.players[member.guild.id]
                logger.info(f"🧹 Cleaned up player for guild {member.guild.name}")

async def setup(bot):
    await bot.add_cog(Music(bot))