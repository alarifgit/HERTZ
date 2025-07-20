"""
Configuration management for HERTZ bot
Handles environment variables, validation, and logging setup
"""

import os
import logging
import logging.handlers
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

@dataclass
class Config:
    """Configuration data class for HERTZ bot."""
    
    # Discord
    discord_token: str
    register_commands_on_bot: bool
    
    # APIs
    youtube_api_key: Optional[str]
    spotify_client_id: Optional[str]
    spotify_client_secret: Optional[str]
    
    # Database
    database_url: str
    
    # Cache settings
    cache_enabled: bool
    cache_size_mb: int
    cache_ttl_hours: int
    cache_dir: str
    
    # Audio settings
    default_volume: int
    max_queue_size: int
    max_track_duration: int
    
    # Bot behavior
    auto_disconnect: bool
    auto_disconnect_delay: int
    
    # Logging
    log_level: str
    log_to_file: bool
    log_rotation: bool
    
    # Performance
    max_guilds: int
    max_concurrent_downloads: int
    
    # Health monitoring
    health_check_enabled: bool
    health_check_port: int
    
    # Bot status
    bot_activity_type: str
    bot_activity: str
    bot_status: str
    
    @property
    def has_youtube_api(self) -> bool:
        """Check if YouTube API is configured."""
        return bool(self.youtube_api_key)
    
    @property
    def has_spotify(self) -> bool:
        """Check if Spotify is configured."""
        return bool(self.spotify_client_id and self.spotify_client_secret)
    
    @property
    def cache_limit_bytes(self) -> int:
        """Get cache limit in bytes."""
        return self.cache_size_mb * 1024 * 1024
    
    def validate(self):
        """Validate configuration values."""
        if not self.discord_token:
            raise ValueError("DISCORD_TOKEN is required")
        
        if self.default_volume < 0 or self.default_volume > 100:
            raise ValueError("DEFAULT_VOLUME must be between 0 and 100")
        
        if self.max_queue_size < 1:
            raise ValueError("MAX_QUEUE_SIZE must be at least 1")
        
        if self.cache_size_mb < 100:
            raise ValueError("CACHE_SIZE_MB must be at least 100")

def get_bool(key: str, default: bool = False) -> bool:
    """Get boolean value from environment."""
    value = os.getenv(key, str(default)).lower()
    return value in ('true', '1', 'yes', 'on')

def get_int(key: str, default: int) -> int:
    """Get integer value from environment."""
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default

def get_config() -> Config:
    """Get configuration from environment variables."""
    
    # Required settings
    discord_token = os.getenv('DISCORD_TOKEN')
    if not discord_token:
        raise ValueError("DISCORD_TOKEN environment variable is required")
    
    # Optional API keys
    youtube_api_key = os.getenv('YOUTUBE_API_KEY')
    spotify_client_id = os.getenv('SPOTIFY_CLIENT_ID')
    spotify_client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
    
    # Create data directory
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    
    cache_dir = Path("cache")
    cache_dir.mkdir(exist_ok=True)
    
    config = Config(
        # Discord
        discord_token=discord_token,
        register_commands_on_bot=get_bool('REGISTER_COMMANDS_ON_BOT', True),
        
        # APIs
        youtube_api_key=youtube_api_key,
        spotify_client_id=spotify_client_id,
        spotify_client_secret=spotify_client_secret,
        
        # Database
        database_url=os.getenv('DATABASE_URL', f'sqlite:///{data_dir}/hertz.db'),
        
        # Cache
        cache_enabled=get_bool('CACHE_ENABLED', True),
        cache_size_mb=get_int('CACHE_SIZE_MB', 2048),
        cache_ttl_hours=get_int('CACHE_TTL_HOURS', 24),
        cache_dir=str(cache_dir),
        
        # Audio
        default_volume=get_int('DEFAULT_VOLUME', 50),
        max_queue_size=get_int('MAX_QUEUE_SIZE', 1000),
        max_track_duration=get_int('MAX_TRACK_DURATION', 3600),
        
        # Bot behavior
        auto_disconnect=get_bool('AUTO_DISCONNECT', True),
        auto_disconnect_delay=get_int('AUTO_DISCONNECT_DELAY', 300),
        
        # Logging
        log_level=os.getenv('LOG_LEVEL', 'INFO').upper(),
        log_to_file=get_bool('LOG_TO_FILE', True),
        log_rotation=get_bool('LOG_ROTATION', True),
        
        # Performance
        max_guilds=get_int('MAX_GUILDS', 1000),
        max_concurrent_downloads=get_int('MAX_CONCURRENT_DOWNLOADS', 5),
        
        # Health monitoring
        health_check_enabled=get_bool('HEALTH_CHECK_ENABLED', True),
        health_check_port=get_int('HEALTH_CHECK_PORT', 8080),
        
        # Bot status
        bot_activity_type=os.getenv('BOT_ACTIVITY_TYPE', 'listening'),
        bot_activity=os.getenv('BOT_ACTIVITY', 'music'),
        bot_status=os.getenv('BOT_STATUS', 'online'),
    )
    
    # Validate configuration
    config.validate()
    
    return config

