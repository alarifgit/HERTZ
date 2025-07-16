# hertz/utils/responses.py
"""Custom response messages with simple, clean language"""

class Responses:
    """Container for HERTZ response messages"""
    
    # Success messages
    TRACK_ADDED = "🎵 Track added to queue"
    TRACKS_ADDED = "🎵 {} tracks added to queue"
    QUEUE_CLEARED = "🧹 Queue cleared"
    FAVORITE_CREATED = "💾 Favorite saved"
    FAVORITE_REMOVED = "🗑️ Favorite deleted"
    TRACK_MOVED = "↕️ Track moved in queue"
    VOLUME_SET = "🔊 Volume set to {}%"
    
    # Status messages
    PAUSED = "⏸️ Paused"
    RESUMED = "▶️ Resumed"
    SKIPPED = "⏭️ Skipped"
    PREVIOUS = "⏮️ Previous track"
    LOOPING = "🔁 Track loop enabled"
    LOOP_STOPPED = "⏹️ Track loop disabled"
    QUEUE_LOOPING = "🔄 Queue loop enabled"
    QUEUE_LOOP_STOPPED = "⏹️ Queue loop disabled"
    SHUFFLED = "🔀 Queue shuffled"
    SEEKED = "⏩ Seeked to {}"
    REPLAYED = "🔄 Track restarted"
    DISCONNECTED = "🔌 Disconnected"
    STOPPED = "⏹️ Stopped"
    
    # Configuration messages
    CONFIG_UPDATED = "⚙️ Setting updated: {}"
    
    # Playback messages for song advancement
    NOW_PLAYING = "🎧 Now playing: {}"
    NEXT_TRACK = "⏭️ Next: {}"
    
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