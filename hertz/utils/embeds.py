# hertz/utils/embeds.py
import disnake
from typing import Optional
import os
import time
import psutil
import asyncio

from ..services.player import Player
from .time import pretty_time
from .progress_bar import get_progress_bar

def truncate(text: str, max_length: int = 50) -> str:
    """Truncate text to a maximum length with ellipsis"""
    return text if len(text) <= max_length else f"{text[:max_length-3]}..."

def get_song_title(song, should_truncate: bool = False) -> str:
    """Format song title with URL if available"""
    from ..services.player import MediaSource
    
    if song.source == MediaSource.HLS.value:
        return f"[{song.title}]({song.url})"
    
    title = song.title.replace("[", "\\[").replace("]", "\\]")
    clean_title = title.strip()
    
    if should_truncate:
        clean_title = truncate(clean_title, 48)
    
    if hasattr(song, 'url') and song.url:
        youtube_id = song.url
        offset_param = f"&t={song.offset}" if song.offset > 0 else ""
        return f"[{clean_title}](https://www.youtube.com/watch?v={youtube_id}{offset_param})"
    
    return clean_title

def get_queue_info(player: Player) -> str:
    """Get queue size info string"""
    queue_size = player.queue_size()
    if queue_size == 0:
        return "-"
    return "1 track" if queue_size == 1 else f"{queue_size} tracks"

def get_player_ui(player: Player) -> str:
    """Generate a text-based UI for the player controls"""
    song = player.get_current()
    if not song:
        return ""
    
    from ..services.player import Status
    
    position = player.get_position()
    button = "⏹️" if player.status == Status.PLAYING else "▶️"
    progress_bar = get_progress_bar(10, position / song.length if song.length > 0 else 0)
    elapsed_time = "LIVE" if song.is_live else f"{pretty_time(position)}/{pretty_time(song.length)}"
    loop = "🔂" if player.loop_current_song else "🔁" if player.loop_current_queue else ""
    vol = f"{player.get_volume()}%"
    
    return f"{button} {progress_bar} `[{elapsed_time}]` 🔊 {vol} {loop}"

def create_playing_embed(player: Player) -> disnake.Embed:
    """Create an embed for the currently playing song"""
    current_song = player.get_current()
    if not current_song:
        raise ValueError("No song is currently playing")
    
    from ..services.player import Status
    
    embed = disnake.Embed()
    
    # Set a more vibrant color scheme
    embed.color = disnake.Color.from_rgb(88, 101, 242) if player.status == Status.PLAYING else disnake.Color.from_rgb(237, 66, 69)
    
    # More audio-themed titles
    embed.title = "🎧 Now Transmitting" if player.status == Status.PLAYING else "⏸️ Signal Paused"
    
    # Description with song details and UI
    embed.description = (
        f"**{get_song_title(current_song)}**\n"
        f"Requested by: <@{current_song.requested_by}>\n\n"
        f"{get_player_ui(player)}"
    )
    
    # Set footer with source info
    embed.set_footer(text=f"Source: {current_song.artist}")
    
    # Set thumbnail if available
    if current_song.thumbnail_url:
        embed.set_thumbnail(url=current_song.thumbnail_url)
    
    return embed

