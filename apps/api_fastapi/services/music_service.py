"""
Music Service Layer - Business Logic for Music Streaming Platform

File: apps/api_fastapi/app/services/music_service.py

This module provides business logic for music operations including:
- S3 audio file management and signed URL generation
- Redis caching for performance optimization
- Track, Artist, Album, and Playlist CRUD operations
- Search and recommendation algorithms
- Analytics and streaming logic
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from urllib.parse import quote

import boto3
from botocore.exceptions import ClientError
from redis import asyncio as aioredis
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from models.music_models import (
    Track, Artist, Album, Playlist, PlayHistory,
    track_artists, playlist_tracks
)
from schemas.music import (
    TrackCreate, TrackUpdate, TrackStreamResponse,
    ArtistCreate, ArtistUpdate,
    AlbumCreate, AlbumUpdate,
    PlaylistCreate, PlaylistUpdate,
    PlayHistoryCreate, SearchResults,
    AudioQuality, PlaylistVisibility
)

logger = logging.getLogger(__name__)


# ============================================================================
# S3 AUDIO SERVICE
# ============================================================================

class S3AudioService:
    """Service for managing audio files in S3"""
    
    def __init__(self):
        """Initialize S3 client"""
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION
        )
        self.bucket_name = settings.S3_BUCKET_NAME
        self.cloudfront_domain = settings.CLOUDFRONT_DOMAIN
        
    def generate_signed_url(
        self,
        s3_key: str,
        expires_in: int = 3600,
        quality: AudioQuality = AudioQuality.HIGH
    ) -> str:
        """
        Generate pre-signed URL for audio streaming
        
        Args:
            s3_key: S3 object key
            expires_in: URL expiration time in seconds (default 1 hour)
            quality: Audio quality level
            
        Returns:
            Pre-signed URL string
        """
        try:
            # Adjust S3 key based on quality
            quality_key = self._get_quality_key(s3_key, quality)
            
            # Generate pre-signed URL
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': quality_key,
                    'ResponseContentType': 'audio/mpeg',
                    'ResponseContentDisposition': 'inline'
                },
                ExpiresIn=expires_in
            )
            
            # Replace S3 URL with CloudFront if configured
            if self.cloudfront_domain:
                url = url.replace(
                    f"https://{self.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com",
                    f"https://{self.cloudfront_domain}"
                )
            
            logger.info(f"Generated signed URL for {s3_key} ({quality})")
            return url
            
        except ClientError as e:
            logger.error(f"Error generating signed URL: {e}")
            raise ValueError(f"Failed to generate streaming URL: {str(e)}")
    
    def _get_quality_key(self, base_key: str, quality: AudioQuality) -> str:
        """
        Get S3 key for specific audio quality
        
        Assumes transcoded files are stored with quality suffixes:
        - original.mp3 → original_low.mp3, original_high.mp3, etc.
        """
        if quality == AudioQuality.LOSSLESS:
            return base_key.replace('.mp3', '.flac')
        elif quality in [AudioQuality.LOW, AudioQuality.MEDIUM, AudioQuality.HIGH]:
            base, ext = base_key.rsplit('.', 1)
            return f"{base}_{quality.value}.{ext}"
        return base_key
    
    async def upload_presigned_url(
        self,
        filename: str,
        content_type: str,
        expires_in: int = 3600
    ) -> Dict[str, Any]:
        """
        Generate pre-signed POST URL for direct upload to S3
        
        Args:
            filename: Original filename
            content_type: MIME type
            expires_in: URL expiration time
            
        Returns:
            Dict with upload URL and required fields
        """
        # Generate unique S3 key
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        safe_filename = quote(filename, safe='')
        s3_key = f"uploads/{timestamp}_{safe_filename}"
        
        try:
            # Generate pre-signed POST
            response = self.s3_client.generate_presigned_post(
                Bucket=self.bucket_name,
                Key=s3_key,
                Fields={
                    'Content-Type': content_type,
                    'acl': 'private'
                },
                Conditions=[
                    {'Content-Type': content_type},
                    ['content-length-range', 100, 104857600]  # 100 bytes to 100MB
                ],
                ExpiresIn=expires_in
            )
            
            return {
                's3_key': s3_key,
                'upload_url': response['url'],
                'fields': response['fields'],
                'expires_at': datetime.utcnow() + timedelta(seconds=expires_in)
            }
            
        except ClientError as e:
            logger.error(f"Error generating upload URL: {e}")
            raise ValueError(f"Failed to generate upload URL: {str(e)}")
    
    async def delete_audio(self, s3_key: str) -> bool:
        """
        Delete audio file from S3
        
        Args:
            s3_key: S3 object key to delete
            
        Returns:
            True if successful
        """
        try:
            # Delete all quality versions
            keys_to_delete = [
                s3_key,
                *[self._get_quality_key(s3_key, q) for q in AudioQuality]
            ]
            
            for key in keys_to_delete:
                try:
                    self.s3_client.delete_object(
                        Bucket=self.bucket_name,
                        Key=key
                    )
                except ClientError:
                    pass  # Ignore if file doesn't exist
            
            logger.info(f"Deleted audio files for {s3_key}")
            return True
            
        except ClientError as e:
            logger.error(f"Error deleting audio: {e}")
            return False


# ============================================================================
# CACHE SERVICE
# ============================================================================

class CacheService:
    """Service for Redis caching"""
    
    def __init__(self):
        """Initialize Redis connection"""
        self.redis = None
        
    async def connect(self):
        """Establish Redis connection"""
        if not self.redis:
            self.redis = await aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )
    
    async def close(self):
        """Close Redis connection"""
        if self.redis:
            await self.redis.close()
    
    async def get(self, key: str) -> Optional[str]:
        """Get value from cache"""
        await self.connect()
        return await self.redis.get(key)
    
    async def set(
        self,
        key: str,
        value: str,
        expire: int = 3600
    ) -> bool:
        """Set value in cache with expiration"""
        await self.connect()
        return await self.redis.setex(key, expire, value)
    
    async def delete(self, key: str) -> bool:
        """Delete key from cache"""
        await self.connect()
        return await self.redis.delete(key) > 0
    
    async def increment(self, key: str, amount: int = 1) -> int:
        """Increment counter"""
        await self.connect()
        return await self.redis.incrby(key, amount)
    
    async def get_popular_tracks(self, limit: int = 50) -> List[int]:
        """Get popular track IDs from sorted set"""
        await self.connect()
        track_ids = await self.redis.zrevrange('popular_tracks', 0, limit - 1)
        return [int(tid) for tid in track_ids]
    
    async def update_popular_tracks(self, track_id: int, score: float):
        """Update track popularity score"""
        await self.connect()
        await self.redis.zadd('popular_tracks', {str(track_id): score})


# ============================================================================
# MUSIC SERVICE
# ============================================================================

class MusicService:
    """Main service for music operations"""
    
    def __init__(self, db: AsyncSession):
        """
        Initialize music service
        
        Args:
            db: Database session
        """
        self.db = db
        self.s3_service = S3AudioService()
        self.cache_service = CacheService()
    
    # ========================================================================
    # TRACK OPERATIONS
    # ========================================================================
    
    async def create_track(
        self,
        track_data: TrackCreate,
        user_id: int
    ) -> Track:
        """
        Create a new track
        
        Args:
            track_data: Track creation data
            user_id: ID of user creating the track
            
        Returns:
            Created Track object
        """
        # Create track instance
        track = Track(
            title=track_data.title,
            album_id=track_data.album_id,
            duration=track_data.duration,
            s3_key=track_data.s3_key,
            cover_url=str(track_data.cover_url) if track_data.cover_url else None,
            genre=track_data.genre,
            release_date=track_data.release_date,
            is_explicit=track_data.is_explicit,
            uploaded_by_user_id=user_id
        )
        
        # Add artists
        for artist_id in track_data.artist_ids:
            artist = await self.db.get(Artist, artist_id)
            if artist:
                track.artists.append(artist)
        
        self.db.add(track)
        await self.db.commit()
        await self.db.refresh(track)
        
        logger.info(f"Created track: {track.title} (ID: {track.id})")
        return track
    
    async def get_track(
        self,
        track_id: int,
        include_signed_url: bool = False
    ) -> Optional[Track]:
        """
        Get track by ID
        
        Args:
            track_id: Track ID
            include_signed_url: Whether to generate signed streaming URL
            
        Returns:
            Track object or None
        """
        # Try cache first
        cache_key = f"track:{track_id}"
        
        query = select(Track).where(Track.id == track_id).options(
            selectinload(Track.artists),
            selectinload(Track.album)
        )
        
        result = await self.db.execute(query)
        track = result.scalar_one_or_none()
        
        if track and include_signed_url and track.s3_key:
            track.signed_url = self.s3_service.generate_signed_url(track.s3_key)
        
        return track
    
    async def update_track(
        self,
        track_id: int,
        track_data: TrackUpdate
    ) -> Optional[Track]:
        """Update track"""
        track = await self.db.get(Track, track_id)
        if not track:
            return None
        
        # Update fields
        for field, value in track_data.model_dump(exclude_unset=True).items():
            setattr(track, field, value)
        
        await self.db.commit()
        await self.db.refresh(track)
        
        # Invalidate cache
        await self.cache_service.delete(f"track:{track_id}")
        
        return track
    
    async def delete_track(self, track_id: int) -> bool:
        """Delete track"""
        track = await self.db.get(Track, track_id)
        if not track:
            return False
        
        # Delete from S3
        if track.s3_key:
            await self.s3_service.delete_audio(track.s3_key)
        
        # Delete from database
        await self.db.delete(track)
        await self.db.commit()
        
        # Invalidate cache
        await self.cache_service.delete(f"track:{track_id}")
        
        logger.info(f"Deleted track ID: {track_id}")
        return True
    
    async def search_tracks(
        self,
        query: str,
        limit: int = 20,
        offset: int = 0
    ) -> List[Track]:
        """
        Search tracks by title, artist, or genre
        
        Args:
            query: Search query string
            limit: Maximum results
            offset: Result offset for pagination
            
        Returns:
            List of matching tracks
        """
        search_pattern = f"%{query}%"
        
        stmt = select(Track).where(
            or_(
                Track.title.ilike(search_pattern),
                Track.genre.ilike(search_pattern)
            )
        ).options(
            selectinload(Track.artists),
            selectinload(Track.album)
        ).limit(limit).offset(offset)
        
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
    
    async def get_popular_tracks(
        self,
        limit: int = 50
    ) -> List[Track]:
        """Get popular tracks based on play count"""
        # Try cache first
        cached_ids = await self.cache_service.get_popular_tracks(limit)
        if cached_ids:
            # Fetch tracks in order
            stmt = select(Track).where(Track.id.in_(cached_ids)).options(
                selectinload(Track.artists),
                selectinload(Track.album)
            )
            result = await self.db.execute(stmt)
            tracks = {t.id: t for t in result.scalars().all()}
            return [tracks[tid] for tid in cached_ids if tid in tracks]
        
        # Query from database
        stmt = select(Track).options(
            selectinload(Track.artists),
            selectinload(Track.album)
        ).order_by(desc(Track.play_count)).limit(limit)
        
        result = await self.db.execute(stmt)
        tracks = list(result.scalars().all())
        
        # Update cache
        for i, track in enumerate(tracks):
            await self.cache_service.update_popular_tracks(
                track.id,
                len(tracks) - i
            )
        
        return tracks
    
    async def increment_play_count(self, track_id: int):
        """Increment track play count"""
        track = await self.db.get(Track, track_id)
        if track:
            track.play_count += 1
            await self.db.commit()
            
            # Update cache
            await self.cache_service.update_popular_tracks(
                track_id,
                track.play_count
            )
    
    # ========================================================================
    # ARTIST OPERATIONS
    # ========================================================================
    
    async def create_artist(self, artist_data: ArtistCreate) -> Artist:
        """Create new artist"""
        artist = Artist(**artist_data.model_dump())
        self.db.add(artist)
        await self.db.commit()
        await self.db.refresh(artist)
        return artist
    
    async def get_artist(self, artist_id: int) -> Optional[Artist]:
        """Get artist by ID"""
        query = select(Artist).where(Artist.id == artist_id).options(
            selectinload(Artist.tracks)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()
    
    # ========================================================================
    # PLAYLIST OPERATIONS
    # ========================================================================
    
    async def create_playlist(
        self,
        playlist_data: PlaylistCreate,
        user_id: int
    ) -> Playlist:
        """Create new playlist"""
        playlist = Playlist(
            **playlist_data.model_dump(),
            user_id=user_id
        )
        self.db.add(playlist)
        await self.db.commit()
        await self.db.refresh(playlist)
        return playlist
    
    async def add_track_to_playlist(
        self,
        playlist_id: int,
        track_id: int,
        position: Optional[int] = None
    ) -> bool:
        """Add track to playlist"""
        playlist = await self.db.get(Playlist, playlist_id)
        track = await self.db.get(Track, track_id)
        
        if not playlist or not track:
            return False
        
        # Append or insert at position
        if position is None:
            playlist.tracks.append(track)
        else:
            playlist.tracks.insert(position, track)
        
        await self.db.commit()
        return True
    
    # ========================================================================
    # PLAY HISTORY
    # ========================================================================
    
    async def record_play(
        self,
        user_id: int,
        history_data: PlayHistoryCreate
    ) -> PlayHistory:
        """Record play history"""
        play_history = PlayHistory(
            user_id=user_id,
            track_id=history_data.track_id,
            played_duration=history_data.played_duration,
            quality=history_data.quality
        )
        
        self.db.add(play_history)
        
        # Increment play count if >30 seconds
        if history_data.played_duration > 30:
            await self.increment_play_count(history_data.track_id)
        
        await self.db.commit()
        await self.db.refresh(play_history)
        
        return play_history
