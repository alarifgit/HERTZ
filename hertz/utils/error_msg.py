# hertz/utils/error_msg.py
"""Utility for generating error messages with simple, clean language"""

def error_msg(error: str = None) -> str:
    """
    Format an error message with simple language
    
    Args:
        error: Error message or None
        
    Returns:
        Formatted error message
    """
    if not error:
        return "❌ Unknown error"
        
    if isinstance(error, Exception):
        error = str(error)
    
    # Common error messages with simple formatting
    error_map = {
        "not connected": "❌ Not connected to voice channel",
        "not currently playing": "❌ Nothing is playing",
        "nothing is playing": "❌ Nothing is playing",
        "gotta be in a voice channel": "❌ You need to be in a voice channel",
        "you need to be in a voice channel": "❌ You need to be in a voice channel",
        "nothing to play": "❌ Queue is empty",
        "nothing is currently playing": "❌ Queue is empty",
        "no song to loop": "❌ Nothing to loop",
        "no songs to loop": "❌ Nothing to loop",
        "no track to loop": "❌ Nothing to loop",
        "no tracks to loop": "❌ Nothing to loop",
        "not enough songs to loop a queue": "❌ Need more tracks to loop queue",
        "not enough tracks to loop a queue": "❌ Need more tracks to loop queue",
        "no favorite with that name exists": "❌ Favorite not found",
        "invalid limit": "❌ Invalid limit",
        "position must be at least 1": "❌ Position must be at least 1",
        "range must be at least 1": "❌ Range must be at least 1",
        "no song to skip to": "❌ No more tracks",
        "no track to skip to": "❌ No more tracks",
        "no song to go back to": "❌ Already at first track",
        "no track to go back to": "❌ Already at first track",
        "can't seek in a livestream": "❌ Cannot seek in livestream",
        "can't seek past the end of the song": "❌ Cannot seek past end of track",
        "can't seek past the end of the track": "❌ Cannot seek past end of track",
        "queue is empty": "❌ Queue is empty",
        "not enough songs to shuffle": "❌ Need more tracks to shuffle",
        "not enough tracks to shuffle": "❌ Need more tracks to shuffle",
        "no songs found": "❌ No tracks found",
        "no tracks found": "❌ No tracks found",
        "a favorite with that name already exists": "❌ Favorite name already exists",
        "you can only remove your own favorites": "❌ You can only delete your own favorites"
    }
    
    # Check for partial matches first
    for key, value in error_map.items():
        if key in error.lower():
            return value
    
    # Default format for other errors
    return f"❌ Error: {error}"