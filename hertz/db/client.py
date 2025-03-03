# hertz/db/client.py
import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float, select, func, delete, update

logger = logging.getLogger(__name__)

# Base class for SQLAlchemy models
Base = declarative_base()

# Database models
class Setting(Base):
    __tablename__ = 'settings'
    
    guildId = Column(String, primary_key=True)
    playlistLimit = Column(Integer, default=50)
    secondsToWaitAfterQueueEmpties = Column(Integer, default=30)
    leaveIfNoListeners = Column(Boolean, default=True)
    queueAddResponseEphemeral = Column(Boolean, default=False)
    autoAnnounceNextSong = Column(Boolean, default=False)
    defaultVolume = Column(Integer, default=100)
    defaultQueuePageSize = Column(Integer, default=10)
    turnDownVolumeWhenPeopleSpeak = Column(Boolean, default=False)
    turnDownVolumeWhenPeopleSpeakTarget = Column(Integer, default=20)
    createdAt = Column(DateTime, default=datetime.utcnow)
    updatedAt = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    async def save(self):
        """Save changes to the database"""
        async with (await get_session()) as session:
            session.add(self)
            await session.commit()
            await session.refresh(self)

class FavoriteQuery(Base):
    __tablename__ = 'favorite_queries'
    
    id = Column(Integer, primary_key=True)
    guildId = Column(String, nullable=False)
    authorId = Column(String, nullable=False)
    name = Column(String, nullable=False)
    query = Column(String, nullable=False)
    createdAt = Column(DateTime, default=datetime.utcnow)
    updatedAt = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    async def save(self):
        """Save changes to the database"""
        async with (await get_session()) as session:
            session.add(self)
            await session.commit()
            await session.refresh(self)

class FileCache(Base):
    __tablename__ = 'file_caches'
    
    hash = Column(String, primary_key=True)
    bytes = Column(Integer, nullable=False)
    accessedAt = Column(DateTime, nullable=False)
    createdAt = Column(DateTime, default=datetime.utcnow)
    updatedAt = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    async def save(self):
        """Save changes to the database"""
        async with (await get_session()) as session:
            session.add(self)
            await session.commit()
            await session.refresh(self)

class KeyValueCache(Base):
    __tablename__ = 'key_value_caches'
    
    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)
    expiresAt = Column(DateTime, nullable=False)
    createdAt = Column(DateTime, default=datetime.utcnow)
    updatedAt = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    async def save(self):
        """Save changes to the database"""
        async with (await get_session()) as session:
            session.add(self)
            await session.commit()
            await session.refresh(self)

# Database engine and session
_engine = None
_async_session = None

async def get_engine():
    """Get or create SQLAlchemy engine"""
    global _engine
    
    if _engine is None:
        # Get database path
        data_dir = os.environ.get("DATA_DIR", "/data")
        os.makedirs(data_dir, exist_ok=True)
        db_path = os.path.join(data_dir, "db.sqlite")
        
        # Create engine
        database_url = f"sqlite+aiosqlite:///{db_path}"
        logger.info(f"Creating database engine with URL: {database_url}")
        _engine = create_async_engine(database_url, echo=False)
    
    return _engine

async def get_session() -> AsyncSession:
    """Get SQLAlchemy session"""
    global _async_session
    
    if _async_session is None:
        engine = await get_engine()
        _async_session = sessionmaker(
            engine, expire_on_commit=False, class_=AsyncSession
        )
    
    return _async_session()

async def initialize_db():
    """Initialize database and create tables if needed"""
    logger.info("Initializing database...")
    
    try:
        # Get engine and create tables
        engine = await get_engine()
        
        # Explicitly create all tables - THIS IS THE CRITICAL CHANGE
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
        logger.info("Database tables created successfully")
        
        # Test database connection and tables
        async with (await get_session()) as session:
            try:
                # Try a simple query to verify tables exist
                test_query = select(Setting).limit(1)
                await session.execute(test_query)
                logger.info("Database connection verified")
            except Exception as e:
                logger.error(f"Database test query failed: {e}")
                raise
        
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

async def get_guild_settings(guild_id: str) -> Setting:
    """Get settings for a guild, creating defaults if needed"""
    async with (await get_session()) as session:
        # Try to get existing settings
        result = await session.execute(
            select(Setting).where(Setting.guildId == guild_id)
        )
        settings = result.scalars().first()
        
        # Create new settings if not found
        if not settings:
            logger.info(f"Creating default settings for guild {guild_id}")
            settings = Setting(guildId=guild_id)
            session.add(settings)
            await session.commit()
            await session.refresh(settings)
        
        return settings

