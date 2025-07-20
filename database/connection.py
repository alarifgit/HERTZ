"""
Database connection management for HERTZ bot
Handles SQLite/PostgreSQL connections with async support
"""

import asyncio
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import text
from contextlib import asynccontextmanager

from config.settings import get_config

logger = logging.getLogger(__name__)

# Base class for all database models
Base = declarative_base()

class DatabaseManager:
    """Manages database connections and sessions."""
    
    def __init__(self):
        self.config = get_config()
        self.engine: Optional[AsyncEngine] = None
        self.session_factory: Optional[async_sessionmaker] = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize database connection."""
        if self._initialized:
            return
        
        try:
            # Convert URL to async if needed
            db_url = self.config.database_url
            if db_url.startswith('sqlite:///'):
                # Convert to async SQLite
                db_url = db_url.replace('sqlite:///', 'sqlite+aiosqlite:///')
            elif db_url.startswith('postgresql://'):
                # Convert to async PostgreSQL
                db_url = db_url.replace('postgresql://', 'postgresql+asyncpg://')
            
            # Create async engine
            self.engine = create_async_engine(
                db_url,
                echo=False,  # Set to True for SQL debugging
                pool_pre_ping=True,
                pool_recycle=3600,  # Recycle connections every hour
            )
            
            # Create session factory
            self.session_factory = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            # Test connection
            await self._test_connection()
            
            # Create tables
            await self.create_tables()
            
            self._initialized = True
            logger.info(f"Database initialized successfully: {db_url.split('://')[0]}")
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    async def _test_connection(self):
        """Test database connection."""
        async with self.engine.begin() as conn:
            result = await conn.execute(text("SELECT 1"))
            assert result.scalar() == 1
    
    async def create_tables(self):
        """Create all database tables."""
        try:
            # Import models to register them
            from database.models import Guild, QueuedTrack, UserFavorite, PlayHistory
            
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            
            logger.info("Database tables created/verified")
            
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}")
            raise
    
    @asynccontextmanager
    async def get_session(self):
        """Get async database session context manager."""
        if not self._initialized:
            await self.initialize()
        
        session = self.session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
    
    async def get_session_direct(self) -> AsyncSession:
        """Get async database session directly (manual management required)."""
        if not self._initialized:
            await self.initialize()
        
        return self.session_factory()
    
    async def execute_raw(self, query: str, parameters: dict = None):
        """Execute raw SQL query."""
        async with self.get_session() as session:
            result = await session.execute(text(query), parameters or {})
            return result
    
    async def close(self):
        """Close database connections."""
        if self.engine:
            await self.engine.dispose()
            logger.info("Database connections closed")
        
        self._initialized = False
    
    async def backup_database(self, backup_path: str):
        """Create database backup (SQLite only)."""
        if not self.config.database_url.startswith('sqlite'):
            raise NotImplementedError("Backup only supported for SQLite databases")
        
        import shutil
        from pathlib import Path
        
        # Extract file path from URL
        db_file = self.config.database_url.replace('sqlite:///', '')
        backup_file = Path(backup_path)
        
        # Ensure backup directory exists
        backup_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Copy database file
        shutil.copy2(db_file, backup_file)
        logger.info(f"Database backed up to: {backup_file}")
    
    async def get_database_info(self) -> dict:
        """Get database information and statistics."""
        try:
            info = {
                'url': self.config.database_url.split('://')[0] + '://[hidden]',
                'initialized': self._initialized,
                'tables': [],
                'total_records': 0
            }
            
            if self._initialized:
                # Get table information
                async with self.get_session() as session:
                    # Get table names
                    if 'sqlite' in self.config.database_url:
                        result = await session.execute(
                            text("SELECT name FROM sqlite_master WHERE type='table'")
                        )
                    else:
                        result = await session.execute(
                            text("SELECT tablename FROM pg_tables WHERE schemaname='public'")
                        )
                    
                    tables = [row[0] for row in result.fetchall()]
                    info['tables'] = tables
                    
                    # Get record counts
                    total_records = 0
                    for table in tables:
                        if not table.startswith('alembic'):  # Skip migration tables
                            count_result = await session.execute(
                                text(f"SELECT COUNT(*) FROM {table}")
                            )
                            count = count_result.scalar()
                            total_records += count
                    
                    info['total_records'] = total_records
            
            return info
            
        except Exception as e:
            logger.error(f"Failed to get database info: {e}")
            return {'error': str(e)}

# Global database manager instance
db_manager = DatabaseManager()