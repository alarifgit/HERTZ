# hertz/utils/responses.py
"""Response messages for HERTZ with professional, music-focused terminology"""

class Responses:
    """Container for HERTZ response messages"""
    
    # Success messages
    TRACK_ADDED = "🎵 Track added to queue"
    TRACKS_ADDED = "🎵 {} tracks added to queue"
    QUEUE_CLEARED = "🧹 Playlist cleared"
    FAVORITE_CREATED = "💾 Track saved to favorites"
    FAVORITE_REMOVED = "🗑️ Track removed from favorites"
    TRACK_MOVED = "↕️ Track repositioned in queue"
    VOLUME_SET = "🔊 Volume set to {}%"
    
    # Status messages
    PAUSED = "⏸️ Playback paused"
    RESUMED = "▶️ Playback resumed"
    SKIPPED = "⏭️ Skipped to next track"
    PREVIOUS = "⏮️ Returned to previous track"
    LOOPING = "🔁 Track loop enabled"
    LOOP_STOPPED = "⏹️ Track loop disabled"
    QUEUE_LOOPING = "🔄 Queue loop enabled"
    QUEUE_LOOP_STOPPED = "⏹️ Queue loop disabled"
    SHUFFLED = "🔀 Queue shuffled"
    SEEKED = "⏩ Seeked to {}"
    REPLAYED = "🔄 Restarting current track"
    DISCONNECTED = "🔌 Disconnected from voice channel"
    STOPPED = "⏹️ Playback stopped and queue cleared"
    
    # Configuration messages
    CONFIG_UPDATED = "⚙️ Settings updated: {}"
    
    # Playback messages for song advancement
    NOW_PLAYING = "🎧 Now playing: {}"
    NEXT_TRACK = "⏭️ Up next: {}"
    
    @staticmethod
    def track_added(title: str, position: str = "", extra: str = "", skipped: bool = False) -> str:
        """Format message for track added to queue"""
        position_text = f" to the {position} of" if position else ""
        skip_text = " and current track skipped" if skipped else ""
        extra_text = f" ({extra})" if extra else ""
        
        return f"🎵 **{title}** added{position_text} the queue{skip_text}{extra_text}"
    
    @staticmethod
    def tracks_added(first_title: str, count: int, position: str = "", extra: str = "", skipped: bool = False) -> str:
        """Format message for multiple tracks added to queue"""
        position_text = f" to the {position} of" if position else ""
        skip_text = " and current track skipped" if skipped else ""
        extra_text = f" ({extra})" if extra else ""
        
        return f"🎵 **{first_title}** and {count} other tracks added{position_text} the queue{skip_text}{extra_text}"