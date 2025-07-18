# hertz/db/client.py
import os
import asyncio
import logging
import contextlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, select, func, delete
from sqlalchemy.pool import StaticPool

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
        """Save changes to the database with proper session management"""
        async with get_session() as session:
            # Merge the object into the session
            merged = await session.merge(self)
            await session.flush()
            # Copy back any updated fields
            for column in self.__table__.columns:
                setattr(self, column.name, getattr(merged, column.name))

class FavoriteQuery(Base):
    __tablename__ = 'favorite_queries'
    
    id = Column(Integer, primary_key=True)
    guildId = Column(String, nullable=False)
    authorId = Column(String, nullable=False)
    name = Column(String, nullable=False)
    query = Column(String, nullable=False)
    createdAt = Column(DateTime, default=datetime.utcnow)
    updatedAt = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class FileCache(Base):
    __tablename__ = 'file_caches'
    
    hash = Column(String, primary_key=True)
    bytes = Column(Integer, nullable=False)
    accessedAt = Column(DateTime, nullable=False)
    createdAt = Column(DateTime, default=datetime.utcnow)
    updatedAt = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class KeyValueCache(Base):
    __tablename__ = 'key_value_caches'
    
    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)
    expiresAt = Column(DateTime, nullable=False)
    createdAt = Column(DateTime, default=datetime.utcnow)
    updatedAt = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# Database engine and session management
_engine = None
_session_factory = None
_session_lock = asyncio.Lock()

async def get_engine():
    """Get or create SQLAlchemy engine with proper connection pooling"""
    global _engine
    
    if _engine is None:
        # Get database path
        data_dir = os.environ.get("DATA_DIR", "/data")
        os.makedirs(data_dir, exist_ok=True)
        db_path = os.path.join(data_dir, "db.sqlite")
        
        # Create engine with proper SQLite settings
        database_url = f"sqlite+aiosqlite:///{db_path}"
        logger.info(f"Creating database engine: {database_url}")
        
        _engine = create_async_engine(
            database_url,
            echo=False,
            poolclass=StaticPool,
            connect_args={
                "check_same_thread": False,
                "timeout": 20
            },
            pool_pre_ping=True,
            pool_recycle=3600  # Recycle connections after 1 hour
        )
    
    return _engine

async def get_session_factory():
    """Get or create session factory"""
    global _session_factory
    
    if _session_factory is None:
        engine = await get_engine()
        _session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=True,
            autocommit=False
        )
    
    return _session_factory

@contextlib.asynccontextmanager
async def get_session():
    """Get a database session with proper cleanup"""
    async with _session_lock:
        session_factory = await get_session_factory()
        session = session_factory()
        
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()

async def initialize_db():
    """Initialize database with better error handling"""
    logger.info("Initializing database...")
    
    try:
        engine = await get_engine()
        
        # Create all tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
        logger.info("Database tables created successfully")
        
        # Test connection
        async with get_session() as session:
            # Simple test query
            result = await session.execute(select(Setting).limit(1))
            logger.info("Database connection verified")
        
        logger.info("Database initialized successfully")
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

# Guild settings operations
async def get_guild_settings(guild_id: str) -> Setting:
    """Get settings for a guild with proper session management"""
    async with get_session() as session:
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
            await session.flush()  # Flush to get the ID
            await session.refresh(settings)
        
        return settings

# Favorite query operations
async def create_favorite_query(guild_id: str, author_id: str, name: str, query: str) -> FavoriteQuery:
    """Create a new favorite query with session management"""
    async with get_session() as session:
        # Check if name already exists
        existing = await session.execute(
            select(FavoriteQuery).where(
                FavoriteQuery.guildId == guild_id,
                FavoriteQuery.name == name
            )
        )
        
        if existing.scalars().first():
            raise ValueError("A favorite with that name already exists")
        
        favorite = FavoriteQuery(
            guildId=guild_id,
            authorId=author_id,
            name=name,
            query=query
        )
        session.add(favorite)
        await session.flush()
        await session.refresh(favorite)
        return favorite

async def get_favorite_queries(guild_id: str) -> List[FavoriteQuery]:
    """Get all favorite queries for a guild"""
    async with get_session() as session:
        result = await session.execute(
            select(FavoriteQuery)
            .where(FavoriteQuery.guildId == guild_id)
            .order_by(FavoriteQuery.name)
        )
        return list(result.scalars().all())

async def get_favorite_query(guild_id: str, name: str) -> Optional[FavoriteQuery]:
    """Get a specific favorite query by name"""
    async with get_session() as session:
        result = await session.execute(
            select(FavoriteQuery).where(
                FavoriteQuery.guildId == guild_id,
                FavoriteQuery.name == name
            )
        )
        return result.scalars().first()

async def delete_favorite_query(query_id: int) -> None:
    """Delete a favorite query by ID"""
    async with get_session() as session:
        favorite = await session.get(FavoriteQuery, query_id)
        if favorite:
            await session.delete(favorite)

# File cache operations
async def get_file_cache(hash_key: str) -> Optional[FileCache]:
    """Get a file cache entry by hash with session management"""
    async with get_session() as session:
        cache = await session.get(FileCache, hash_key)
        if cache:
            # Update accessed time
            cache.accessedAt = datetime.utcnow()
            # Session will auto-commit due to context manager
        return cache

