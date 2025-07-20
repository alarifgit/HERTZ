"""
Music queue management for HERTZ bot
Handles track queuing, ordering, and persistence
"""

import asyncio
import logging
import random
from typing import List, Dict, Any, Optional
from datetime import datetime

from database.connection import db_manager
from database.models import QueuedTrack

logger = logging.getLogger(__name__)

class MusicQueue:
    """Music queue for a guild."""
    
    def __init__(self, guild_id: str):
        self.guild_id = str(guild_id)
        self._tracks: List[Dict[str, Any]] = []
        self._position = 0
        self._lock = asyncio.Lock()
        
        logger.debug(f"Created music queue for guild {guild_id}")
    
    async def add(self, track: Dict[str, Any], position: Optional[int] = None) -> int:
        """Add a track to the queue."""
        async with self._lock:
            # Ensure required fields
            if 'title' not in track or 'url' not in track:
                raise ValueError("Track must have title and url")
            
            # Add default values
            track.setdefault('artist', 'Unknown Artist')
            track.setdefault('duration', None)
            track.setdefault('thumbnail_url', None)
            track.setdefault('source', 'unknown')
            track.setdefault('source_id', None)
            track.setdefault('added_at', datetime.utcnow())
            
            if position is None:
                # Add to end
                self._tracks.append(track)
                position = len(self._tracks) - 1
            else:
                # Insert at specific position
                position = max(0, min(position, len(self._tracks)))
                self._tracks.insert(position, track)
            
            # Persist to database
            await self._persist_track(track, position)
            
            logger.debug(f"Added track '{track['title']}' to queue at position {position}")
            return position
    
    async def add_to_front(self, track: Dict[str, Any]) -> int:
        """Add a track to the front of the queue (next to play)."""
        return await self.add(track, 0)
    
    async def add_multiple(self, tracks: List[Dict[str, Any]]) -> List[int]:
        """Add multiple tracks to the queue."""
        positions = []
        
        async with self._lock:
            for track in tracks:
                position = await self.add(track)
                positions.append(position)
        
        logger.info(f"Added {len(tracks)} tracks to queue")
        return positions
    
    async def get_next(self) -> Optional[Dict[str, Any]]:
        """Get the next track to play."""
        async with self._lock:
            if self._position < len(self._tracks):
                track = self._tracks[self._position].copy()
                self._position += 1
                
                # Remove from database
                await self._remove_from_db(track)
                
                logger.debug(f"Retrieved next track: {track['title']}")
                return track
            
            return None
    
    async def peek_next(self) -> Optional[Dict[str, Any]]:
        """Peek at the next track without consuming it."""
        async with self._lock:
            if self._position < len(self._tracks):
                return self._tracks[self._position].copy()
            return None
    
    async def remove(self, position: int) -> Optional[Dict[str, Any]]:
        """Remove a track at a specific position."""
        async with self._lock:
            if 0 <= position < len(self._tracks):
                track = self._tracks.pop(position)
                
                # Adjust position if needed
                if position < self._position:
                    self._position -= 1
                
                # Remove from database
                await self._remove_from_db(track)
                
                logger.debug(f"Removed track at position {position}: {track['title']}")
                return track
            
            return None
    
    async def move(self, from_pos: int, to_pos: int) -> bool:
        """Move a track from one position to another."""
        async with self._lock:
            if (0 <= from_pos < len(self._tracks) and 
                0 <= to_pos < len(self._tracks) and 
                from_pos != to_pos):
                
                track = self._tracks.pop(from_pos)
                self._tracks.insert(to_pos, track)
                
                # Adjust position pointer if needed
                if from_pos < self._position <= to_pos:
                    self._position -= 1
                elif to_pos < self._position <= from_pos:
                    self._position += 1
                elif from_pos == self._position:
                    self._position = to_pos
                
                # Update database positions
                await self._refresh_db_positions()
                
                logger.debug(f"Moved track from position {from_pos} to {to_pos}")
                return True
            
            return False
    
    async def shuffle(self):
        """Shuffle the remaining tracks in the queue."""
        async with self._lock:
            if self._position < len(self._tracks):
                remaining_tracks = self._tracks[self._position:]
                random.shuffle(remaining_tracks)
                self._tracks[self._position:] = remaining_tracks
                
                # Update database positions
                await self._refresh_db_positions()
                
                logger.debug("Shuffled queue")
    
    async def clear(self):
        """Clear all tracks from the queue."""
        async with self._lock:
            self._tracks.clear()
            self._position = 0
            
            # Clear database
            await self._clear_db()
            
            logger.debug("Cleared queue")
    
    async def get_tracks(self, start: int = 0, limit: int = 50) -> List[Dict[str, Any]]:
        """Get tracks from the queue with pagination."""
        async with self._lock:
            # Get remaining tracks (not yet played)
            remaining_tracks = self._tracks[self._position:]
            
            # Apply pagination
            end = min(start + limit, len(remaining_tracks))
            return remaining_tracks[start:end]
    
    async def get_all_tracks(self) -> List[Dict[str, Any]]:
        """Get all tracks in the queue."""
        async with self._lock:
            return self._tracks[self._position:].copy()
    
    def size(self) -> int:
        """Get the current size of the queue."""
        return max(0, len(self._tracks) - self._position)
    
    async def is_empty(self) -> bool:
        """Check if the queue is empty."""
        return self.size() == 0
    
    def get_total_duration(self) -> int:
        """Get total duration of all tracks in seconds."""
        total = 0
        for track in self._tracks[self._position:]:
            if track.get('duration'):
                total += track['duration']
        return total
    
    async def find_track(self, query: str) -> List[int]:
        """Find tracks in queue by title or artist."""
        async with self._lock:
            matches = []
            query_lower = query.lower()
            
            for i, track in enumerate(self._tracks[self._position:], self._position):
                title_match = query_lower in track['title'].lower()
                artist_match = track.get('artist') and query_lower in track['artist'].lower()
                
                if title_match or artist_match:
                    matches.append(i - self._position)  # Return relative position
            
            return matches
    
    async def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recently played tracks from this session."""
        async with self._lock:
            if self._position > 0:
                start = max(0, self._position - limit)
                return self._tracks[start:self._position]
            return []
    
    async def load_from_database(self):
        """Load persisted queue from database."""
        try:
            async with db_manager.get_session() as session:
                # Get all queued tracks for this guild, ordered by position
                from sqlalchemy import select
                from sqlalchemy.orm import selectinload
                
                result = await session.execute(
                    select(QueuedTrack)
                    .where(QueuedTrack.guild_id == self.guild_id)
                    .order_by(QueuedTrack.position)
                )
                
                db_tracks = result.scalars().all()
                
                # Convert to dict format
                tracks = []
                for db_track in db_tracks:
                    track = {
                        'title': db_track.title,
                        'artist': db_track.artist,
                        'url': db_track.url,
                        'thumbnail_url': db_track.thumbnail_url,
                        'duration': db_track.duration,
                        'source': db_track.source,
                        'source_id': db_track.source_id,
                        'requested_by_id': db_track.requested_by_id,
                        'requested_by_name': db_track.requested_by_name,
                        'added_at': db_track.added_at
                    }
                    tracks.append(track)
                
                async with self._lock:
                    self._tracks = tracks
                    self._position = 0
                
                logger.info(f"Loaded {len(tracks)} tracks from database for guild {self.guild_id}")
                
        except Exception as e:
            logger.error(f"Failed to load queue from database: {e}")
    
    async def _persist_track(self, track: Dict[str, Any], position: int):
        """Persist a track to the database."""
        try:
            async with db_manager.get_session() as session:
                db_track = QueuedTrack(
                    guild_id=self.guild_id,
                    title=track['title'],
                    artist=track.get('artist'),
                    url=track['url'],
                    thumbnail_url=track.get('thumbnail_url'),
                    duration=track.get('duration'),
                    position=position,
                    requested_by_id=track['requested_by_id'],
                    requested_by_name=track['requested_by_name'],
                    source=track['source'],
                    source_id=track.get('source_id')
                )
                
                session.add(db_track)
                await session.commit()
                
        except Exception as e:
            logger.error(f"Failed to persist track to database: {e}")
    
    async def _remove_from_db(self, track: Dict[str, Any]):
        """Remove a track from the database."""
        try:
            async with db_manager.get_session() as session:
                from sqlalchemy import delete
                
                await session.execute(
                    delete(QueuedTrack)
                    .where(QueuedTrack.guild_id == self.guild_id)
                    .where(QueuedTrack.url == track['url'])
                    .where(QueuedTrack.title == track['title'])
                )
                
                await session.commit()
                
        except Exception as e:
            logger.error(f"Failed to remove track from database: {e}")
    
    async def _clear_db(self):
        """Clear all tracks from database."""
        try:
            async with db_manager.get_session() as session:
                from sqlalchemy import delete
                
                await session.execute(
                    delete(QueuedTrack)
                    .where(QueuedTrack.guild_id == self.guild_id)
                )
                
                await session.commit()
                
        except Exception as e:
            logger.error(f"Failed to clear queue from database: {e}")
    
    async def _refresh_db_positions(self):
        """Refresh all position values in database."""
        try:
            async with db_manager.get_session() as session:
                from sqlalchemy import delete
                
                # Clear existing entries
                await session.execute(
                    delete(QueuedTrack)
                    .where(QueuedTrack.guild_id == self.guild_id)
                )
                
                # Re-add all tracks with correct positions
                for i, track in enumerate(self._tracks[self._position:]):
                    db_track = QueuedTrack(
                        guild_id=self.guild_id,
                        title=track['title'],
                        artist=track.get('artist'),
                        url=track['url'],
                        thumbnail_url=track.get('thumbnail_url'),
                        duration=track.get('duration'),
                        position=i,
                        requested_by_id=track['requested_by_id'],
                        requested_by_name=track['requested_by_name'],
                        source=track['source'],
                        source_id=track.get('source_id')
                    )
                    session.add(db_track)
                
                await session.commit()
                
        except Exception as e:
            logger.error(f"Failed to refresh database positions: {e}")
    
    def get_info(self) -> dict:
        """Get queue information."""
        return {
            'guild_id': self.guild_id,
            'size': self.size(),
            'total_tracks': len(self._tracks),
            'position': self._position,
            'total_duration': self.get_total_duration(),
            'average_duration': self.get_total_duration() // max(self.size(), 1)
        }