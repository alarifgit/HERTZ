# hertz/config.py
import os
from typing import Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, validator

TEST_GUILDS: str = os.environ.get('TEST_GUILDS', '')  # Comma-separated list of guild IDs

class ActivityType(str, Enum):
    PLAYING = "PLAYING"
    LISTENING = "LISTENING"
    WATCHING = "WATCHING"
    STREAMING = "STREAMING"

class Status(str, Enum):
    ONLINE = "online"
    IDLE = "idle"
    DND = "dnd"

class Config(BaseModel):
    # Required configuration
    DISCORD_TOKEN: str
    YOUTUBE_API_KEY: str
    
    # Optional configuration with defaults
    SPOTIFY_CLIENT_ID: Optional[str] = None
    SPOTIFY_CLIENT_SECRET: Optional[str] = None
    DATA_DIR: str = "/data"
    CACHE_DIR: Optional[str] = None
    CACHE_LIMIT: str = "2GB"
    BOT_STATUS: Status = Status.ONLINE
    BOT_ACTIVITY_TYPE: ActivityType = ActivityType.LISTENING
    BOT_ACTIVITY: str = "music"
    BOT_ACTIVITY_URL: Optional[str] = None
    
    # Validators to handle case insensitivity
    @validator('BOT_ACTIVITY_TYPE', pre=True)
    def uppercase_activity_type(cls, v):
        if isinstance(v, str):
            return v.upper()
        return v
    
    @validator('BOT_STATUS', pre=True)
    def lowercase_status(cls, v):
        if isinstance(v, str):
            return v.lower()
        return v
    
    # Settings with computed fields
    @property
    def cache_limit_bytes(self) -> int:
        """Convert cache limit string to bytes"""
        unit_map = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
        value = self.CACHE_LIMIT.upper()
        if value.endswith("B"):
            if value.endswith("KB") or value.endswith("MB") or value.endswith("GB") or value.endswith("TB"):
                number = float(value[:-2])
                unit = value[-2:]
            else:
                number = float(value[:-1])
                unit = value[-1:]
        else:
            # Default to MB if no unit specified
            number = float(value)
            unit = "MB"
        
        return int(number * unit_map.get(unit, 1))
    
    @validator('CACHE_DIR', pre=True, always=True)
    def set_cache_dir(cls, v, values):
        """Set cache directory if not provided"""
        if v is None and 'DATA_DIR' in values:
            return os.path.join(values['DATA_DIR'], 'cache')
        return v
    
    class Config:
        # Allow extra fields in case we add more config options later
        extra = "ignore"

def load_config() -> Config:
    """Load configuration from environment variables"""
    # Process environment variables with special handling for enums
    env_vars = {}
    
    for key, val in os.environ.items():
        # Only include fields that are part of our Config model
        if key in Config.__annotations__:
            # For enum fields, perform case conversion before validation
            if key == 'BOT_ACTIVITY_TYPE':
                env_vars[key] = val.upper() if val else val
            elif key == 'BOT_STATUS':
                env_vars[key] = val.lower() if val else val
            else:
                env_vars[key] = val
    
    # Create config object with processed environment variables
    return Config(**env_vars)