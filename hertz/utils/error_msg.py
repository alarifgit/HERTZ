# hertz/utils/error_msg.py
"""Utility for generating error messages with professional terminology"""

def error_msg(error: str = None) -> str:
    """
    Format an error message with professional terminology
    
    Args:
        error: Error message or None
        
    Returns:
        Formatted error message
    """
    if not error:
        return "❌ Unknown error occurred"
        
    if isinstance(error, Exception):
        error = str(error)
    
    # Common error messages with clear formatting
    error_map = {
        "not connected": "🔌 Not connected to voice channel",
        "not currently playing": "⚠️ Nothing currently playing",
        "nothing is playing": "⚠️ Nothing currently playing",
        "gotta be in a voice channel": "🎧 You need to be in a voice channel",
        "you need to be in a voice channel": "🎧 You need to be in a voice channel",
        "nothing to play": "📂 Playlist empty. Add some tracks first",
        "nothing is currently playing": "📂 Playlist empty. Add some tracks first",
        "no song to loop": "⚠️ No track available to loop",
        "no songs to loop": "⚠️ No track available to loop",
        "no track to loop": "⚠️ No track available to loop",
        "no tracks to loop": "⚠️ No track available to loop",
        "not enough songs to loop a queue": "⚠️ Need more tracks to loop the queue",
        "not enough tracks to loop a queue": "⚠️ Need more tracks to loop the queue",
        "no favorite with that name exists": "⚠️ Favorite not found",
        "invalid limit": "⚠️ Invalid value: Limit out of range",
        "position must be at least 1": "⚠️ Track position must be at least 1",
        "range must be at least 1": "⚠️ Range must be at least 1",
        "no song to skip to": "⚠️ End of playlist reached",
        "no track to skip to": "⚠️ End of playlist reached",
        "no song to go back to": "⚠️ Already at the first track",
        "no track to go back to": "⚠️ Already at the first track",
        "can't seek in a livestream": "⚠️ Cannot seek in livestream",
        "can't seek past the end of the song": "⚠️ Cannot seek past the end of the track",
        "can't seek past the end of the track": "⚠️ Cannot seek past the end of the track",
        "queue is empty": "📂 Playlist empty. Add some tracks first",
        "not enough songs to shuffle": "⚠️ Need more tracks to shuffle",
        "not enough tracks to shuffle": "⚠️ Need more tracks to shuffle",
        "no songs found": "🔍 No matching tracks found. Try different search terms.",
        "no tracks found": "🔍 No matching tracks found. Try different search terms.",
        "a favorite with that name already exists": "⚠️ A favorite with that name already exists.",
        "you can only remove your own favorites": "🔒 You can only delete your own favorites."
    }
    
    # Check for partial matches first
    for key, value in error_map.items():
        if key in error.lower():
            return value
    
    # Default format for other errors
    return f"❌ Error: {error}"