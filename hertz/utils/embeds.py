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
    return "1 song" if queue_size == 1 else f"{queue_size} songs"

def get_player_ui(player: Player) -> str:
    """Generate a text-based UI for the player controls"""
    song = player.get_current()
    if not song:
        return ""
    
    from ..services.player import Status
    
    position = player.get_position()
    button = "⏹️" if player.status == Status.PLAYING else "▶️"
    progress_bar = get_progress_bar(10, position / song.length if song.length > 0 else 0)
    elapsed_time = "live" if song.is_live else f"{pretty_time(position)}/{pretty_time(song.length)}"
    loop = "🔂" if player.loop_current_song else "🔁" if player.loop_current_queue else ""
    vol = f"{player.get_volume()}%"
    
    return f"{button} {progress_bar} `[{elapsed_time}]`🔉 {vol} {loop}"

def create_playing_embed(player: Player) -> disnake.Embed:
    """Create an embed for the currently playing song"""
    current_song = player.get_current()
    if not current_song:
        raise ValueError("No song is currently playing")
    
    from ..services.player import Status
    
    embed = disnake.Embed()
    embed.title = "Now Playing" if player.status == Status.PLAYING else "Paused"
    embed.color = disnake.Color.dark_green() if player.status == Status.PLAYING else disnake.Color.dark_red()
    
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
    embed.title = f"Now Playing {player.loop_current_song and '(loop)' or ''}"
    embed.color = disnake.Color.dark_green() if player.status == Status.PLAYING else disnake.Color.dark_grey()
    
    # Description with current song and UI
    description = (
        f"**{get_song_title(current_song)}**\n"
        f"Requested by: <@{current_song.requested_by}>\n\n"
        f"{get_player_ui(player)}\n\n"
    )
    
    # Add queued songs
    if queue_size > 0:
        description += "**Up next:**\n"
        for i in range(page_start, page_end):
            song = queue[i]
            song_number = i + 1
            duration = "live" if song.is_live else pretty_time(song.length)
            description += f"`{song_number}.` {get_song_title(song, True)} `[{duration}]`\n"
    
    embed.description = description
    
    # Add fields with queue stats
    total_length = sum(song.length for song in queue)
    
    embed.add_field(name="In queue", value=get_queue_info(player), inline=True)
    embed.add_field(name="Total length", value=f"{pretty_time(total_length) if total_length > 0 else '-'}", inline=True)
    embed.add_field(name="Page", value=f"{page} of {max_page}", inline=True)
    
    # Set footer with source info
    playlist_title = f" ({current_song.playlist['title']})" if current_song.playlist else ""
    embed.set_footer(text=f"Source: {current_song.artist}{playlist_title}")
    
    # Set thumbnail if available
    if current_song.thumbnail_url:
        embed.set_thumbnail(url=current_song.thumbnail_url)
    
    return embed

# New utility functions for metrics and dashboards

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
    
    # Create embed
    embed = disnake.Embed(
        title="Bot Health Status",
        description="Current status of the HERTZ Discord bot",
        color=disnake.Color.green()
    )
    
    embed.add_field(name="Status", value="✅ Operational", inline=False)
    embed.add_field(name="Uptime", value=uptime, inline=True)
    embed.add_field(name="Last Health Update", value=last_update, inline=True)
    embed.add_field(name="Connected Guilds", value=str(len(bot.guilds)), inline=True)
    
    # Add some system stats
    memory_info = process.memory_info()
    memory_usage = memory_info.rss / 1024 / 1024  # Convert to MB
    embed.add_field(name="Memory Usage", value=f"{memory_usage:.2f} MB", inline=True)
    embed.add_field(name="CPU Usage", value=f"{process.cpu_percent()}%", inline=True)
    
    # Add active voice connections
    voice_connections = sum(1 for guild in bot.guilds if guild.voice_client is not None)
    embed.add_field(name="Active Voice Connections", value=str(voice_connections), inline=True)
    
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
    
    # Create embed
    embed = disnake.Embed(
        title="Cache Information",
        color=disnake.Color.blue()
    )
    
    embed.add_field(name="Cache Size", value=f"{total_size/1024/1024:.2f} MB / {cache_limit/1024/1024:.2f} MB", inline=False)
    embed.add_field(name="Usage", value=f"{(total_size/cache_limit)*100:.1f}%", inline=True)
    embed.add_field(name="Files Cached", value=str(file_count), inline=True)
    
    if recent_files:
        embed.add_field(name="Recently Cached Songs", value="\n".join([f"{i+1}. {file.hash}" for i, file in enumerate(recent_files)]), inline=False)
    
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
    
    # Create embed
    embed = disnake.Embed(
        title="Music Playback Statistics",
        color=disnake.Color.purple()
    )
    
    embed.add_field(name="Active Music Sessions", value=str(guilds_with_music), inline=True)
    embed.add_field(name="Total Songs in Queues", value=str(total_queued_songs), inline=True)
    embed.add_field(name="Currently Playing", value=str(total_playing), inline=True)
    
    if most_songs_guild["id"]:
        embed.add_field(
            name="Server with Largest Queue", 
            value=f"{most_songs_guild['name']}: {most_songs_guild['count']} songs", 
            inline=False
        )
    
    return embed