"""
Music Cog - Main music functionality for Hertz
"""
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import yt_dlp
import re
import logging
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from datetime import datetime, timezone
from typing import List, Dict, Optional
import os

logger = logging.getLogger('hertz.music')

# yt-dlp options
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'extractaudio': True,
    'audioformat': 'best',
    'audioquality': '320K',
}

# FFmpeg options
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -filter:a "volume=0.5"'
}


class SpotifyHandler:
    """Handle Spotify URL processing"""
    
    def __init__(self):
        client_id = os.getenv('SPOTIFY_CLIENT_ID')
        client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
        
        self.enabled = bool(client_id and client_secret)
        self.sp = None
        
        if self.enabled:
            try:
                credentials = SpotifyClientCredentials(
                    client_id=client_id,
                    client_secret=client_secret
                )
                self.sp = spotipy.Spotify(client_credentials_manager=credentials)
                logger.info("✅ Spotify integration enabled")
            except Exception as e:
                logger.warning(f"⚠️ Spotify setup failed: {e}")
                self.enabled = False
        else:
            logger.info("ℹ️ Spotify credentials not found - Spotify integration disabled")
    
    def extract_spotify_id(self, url: str) -> tuple:
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
        self.added_at = datetime.now(timezone.utc)
    
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
    
    def __init__(self, interaction):
        self.bot = interaction.client
        self.guild = interaction.guild
        self.channel = interaction.channel
        self.cog = interaction.client.get_cog('Music')
        
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
    
    def get_player(self, interaction) -> GuildMusicPlayer:
        """Get or create player for guild"""
        try:
            player = self.players[interaction.guild.id]
        except KeyError:
            player = GuildMusicPlayer(interaction)
            self.players[interaction.guild.id] = player
        
        return player
    
    async def search_youtube(self, query: str, limit: int = 5) -> List[Dict]:
        """Search YouTube and return results"""
        # Check cache
        cache_key = f"{query}:{limit}"
        if cache_key in self.search_cache:
            cached_time, results = self.search_cache[cache_key]
            if (datetime.now(timezone.utc) - cached_time).seconds < self.cache_ttl:
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
        self.search_cache[cache_key] = (datetime.now(timezone.utc), results)
        
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
            await interaction.followup.send(embed=embed, ephemeral=True)
            return
        
        # Get or create player
        player = self.get_player(interaction)
        
        # Connect to voice channel if not connected
        if not interaction.guild.voice_client:
            try:
                voice_client = await interaction.user.voice.channel.connect()
                player.voice_client = voice_client
                logger.info(f"🔗 Connected to {interaction.user.voice.channel.name}")
            except Exception as e:
                embed = discord.Embed(
                    title="❌ Connection Failed",
                    description=f"Failed to connect to voice channel: {e}",
                    color=0xff0000
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
        else:
            player.voice_client = interaction.guild.voice_client
        
        # Handle Spotify URLs
        if 'spotify.com' in query:
            if not self.spotify.enabled:
                embed = discord.Embed(
                    title="❌ Spotify Not Available",
                    description="Spotify integration is not configured!",
                    color=0xff0000
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Get tracks from Spotify
            tracks = await self.spotify.get_tracks(query)
            if not tracks:
                embed = discord.Embed(
                    title="❌ No Tracks Found",
                    description="No tracks found from Spotify URL!",
                    color=0xff0000
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Add tracks to queue
            added_count = 0
            for track_query in tracks[:50]:  # Limit to 50 tracks
                source_data = await YTDLSource.search(
                    track_query,
                    loop=self.bot.loop,
                    requester=interaction.user
                )
                if source_data:
                    await player.queue.put(source_data)
                    added_count += 1
            
            embed = discord.Embed(
                title="✅ Spotify Playlist Added",
                description=f"Added {added_count} tracks to the queue!",
                color=0x00ff00
            )
            await interaction.followup.send(embed=embed)
            return
        
        # Handle regular search/URL
        try:
            source_data = await YTDLSource.search(
                query,
                loop=self.bot.loop,
                requester=interaction.user
            )
            
            if not source_data:
                embed = discord.Embed(
                    title="❌ No Results",
                    description="No results found for your search!",
                    color=0xff0000
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # Add to queue
            await player.queue.put(source_data)
            
            embed = discord.Embed(
                title="✅ Track Added",
                description=f"**[{source_data['title']}]({source_data['webpage_url']})**",
                color=0x00ff00
            )
            
            if source_data.get('thumbnail'):
                embed.set_thumbnail(url=source_data['thumbnail'])
            
            if source_data.get('duration'):
                duration = f"{source_data['duration'] // 60}:{source_data['duration'] % 60:02d}"
                embed.add_field(name="Duration", value=duration, inline=True)
            
            queue_size = player.queue.qsize()
            if queue_size > 1:
                embed.add_field(name="Position in Queue", value=str(queue_size), inline=True)
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Play command error: {e}")
            embed = discord.Embed(
                title="❌ Playback Error",
                description="An error occurred while trying to play this track!",
                color=0xff0000
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
    
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
            color=0x00ff00
        )
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="resume", description="Resume playback")
    async def resume(self, interaction: discord.Interaction):
        """Resume playback"""
        vc = interaction.guild.voice_client
        
        if not vc:
            embed = discord.Embed(
                title="❌ Not Playing",
                description="Nothing is currently playing!",
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
        """Stop playback and clear queue"""
        player = self.players.get(interaction.guild.id)
        
        if not player or not interaction.guild.voice_client:
            embed = discord.Embed(
                title="❌ Not Playing",
                description="Nothing is currently playing!",
                color=0xff0000
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Clear queue
        while not player.queue.empty():
            try:
                player.queue.get_nowait()
            except:
                break
        
        # Stop playback
        interaction.guild.voice_client.stop()
        
        embed = discord.Embed(
            title="⏹️ Stopped",
            description="Playback stopped and queue cleared!",
            color=0x00ff00
        )
        await interaction.response.send_message(embed=embed)
    
# disconnect command moved to playback cog to avoid conflicts


async def setup(bot):
    await bot.add_cog(Music(bot))