def setup_logging():
    """Setup logging configuration."""
    config = get_config()
    
    # Create logs directory
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.log_level))
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(logging.INFO)  # Console gets INFO and above
    root_logger.addHandler(console_handler)
    
    # File handler (if enabled)
    if config.log_to_file:
        file_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)-30s | %(funcName)-20s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        if config.log_rotation:
            # Rotating file handler
            file_handler = logging.handlers.RotatingFileHandler(
                log_dir / "hertz.log",
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=5,
                encoding='utf-8'
            )
        else:
            # Regular file handler
            file_handler = logging.FileHandler(
                log_dir / "hertz.log",
                encoding='utf-8'
            )
        
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(logging.DEBUG)  # File gets all messages
        root_logger.addHandler(file_handler)
    
    # Error file handler (always enabled)
    error_handler = logging.FileHandler(
        log_dir / "errors.log",
        encoding='utf-8'
    )
    error_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)-30s | %(funcName)-20s | %(message)s\n%(exc_info)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    error_handler.setFormatter(error_formatter)
    error_handler.setLevel(logging.ERROR)
    root_logger.addHandler(error_handler)
    
    # Silence noisy loggers
    logging.getLogger('discord').setLevel(logging.WARNING)
    logging.getLogger('discord.http').setLevel(logging.WARNING)
    logging.getLogger('discord.gateway').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    logging.getLogger('yt_dlp').setLevel(logging.ERROR)
    
    # Log startup info
    logger = logging.getLogger(__name__)
    logger.info("=" * 50)
    logger.info("🎵 HERTZ Discord Music Bot")
    logger.info("=" * 50)
    logger.info(f"Log Level: {config.log_level}")
    logger.info(f"Log to File: {config.log_to_file}")
    logger.info(f"Log Rotation: {config.log_rotation}")
    logger.info(f"Cache Enabled: {config.cache_enabled}")
    logger.info(f"Cache Size: {config.cache_size_mb} MB")
    logger.info(f"YouTube API: {'Enabled' if config.has_youtube_api else 'Disabled'}")
    logger.info(f"Spotify: {'Enabled' if config.has_spotify else 'Disabled'}")
    logger.info(f"Health Check: {'Enabled' if config.health_check_enabled else 'Disabled'}")
    logger.info("=" * 50)

def create_directories():
    """Create necessary directories."""
    directories = [
        Path("data"),
        Path("logs"),
        Path("cache"),
        Path("backups")
    ]
    
    for directory in directories:
        directory.mkdir(exist_ok=True)
        
    # Create .gitkeep files to preserve directory structure
    for directory in directories:
        gitkeep = directory / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()

# Create directories on import
create_directories()