async def create_file_cache(hash_key: str, size: int) -> FileCache:
    """Create a new file cache entry with session management"""
    async with get_session() as session:
        cache = FileCache(
            hash=hash_key,
            bytes=size,
            accessedAt=datetime.utcnow()
        )
        session.add(cache)
        await session.flush()
        await session.refresh(cache)
        return cache

async def remove_file_cache(hash_key: str) -> None:
    """Remove a file cache entry from the database"""
    async with get_session() as session:
        cache = await session.get(FileCache, hash_key)
        if cache:
            await session.delete(cache)

async def get_total_cache_size() -> int:
    """Get the total size of all cached files in bytes"""
    async with get_session() as session:
        result = await session.execute(
            select(func.sum(FileCache.bytes))
        )
        return result.scalar() or 0

async def get_oldest_file_caches(limit: int = 10) -> List[FileCache]:
    """Get the oldest file cache entries by access time"""
    async with get_session() as session:
        result = await session.execute(
            select(FileCache)
            .order_by(FileCache.accessedAt)
            .limit(limit)
        )
        return list(result.scalars().all())

async def get_recent_file_caches(limit: int = 5) -> List[FileCache]:
    """Get the most recently accessed file cache entries"""
    async with get_session() as session:
        result = await session.execute(
            select(FileCache)
            .order_by(FileCache.accessedAt.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

# Key-value cache operations
async def get_key_value(key: str) -> Optional[str]:
    """Get a value from the key-value cache"""
    async with get_session() as session:
        cache = await session.get(KeyValueCache, key)
        
        if not cache:
            return None
            
        # Check if expired
        if cache.expiresAt < datetime.utcnow():
            await session.delete(cache)
            return None
            
        return cache.value

async def set_key_value(key: str, value: str, ttl: int) -> None:
    """Set a value in the key-value cache"""
    async with get_session() as session:
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

async def cleanup_expired_key_value_cache() -> int:
    """Remove all expired key-value cache entries"""
    async with get_session() as session:
        result = await session.execute(
            delete(KeyValueCache).where(KeyValueCache.expiresAt < datetime.utcnow())
        )
        return result.rowcount

# Utility functions for database maintenance
async def cleanup_database():
    """Perform general database cleanup tasks"""
    try:
        # Clean up expired cache entries
        expired_count = await cleanup_expired_key_value_cache()
        logger.info(f"Cleaned up {expired_count} expired cache entries")
        
        # Check for orphaned file cache entries
        # This would require checking the file system, which we'll do in the file cache service
        
    except Exception as e:
        logger.error(f"Error during database cleanup: {e}")

async def get_database_stats() -> Dict[str, Any]:
    """Get database statistics for monitoring"""
    stats = {}
    
    try:
        async with get_session() as session:
            # Count settings
            result = await session.execute(select(func.count(Setting.guildId)))
            stats['guild_settings'] = result.scalar()
            
            # Count favorites
            result = await session.execute(select(func.count(FavoriteQuery.id)))
            stats['favorite_queries'] = result.scalar()
            
            # Count file cache entries
            result = await session.execute(select(func.count(FileCache.hash)))
            stats['cached_files'] = result.scalar()
            
            # Get total cache size
            result = await session.execute(select(func.sum(FileCache.bytes)))
            stats['total_cache_size'] = result.scalar() or 0
            
            # Count key-value cache entries
            result = await session.execute(select(func.count(KeyValueCache.key)))
            stats['key_value_entries'] = result.scalar()
            
            # Count expired key-value entries
            result = await session.execute(
                select(func.count(KeyValueCache.key))
                .where(KeyValueCache.expiresAt < datetime.utcnow())
            )
            stats['expired_kv_entries'] = result.scalar()
            
    except Exception as e:
        logger.error(f"Error getting database stats: {e}")
        stats['error'] = str(e)
    
    return stats

async def vacuum_database():
    """Vacuum the SQLite database to reclaim space"""
    try:
        engine = await get_engine()
        async with engine.begin() as conn:
            await conn.execute("VACUUM")
        logger.info("Database vacuum completed")
    except Exception as e:
        logger.error(f"Error during database vacuum: {e}")

# Migration helpers (for future use)
async def get_database_version() -> int:
    """Get the current database schema version"""
    # This would be used for future migrations
    # For now, we'll assume version 1
    return 1

async def run_migrations():
    """Run any pending database migrations"""
    # Placeholder for future migration system
    current_version = await get_database_version()
    logger.info(f"Database schema version: {current_version}")
    
    # Future migrations would go here
    pass

# Health check functions
async def check_database_health() -> Dict[str, Any]:
    """Check database health and return status"""
    health = {
        'status': 'unknown',
        'response_time': None,
        'error': None
    }
    
    try:
        import time
        start_time = time.time()
        
        # Simple health check query
        async with get_session() as session:
            await session.execute(select(1))
        
        end_time = time.time()
        health['response_time'] = round((end_time - start_time) * 1000, 2)  # ms
        health['status'] = 'healthy'
        
    except Exception as e:
        health['status'] = 'unhealthy'
        health['error'] = str(e)
        logger.error(f"Database health check failed: {e}")
    
    return health