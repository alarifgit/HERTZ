# hertz/utils/error_msg.py
"""Utility for generating error messages with the HERTZ personality"""

def error_msg(error: str = None) -> str:
    """
    Format an error message with HERTZ audio-engineer personality
    
    Args:
        error: Error message or None
        
    Returns:
        Formatted error message
    """
    if not error:
        return "🔇 Signal loss: Unknown error"
        
    if isinstance(error, Exception):
        error = str(error)
    
    # Common error messages with custom formatting
    error_map = {
        "not connected": "🔌 No connection to voice channel",
        "not currently playing": "⚠️ No audio signal detected",
        "nothing is playing": "⚠️ No audio signal detected",
        "gotta be in a voice channel": "🎧 You need to be in a voice channel",
        "you need to be in a voice channel": "🎧 You need to be in a voice channel",
        "nothing to play": "📂 Playlist empty. Add some tracks first",
        "nothing is currently playing": "📂 Playlist empty. Add some tracks first",
        "no song to loop": "⚠️ Cannot amplify: No signal to loop",
        "no songs to loop": "⚠️ Cannot amplify: No signal to loop",
        "no track to loop": "⚠️ Cannot amplify: No signal to loop",
        "no tracks to loop": "⚠️ Cannot amplify: No signal to loop",
        "not enough songs to loop a queue": "⚠️ Need more tracks to engage queue loop",
        "not enough tracks to loop a queue": "⚠️ Need more tracks to engage queue loop",
        "no favorite with that name exists": "⚠️ Frequency not found in favorites",
        "invalid limit": "⚠️ Invalid parameter: Limit out of range",
        "position must be at least 1": "⚠️ Track position must be at least 1",
        "range must be at least 1": "⚠️ Range must be at least 1",
        "no song to skip to": "⚠️ End of playlist reached",
        "no track to skip to": "⚠️ End of playlist reached",
        "no song to go back to": "⚠️ Already at the first track",
        "no track to go back to": "⚠️ Already at the first track",
        "can't seek in a livestream": "⚠️ Cannot seek in livestream signal",
        "can't seek past the end of the song": "⚠️ Seek position beyond track duration",
        "can't seek past the end of the track": "⚠️ Seek position beyond track duration",
        "queue is empty": "📂 Playlist empty. Add some tracks first",
        "not enough songs to shuffle": "⚠️ Need more tracks to shuffle",
        "not enough tracks to shuffle": "⚠️ Need more tracks to shuffle",
        "no songs found": "🔍 No matching signals found. Try different search terms.",
        "no tracks found": "🔍 No matching signals found. Try different search terms.",
        "a favorite with that name already exists": "⚠️ Frequency preset name already in use. Choose a different name.",
        "you can only remove your own favorites": "🔒 Access denied: You can only delete your own frequency presets."
    }
    
    # Check for partial matches first
    for key, value in error_map.items():
        if key in error.lower():
            return value
    
    # Default format for other errors
    return f"🔇 Signal distortion: {error}"