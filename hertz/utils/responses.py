# hertz/utils/responses.py
"""Custom response messages with HERTZ audio-engineer personality"""

class Responses:
    """Container for HERTZ response messages"""
    
    # Success messages
    TRACK_ADDED = "🎵 Signal received! Track added to queue"
    TRACKS_ADDED = "🎵 Signal received! {} tracks added to queue"
    QUEUE_CLEARED = "🧹 Playlist cleared. Channels silent."
    FAVORITE_CREATED = "💾 Frequency saved! Added to favorites"
    FAVORITE_REMOVED = "🗑️ Frequency deleted from favorites"
    TRACK_MOVED = "↕️ Track repositioned in queue"
    VOLUME_SET = "🔊 Audio levels calibrated to {}%"
    
    # Status messages
    PAUSED = "⏸️ Track paused. Signal on standby."
    RESUMED = "▶️ Signal live. Resuming transmission."
    SKIPPED = "⏭️ Signal forwarded to next track"
    PREVIOUS = "⏮️ Signal reversed to previous track"
    LOOPING = "🔁 Track loop enabled"
    LOOP_STOPPED = "⏹️ Loop disengaged"
    QUEUE_LOOPING = "🔄 Queue loop enabled"
    QUEUE_LOOP_STOPPED = "⏹️ Queue loop disabled"
    SHUFFLED = "🔀 Playlist frequencies randomized"
    SEEKED = "⏩ Signal seeked to {}"
    REPLAYED = "🔄 Restarting current track"
    DISCONNECTED = "🔌 Connection terminated. Signal offline."
    STOPPED = "⏹️ Playback terminated. All channels cleared."
    
    # Configuration messages
    CONFIG_UPDATED = "⚙️ Configuration updated: {}"
    
    # Playback messages for song advancement
    NOW_PLAYING = "🎧 Now transmitting: {}"
    NEXT_TRACK = "⏭️ Next in queue: {}"
    
    @staticmethod
    def track_added(title: str, position: str = "", extra: str = "", skipped: bool = False) -> str:
        """Format message for track added to queue"""
        position_text = f" to the {position} of" if position else ""
        skip_text = " and current track skipped" if skipped else ""
        extra_text = f" ({extra})" if extra else ""
        
        return f"🎵 Signal received! **{title}** added{position_text} the queue{skip_text}{extra_text}"
    
    @staticmethod
    def tracks_added(first_title: str, count: int, position: str = "", extra: str = "", skipped: bool = False) -> str:
        """Format message for multiple tracks added to queue"""
        position_text = f" to the {position} of" if position else ""
        skip_text = " and current track skipped" if skipped else ""
        extra_text = f" ({extra})" if extra else ""
        
        return f"🎵 Signal received! **{first_title}** and {count} other tracks added{position_text} the queue{skip_text}{extra_text}"