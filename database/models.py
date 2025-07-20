"""
Database models for HERTZ bot
SQLAlchemy models for storing bot data
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, Float, ForeignKey, Index
from sqlalchemy.orm import relationship
from database.connection import Base

class Guild(Base):
    """Guild (server) settings and configuration."""
    
    __tablename__ = 'guilds'
    
    id = Column(String, primary_key=True)  # Discord guild ID
    name = Column(String, nullable=False)
    
    # Settings
    default_volume = Column(Integer, default=50)
    auto_disconnect = Column(Boolean, default=True)
    auto_disconnect_delay = Column(Integer, default=300)  # seconds
    max_queue_size = Column(Integer, default=1000)
    
    # Permissions
    dj_role_id = Column(String, nullable=True)
    music_channel_id = Column(String, nullable=True)
    
    # Statistics
    total_songs_played = Column(Integer, default=0)
    total_play_time = Column(Integer, default=0)  # seconds
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_activity = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    queued_tracks = relationship("QueuedTrack", back_populates="guild", cascade="all, delete-orphan")
    play_history = relationship("PlayHistory", back_populates="guild", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Guild(id={self.id}, name={self.name})>"

class QueuedTrack(Base):
    """Tracks in guild music queues."""
    
    __tablename__ = 'queued_tracks'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String, ForeignKey('guilds.id'), nullable=False)
    
    # Track information
    title = Column(String, nullable=False)
    artist = Column(String, nullable=True)
    url = Column(String, nullable=False)
    thumbnail_url = Column(String, nullable=True)
    duration = Column(Integer, nullable=True)  # seconds
    
    # Queue information
    position = Column(Integer, nullable=False)
    requested_by_id = Column(String, nullable=False)  # Discord user ID
    requested_by_name = Column(String, nullable=False)
    
    # Source information
    source = Column(String, nullable=False)  # youtube, spotify, etc.
    source_id = Column(String, nullable=True)  # original platform ID
    
    # Timestamps
    added_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    guild = relationship("Guild", back_populates="queued_tracks")
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_guild_position', 'guild_id', 'position'),
        Index('idx_guild_added', 'guild_id', 'added_at'),
    )
    
    def __repr__(self):
        return f"<QueuedTrack(id={self.id}, title={self.title}, guild_id={self.guild_id})>"

class UserFavorite(Base):
    """User's favorite tracks."""
    
    __tablename__ = 'user_favorites'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False)  # Discord user ID
    user_name = Column(String, nullable=False)
    
    # Track information
    title = Column(String, nullable=False)
    artist = Column(String, nullable=True)
    url = Column(String, nullable=False)
    thumbnail_url = Column(String, nullable=True)
    duration = Column(Integer, nullable=True)  # seconds
    
    # Source information
    source = Column(String, nullable=False)
    source_id = Column(String, nullable=True)
    
    # Statistics
    play_count = Column(Integer, default=0)
    last_played = Column(DateTime, nullable=True)
    
    # Timestamps
    added_at = Column(DateTime, default=datetime.utcnow)
    
    # Indexes
    __table_args__ = (
        Index('idx_user_favorites', 'user_id', 'added_at'),
        Index('idx_user_play_count', 'user_id', 'play_count'),
    )
    
    def __repr__(self):
        return f"<UserFavorite(id={self.id}, title={self.title}, user_id={self.user_id})>"

class PlayHistory(Base):
    """History of played tracks per guild."""
    
    __tablename__ = 'play_history'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String, ForeignKey('guilds.id'), nullable=False)
    
    # Track information
    title = Column(String, nullable=False)
    artist = Column(String, nullable=True)
    url = Column(String, nullable=False)
    thumbnail_url = Column(String, nullable=True)
    duration = Column(Integer, nullable=True)  # seconds
    
    # Play information
    requested_by_id = Column(String, nullable=False)
    requested_by_name = Column(String, nullable=False)
    played_at = Column(DateTime, default=datetime.utcnow)
    play_duration = Column(Integer, nullable=True)  # How long it actually played
    skipped = Column(Boolean, default=False)
    
    # Source information
    source = Column(String, nullable=False)
    source_id = Column(String, nullable=True)
    
    # Relationships
    guild = relationship("Guild", back_populates="play_history")
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_guild_played_at', 'guild_id', 'played_at'),
        Index('idx_user_history', 'requested_by_id', 'played_at'),
    )
    
    def __repr__(self):
        return f"<PlayHistory(id={self.id}, title={self.title}, guild_id={self.guild_id})>"

class CachedTrack(Base):
    """Cache information for downloaded tracks."""
    
    __tablename__ = 'cached_tracks'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Track identification
    url_hash = Column(String, unique=True, nullable=False)  # Hash of original URL
    original_url = Column(String, nullable=False)
    
    # File information
    file_path = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)  # bytes
    file_format = Column(String, nullable=False)  # mp3, webm, etc.
    
    # Track metadata
    title = Column(String, nullable=True)
    artist = Column(String, nullable=True)
    duration = Column(Integer, nullable=True)
    
    # Cache information
    access_count = Column(Integer, default=0)
    last_accessed = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    
    # Quality information
    bitrate = Column(Integer, nullable=True)
    sample_rate = Column(Integer, nullable=True)
    
    # Indexes
    __table_args__ = (
        Index('idx_url_hash', 'url_hash'),
        Index('idx_last_accessed', 'last_accessed'),
        Index('idx_expires_at', 'expires_at'),
    )
    
    def __repr__(self):
        return f"<CachedTrack(id={self.id}, url_hash={self.url_hash}, file_path={self.file_path})>"

class Playlist(Base):
    """User-created playlists."""
    
    __tablename__ = 'playlists'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Playlist information
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    
    # Owner information
    owner_id = Column(String, nullable=False)  # Discord user ID
    owner_name = Column(String, nullable=False)
    guild_id = Column(String, nullable=True)  # Optional guild association
    
    # Settings
    is_public = Column(Boolean, default=False)
    
    # Statistics
    play_count = Column(Integer, default=0)
    track_count = Column(Integer, default=0)
    total_duration = Column(Integer, default=0)  # seconds
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_played = Column(DateTime, nullable=True)
    
    # Relationships
    tracks = relationship("PlaylistTrack", back_populates="playlist", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index('idx_owner_playlists', 'owner_id', 'created_at'),
        Index('idx_guild_playlists', 'guild_id', 'is_public'),
    )
    
    def __repr__(self):
        return f"<Playlist(id={self.id}, name={self.name}, owner_id={self.owner_id})>"

class PlaylistTrack(Base):
    """Tracks within playlists."""
    
    __tablename__ = 'playlist_tracks'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    playlist_id = Column(Integer, ForeignKey('playlists.id'), nullable=False)
    
    # Track information
    title = Column(String, nullable=False)
    artist = Column(String, nullable=True)
    url = Column(String, nullable=False)
    thumbnail_url = Column(String, nullable=True)
    duration = Column(Integer, nullable=True)  # seconds
    
    # Playlist position
    position = Column(Integer, nullable=False)
    
    # Source information
    source = Column(String, nullable=False)
    source_id = Column(String, nullable=True)
    
    # Added information
    added_by_id = Column(String, nullable=False)
    added_by_name = Column(String, nullable=False)
    added_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    playlist = relationship("Playlist", back_populates="tracks")
    
    # Indexes
    __table_args__ = (
        Index('idx_playlist_position', 'playlist_id', 'position'),
    )
    
    def __repr__(self):
        return f"<PlaylistTrack(id={self.id}, title={self.title}, playlist_id={self.playlist_id})>"