def create_queue_embed(player: Player, page: int = 1, page_size: int = 10) -> disnake.Embed:
    """Create an embed for the queue"""
    current_song = player.get_current()
    if not current_song:
        raise ValueError("Queue is empty")
    
    queue = player.get_queue()
    queue_size = len(queue)
    max_page = max(1, (queue_size + page_size - 1) // page_size)
    
    if page > max_page:
        raise ValueError("Page number is too high")
    
    page_start = (page - 1) * page_size
    page_end = min(page_start + page_size, queue_size)
    
    from ..services.player import Status
    
    embed = disnake.Embed()
    
    # Better title and color for queue
    if player.loop_current_song:
        embed.title = "🔂 Signal Looping"
    elif player.loop_current_queue:
        embed.title = "🔄 Playlist Looping" 
    else:
        embed.title = "📻 Audio Stream"
        
    # Updated color scheme
    embed.color = disnake.Color.from_rgb(88, 101, 242) if player.status == Status.PLAYING else disnake.Color.from_rgb(153, 170, 181)
    
    # Description with current song and UI
    description = (
        f"**{get_song_title(current_song)}**\n"
        f"Requested by: <@{current_song.requested_by}>\n\n"
        f"{get_player_ui(player)}\n\n"
    )
    
    # Add queued songs
    if queue_size > 0:
        description += "**Upcoming Tracks:**\n"
        for i in range(page_start, page_end):
            song = queue[i]
            song_number = i + 1
            duration = "LIVE" if song.is_live else pretty_time(song.length)
            description += f"`{song_number}.` {get_song_title(song, True)} `[{duration}]`\n"
    
    embed.description = description
    
    # Add fields with queue stats
    total_length = sum(song.length for song in queue)
    
    embed.add_field(name="Queue Size", value=get_queue_info(player), inline=True)
    embed.add_field(name="Total Duration", value=f"{pretty_time(total_length) if total_length > 0 else '-'}", inline=True)
    embed.add_field(name="Page", value=f"{page} of {max_page}", inline=True)
    
    # Set footer with source info
    playlist_title = f" ({current_song.playlist['title']})" if current_song.playlist else ""
    embed.set_footer(text=f"Source: {current_song.artist}{playlist_title}")
    
    # Set thumbnail if available
    if current_song.thumbnail_url:
        embed.set_thumbnail(url=current_song.thumbnail_url)
    
    return embed

# Create a health embed with the HERTZ personality
def create_health_embed(bot) -> disnake.Embed:
    """Create an embed with bot health metrics"""
    process = psutil.Process(os.getpid())
    
    # Calculate uptime
    start_time = process.create_time()
    uptime_seconds = time.time() - start_time
    
    # Format uptime nicely
    days, remainder = divmod(uptime_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if days > 0:
        uptime = f"{int(days)}d {int(hours)}h {int(minutes)}m"
    elif hours > 0:
        uptime = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
    else:
        uptime = f"{int(minutes)}m {int(seconds)}s"
    
    # Get last health check time
    health_file = '/data/health_status'
    last_update = "Unknown"
    if os.path.exists(health_file):
        with open(health_file, 'r') as f:
            timestamp = int(f.read().strip())
            now = int(time.time())
            seconds_since_update = now - timestamp
            last_update = f"{seconds_since_update} seconds ago"
    
    # Create embed with audio-themed styling
    embed = disnake.Embed(
        title="📡 System Status Monitor",
        description="Current HERTZ broadcast metrics",
        color=disnake.Color.from_rgb(88, 101, 242)
    )
    
    # Signal strength indicator based on health
    signal_strength = "▁▂▃▄▅▆▇█"  # Full strength
    
    embed.add_field(name="🟢 Signal Strength", value=signal_strength, inline=False)
    embed.add_field(name="⏱️ Uptime", value=uptime, inline=True)
    embed.add_field(name="🔄 Last Heartbeat", value=last_update, inline=True)
    embed.add_field(name="📡 Connected Servers", value=str(len(bot.guilds)), inline=True)
    
    # Add some system stats
    memory_info = process.memory_info()
    memory_usage = memory_info.rss / 1024 / 1024  # Convert to MB
    embed.add_field(name="💾 Memory Usage", value=f"{memory_usage:.2f} MB", inline=True)
    embed.add_field(name="⚡ CPU Usage", value=f"{process.cpu_percent()}%", inline=True)
    
    # Add active voice connections
    voice_connections = sum(1 for guild in bot.guilds if guild.voice_client is not None)
    embed.add_field(name="🎧 Active Streams", value=str(voice_connections), inline=True)
    
    return embed

async def create_cache_embed(bot) -> disnake.Embed:
    """Create an embed with cache statistics"""
    from ..db.client import get_total_cache_size, get_recent_file_caches
    
    # Get cache data asynchronously (without asyncio.run)
    total_size = await get_total_cache_size()
    cache_limit = bot.config.cache_limit_bytes
    
    # Get count of cached files
    cache_dir = bot.config.CACHE_DIR
    file_count = len([f for f in os.listdir(cache_dir) if os.path.isfile(os.path.join(cache_dir, f)) and not f.endswith('.tmp')])
    
    # Get recent cached songs
    recent_files = await get_recent_file_caches(5)
    
    # Create embed with audio-themed styling
    embed = disnake.Embed(
        title="💽 Audio Cache Status",
        description="Current track storage information",
        color=disnake.Color.from_rgb(88, 101, 242)
    )
    
    usage_percent = (total_size/cache_limit)*100 if cache_limit > 0 else 0
    
    # Create a visual bar for cache usage
    full_blocks = min(int(usage_percent / 10), 10)
    usage_bar = "█" * full_blocks + "░" * (10 - full_blocks)
    
    embed.add_field(
        name="📊 Cache Usage", 
        value=f"`{usage_bar}` {usage_percent:.1f}%\n{total_size/1024/1024:.2f} MB / {cache_limit/1024/1024:.2f} MB", 
        inline=False
    )
    
    embed.add_field(name="📀 Cached Tracks", value=str(file_count), inline=True)
    
    if recent_files:
        embed.add_field(
            name="🆕 Recently Cached",
            value="\n".join([f"{i+1}. {file.hash[:8]}... ({file.bytes/1024:.1f} KB)" for i, file in enumerate(recent_files)]),
            inline=False
        )
    
    return embed

def create_music_stats_embed(bot) -> disnake.Embed:
    """Create an embed with music playback statistics"""
    # Initialize counters
    total_queued_songs = 0
    total_playing = 0
    guilds_with_music = 0
    most_songs_guild = {"id": None, "count": 0, "name": "None"}
    
    # Gather stats from all players
    for guild_id, player in bot.player_manager.players.items():
        guild = bot.get_guild(int(guild_id))
        guild_name = guild.name if guild else f"Unknown ({guild_id})"
        
        # Count current queue size
        queue_size = len(player.queue)
        total_queued_songs += queue_size
        
        # Track guild with most songs
        if queue_size > most_songs_guild["count"]:
            most_songs_guild = {
                "id": guild_id,
                "count": queue_size,
                "name": guild_name
            }
        
        # Count playing status
        if player.get_current():
            total_playing += 1
            guilds_with_music += 1
    
    # Create embed with audio-themed styling
    embed = disnake.Embed(
        title="🎛️ Audio Dashboard",
        description="Current broadcast statistics",
        color=disnake.Color.from_rgb(88, 101, 242)
    )
    
    embed.add_field(name="🎧 Active Streams", value=str(guilds_with_music), inline=True)
    embed.add_field(name="🎵 Queued Tracks", value=str(total_queued_songs), inline=True)
    embed.add_field(name="▶️ Now Playing", value=str(total_playing), inline=True)
    
    if most_songs_guild["id"]:
        embed.add_field(
            name="📊 Top Server", 
            value=f"{most_songs_guild['name']}: {most_songs_guild['count']} tracks", 
            inline=False
        )
    
    return embed