# hertz/config.py
import os
import logging
from typing import Optional, Dict, Any, List
from enum import Enum
from pathlib import Path
import re

# Configure logger
logger = logging.getLogger(__name__)

class ActivityType(str, Enum):
    """Discord bot activity types"""
    PLAYING = "PLAYING"
    LISTENING = "LISTENING"
    WATCHING = "WATCHING"
    STREAMING = "STREAMING"
    COMPETING = "COMPETING"

class Status(str, Enum):
    """Discord bot status options"""
    ONLINE = "online"
    IDLE = "idle"
    DND = "dnd"
    INVISIBLE = "invisible"

class Config:
    """
    Configuration class for HERTZ Discord bot.
    Loads settings from environment variables with sensible defaults.
    """
    # Default locations
    DEFAULT_DATA_DIR = "/data"
    
    def __init__(self):
        # Required configuration - will raise error if not provided
        self.DISCORD_TOKEN = self._get_required_env("DISCORD_TOKEN")
        self.YOUTUBE_API_KEY = self._get_required_env("YOUTUBE_API_KEY")
        
        # Optional integrations
        self.SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
        self.SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
        
        # Data directories
        self.DATA_DIR = os.environ.get("DATA_DIR", self.DEFAULT_DATA_DIR)
        self.CACHE_DIR = os.environ.get("CACHE_DIR", os.path.join(self.DATA_DIR, "cache"))
        
        # Cache settings
        self.CACHE_LIMIT = os.environ.get("CACHE_LIMIT", "2GB")
        self.cache_limit_bytes = self._parse_size(self.CACHE_LIMIT)
        
        # Bot appearance
        self.BOT_STATUS = self._parse_status(os.environ.get("BOT_STATUS", "online"))
        self.BOT_ACTIVITY_TYPE = self._parse_activity_type(os.environ.get("BOT_ACTIVITY_TYPE", "LISTENING"))
        self.BOT_ACTIVITY = os.environ.get("BOT_ACTIVITY", "music")
        self.BOT_ACTIVITY_URL = os.environ.get("BOT_ACTIVITY_URL", None)
        
        # Command registration settings
        self.TEST_GUILDS = self._parse_test_guilds(os.environ.get("TEST_GUILDS", ""))
        
        # Debugging and logging
        self.DEBUG = os.environ.get("DEBUG", "false").lower() in ("true", "1", "yes")
        self.LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
        
        # Connection and retry settings
        self.CONNECTION_TIMEOUT = int(os.environ.get("CONNECTION_TIMEOUT", "30"))
        self.MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "3"))
        self.RETRY_DELAY = int(os.environ.get("RETRY_DELAY", "5"))
        
        # Audio quality settings
        self.AUDIO_BITRATE = int(os.environ.get("AUDIO_BITRATE", "128"))
        self.ENABLE_AUDIO_CACHE = os.environ.get("ENABLE_AUDIO_CACHE", "true").lower() in ("true", "1", "yes")
        
        # Performance settings
        self.CONCURRENT_DOWNLOADS = int(os.environ.get("CONCURRENT_DOWNLOADS", "4"))
        self.API_RATE_LIMIT = int(os.environ.get("API_RATE_LIMIT", "100"))  # requests per minute
        
        # Health check settings
        self.HEALTH_CHECK_INTERVAL = int(os.environ.get("HEALTH_CHECK_INTERVAL", "60"))
        self.VOICE_CLIENT_TIMEOUT = int(os.environ.get("VOICE_CLIENT_TIMEOUT", "300"))  # 5 minutes
        
        # Auto-recovery settings
        self.AUTO_RECOVERY_ENABLED = os.environ.get("AUTO_RECOVERY_ENABLED", "true").lower() in ("true", "1", "yes")
        self.MAX_RECOVERY_ATTEMPTS = int(os.environ.get("MAX_RECOVERY_ATTEMPTS", "3"))
        
        # Network optimization
        self.ENABLE_CONNECTION_POOLING = os.environ.get("ENABLE_CONNECTION_POOLING", "true").lower() in ("true", "1", "yes")
        self.CONNECTION_POOL_SIZE = int(os.environ.get("CONNECTION_POOL_SIZE", "10"))
        
        # Verify and create directories
        self._verify_directories()
        
        # Log configuration summary
        self._log_config()
    
    def _get_required_env(self, name: str) -> str:
        """Get a required environment variable or raise an error"""
        value = os.environ.get(name)
        if not value:
            error_msg = f"❌ CRITICAL: {name} environment variable is required"
            logger.error(error_msg)
            raise ValueError(error_msg)
        return value
    
    def _parse_size(self, size_str: str) -> int:
        """Parse a string like '2GB' into bytes"""
        units = {
            "B": 1,
            "KB": 1024,
            "MB": 1024**2,
            "GB": 1024**3,
            "TB": 1024**4
        }
        
        # Use regex to extract number and unit
        match = re.match(r"^([\d.]+)([KMGT]?B)?$", size_str.upper())
        if not match:
            logger.warning(f"Invalid size format: {size_str}, using default of 2GB")
            return 2 * 1024**3
        
        number, unit = match.groups()
        number = float(number)
        unit = unit or "B"  # Default to bytes if no unit specified
        
        return int(number * units.get(unit, 1))
    
    def _parse_status(self, status_str: str) -> Status:
        """Parse and validate bot status"""
        try:
            return Status(status_str.lower())
        except ValueError:
            logger.warning(f"Invalid status: {status_str}, using default of 'online'")
            return Status.ONLINE
    
    def _parse_activity_type(self, activity_str: str) -> ActivityType:
        """Parse and validate bot activity type"""
        try:
            return ActivityType(activity_str.upper())
        except ValueError:
            logger.warning(f"Invalid activity type: {activity_str}, using default of 'LISTENING'")
            return ActivityType.LISTENING
    
    def _parse_test_guilds(self, guilds_str: str) -> List[int]:
        """Parse comma-separated guild IDs"""
        if not guilds_str:
            return []
        
        try:
            return [int(guild_id.strip()) for guild_id in guilds_str.split(",") if guild_id.strip()]
        except ValueError:
            logger.warning(f"Invalid test guilds format: {guilds_str}, must be comma-separated IDs")
            return []
    
    def _verify_directories(self):
        """Verify that necessary directories exist, create if they don't"""
        for directory in [self.DATA_DIR, self.CACHE_DIR, os.path.join(self.CACHE_DIR, "tmp")]:
            os.makedirs(directory, exist_ok=True)
    
    def _log_config(self):
        """Log configuration settings at startup"""
        if not logger.isEnabledFor(logging.DEBUG):
            return
            
        logger.debug("HERTZ Configuration:")
        logger.debug(f"- Data directory: {self.DATA_DIR}")
        logger.debug(f"- Cache directory: {self.CACHE_DIR}")
        logger.debug(f"- Cache limit: {self.CACHE_LIMIT} ({self.cache_limit_bytes} bytes)")
        logger.debug(f"- Bot status: {self.BOT_STATUS}")
        logger.debug(f"- Bot activity: {self.BOT_ACTIVITY_TYPE} {self.BOT_ACTIVITY}")
        logger.debug(f"- Connection timeout: {self.CONNECTION_TIMEOUT}s")
        logger.debug(f"- Max retries: {self.MAX_RETRIES}")
        logger.debug(f"- Audio bitrate: {self.AUDIO_BITRATE}kbps")
        logger.debug(f"- Audio cache: {'enabled' if self.ENABLE_AUDIO_CACHE else 'disabled'}")
        logger.debug(f"- Auto recovery: {'enabled' if self.AUTO_RECOVERY_ENABLED else 'disabled'}")
        
        if self.SPOTIFY_CLIENT_ID and self.SPOTIFY_CLIENT_SECRET:
            logger.debug("- Spotify integration: Enabled")
        else:
            logger.debug("- Spotify integration: Disabled")
            
        if self.TEST_GUILDS:
            logger.debug(f"- Test guilds: {', '.join(map(str, self.TEST_GUILDS))}")

def load_config() -> Config:
    """Load configuration from environment variables"""
    return Config()