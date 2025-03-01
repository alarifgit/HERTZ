# hertz/utils/embeds.py
import disnake
from typing import Optional

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