async def create_favorite_query(guild_id: str, author_id: str, name: str, query: str) -> FavoriteQuery:
    """Create a new favorite query"""
    async with (await get_session()) as session:
        favorite = FavoriteQuery(
            guildId=guild_id,
            authorId=author_id,
            name=name,
            query=query
        )
        session.add(favorite)
        await session.commit()
        await session.refresh(favorite)
        return favorite

async def get_favorite_queries(guild_id: str) -> List[FavoriteQuery]:
    """Get all favorite queries for a guild"""
    async with (await get_session()) as session:
        result = await session.execute(
            select(FavoriteQuery).where(FavoriteQuery.guildId == guild_id)
        )
        return list(result.scalars().all())

async def get_favorite_query(guild_id: str, name: str) -> Optional[FavoriteQuery]:
    """Get a specific favorite query by name"""
    async with (await get_session()) as session:
        result = await session.execute(
            select(FavoriteQuery).where(
                FavoriteQuery.guildId == guild_id,
                FavoriteQuery.name == name
            )
        )
        return result.scalars().first()

async def delete_favorite_query(query_id: int) -> None:
    """Delete a favorite query by ID"""
    async with (await get_session()) as session:
        favorite = await session.get(FavoriteQuery, query_id)
        if favorite:
            await session.delete(favorite)
            await session.commit()

# File cache operations
async def get_file_cache(hash_key: str) -> Optional[FileCache]:
    """Get a file cache entry by hash"""
    async with (await get_session()) as session:
        cache = await session.get(FileCache, hash_key)
        if cache:
            # Update accessed time
            cache.accessedAt = datetime.utcnow()
            await session.commit()
        return cache

async def create_file_cache(hash_key: str, size: int) -> FileCache:
    """Create a new file cache entry"""
    async with (await get_session()) as session:
        cache = FileCache(
            hash=hash_key,
            bytes=size,
            accessedAt=datetime.utcnow()
        )
        session.add(cache)
        await session.commit()
        await session.refresh(cache)
        return cache

async def remove_file_cache(hash_key: str) -> None:
    """Remove a file cache entry from the database"""
    async with (await get_session()) as session:
        cache = await session.get(FileCache, hash_key)
        if cache:
            await session.delete(cache)
            await session.commit()

async def get_total_cache_size() -> int:
    """Get the total size of all cached files in bytes"""
    async with (await get_session()) as session:
        result = await session.execute(
            select(func.sum(FileCache.bytes))
        )
        return result.scalar() or 0

async def get_oldest_file_caches(limit: int = 10) -> List[FileCache]:
    """Get the oldest file cache entries by access time"""
    async with (await get_session()) as session:
        result = await session.execute(
            select(FileCache).order_by(FileCache.accessedAt).limit(limit)
        )
        return list(result.scalars().all())

# Key-value cache operations
async def get_key_value(key: str) -> Optional[str]:
    """Get a value from the key-value cache"""
    async with (await get_session()) as session:
        cache = await session.get(KeyValueCache, key)
        
        if not cache:
            return None
            
        # Check if expired
        if cache.expiresAt < datetime.utcnow():
            await session.delete(cache)
            await session.commit()
            return None
            
        return cache.value

async def set_key_value(key: str, value: str, ttl: int) -> None:
    """Set a value in the key-value cache"""
    async with (await get_session()) as session:
        # Check if key exists
        cache = await session.get(KeyValueCache, key)
        
        expires_at = datetime.utcnow().replace(microsecond=0) + timedelta(seconds=ttl)
        
        if cache:
            # Update existing
            cache.value = value
            cache.expiresAt = expires_at
        else:
            # Create new
            cache = KeyValueCache(
                key=key,
                value=value,
                expiresAt=expires_at
            )
            session.add(cache)
            
        await session.commit()

async def cleanup_expired_key_value_cache() -> int:
    """Remove all expired key-value cache entries"""
    async with (await get_session()) as session:
        result = await session.execute(
            delete(KeyValueCache).where(KeyValueCache.expiresAt < datetime.utcnow())
        )
        await session.commit()
        return result.rowcount

async def get_recent_file_caches(limit: int = 5) -> List[FileCache]:
    """Get the most recently accessed file cache entries"""
    async with (await get_session()) as session:
        result = await session.execute(
            select(FileCache).order_by(FileCache.accessedAt.desc()).limit(limit)
        )
        return list(result.scalars().all())