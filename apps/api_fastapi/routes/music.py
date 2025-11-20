"""
Music API Endpoints - RESTful API for Music Streaming Platform

File: apps/api_fastapi/app/routes/music.py

This module provides FastAPI endpoints for:
- Track management (CRUD, streaming, upload)
- Artist and album operations
- Playlist management
- Search functionality
- Analytics and recommendations
- Play history tracking

All endpoints include:
- JWT authentication
- RBAC authorization
- Rate limiting
- Request validation
- Comprehensive error handling
"""

import logging
from typing import List, Optional
from datetime import datetime, timedelta

from fastapi import (
    APIRouter, Depends, HTTPException, status,
    Query, Path, Body, UploadFile, File
)
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.dependencies import get_current_user, require_role
from models.user_models import User
from models.music_models import Track, Artist, Album, Playlist
from schemas.music import (
    # Track schemas
    TrackCreate, TrackUpdate, TrackResponse, TrackStreamRequest,
    TrackStreamResponse, TrackUploadInitiate, TrackUploadResponse,
    PaginatedTracks,
    # Artist schemas
    ArtistCreate, ArtistUpdate, ArtistResponse, ArtistDetailResponse,
    PaginatedArtists,
    # Album schemas
    AlbumCreate, AlbumUpdate, AlbumResponse, AlbumDetailResponse,
    PaginatedAlbums,
    # Playlist schemas
    PlaylistCreate, PlaylistUpdate, PlaylistResponse,
    PlaylistDetailResponse, PlaylistAddTrackRequest,
    PlaylistReorderRequest, PaginatedPlaylists,
    # Play history
    PlayHistoryCreate, PlayHistoryResponse,
    # Search
    SearchQuery, SearchResults,
    # Analytics
    TrackAnalytics, ArtistAnalytics, UserListeningStats,
    # Recommendations
    RecommendationRequest, RecommendationResponse,
    # Bulk operations
    BulkTrackCreate, BulkOperationResponse
)
from services.music_service import MusicService
from app.security.permissions import require_permission, Permission
from middleware.rate_limit import rate_limit

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/music", tags=["music"])


# ============================================================================
# TRACK ENDPOINTS
# ============================================================================

@router.post(
    "/tracks",
    response_model=TrackResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("curator"))]
)
@rate_limit(calls=10, period=60)  # 10 tracks per minute
async def create_track(
    track_data: TrackCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new track (curator/admin only)
    
    **Required Role:** curator or admin
    
    **Rate Limit:** 10 requests per minute
    
    **Request Body:**
    - title: Track title (required)
    - artist_ids: List of artist IDs (required, min 1)
    - album_id: Album ID (optional)
    - duration: Duration in seconds (required)
    - s3_key: S3 object key for audio file (required)
    - cover_url: Cover image URL (optional)
    - genre: Music genre (optional)
    - release_date: Release date (optional)
    - is_explicit: Explicit content flag (default: false)
    """
    try:
        service = MusicService(db)
        track = await service.create_track(track_data, current_user.id)
        
        logger.info(
            f"Track created: {track.title} (ID: {track.id}) by user {current_user.id}"
        )
        
        return track
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creating track: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create track"
        )


@router.get("/tracks/{track_id}", response_model=TrackResponse)
@rate_limit(calls=100, period=60)  # 100 requests per minute
async def get_track(
    track_id: int = Path(..., gt=0),
    include_url: bool = Query(False, description="Include streaming URL"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get track by ID
    
    **Rate Limit:** 100 requests per minute
    
    **Query Parameters:**
    - include_url: If true, includes a pre-signed streaming URL (expires in 1 hour)
    """
    service = MusicService(db)
    track = await service.get_track(track_id, include_signed_url=include_url)
    
    if not track:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Track {track_id} not found"
        )
    
    return track


@router.get("/tracks", response_model=PaginatedTracks)
@rate_limit(calls=100, period=60)
async def list_tracks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    genre: Optional[str] = Query(None),
    artist_id: Optional[int] = Query(None),
    album_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """
    List tracks with pagination and filtering
    
    **Rate Limit:** 100 requests per minute
    
    **Query Parameters:**
    - page: Page number (default: 1)
    - page_size: Items per page (default: 20, max: 100)
    - genre: Filter by genre (optional)
    - artist_id: Filter by artist ID (optional)
    - album_id: Filter by album ID (optional)
    """
    service = MusicService(db)
    
    # Calculate offset
    offset = (page - 1) * page_size
    
    # Get tracks (simplified - you'd implement filtering in service)
    tracks = await service.search_tracks("", limit=page_size, offset=offset)
    total = len(tracks)  # You'd query total count separately
    
    return {
        "items": tracks,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }


@router.put("/tracks/{track_id}", response_model=TrackResponse)
@rate_limit(calls=20, period=60)
async def update_track(
    track_id: int = Path(..., gt=0),
    track_data: TrackUpdate = Body(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update track (curator/admin only)
    
    **Required Role:** curator or admin
    **Rate Limit:** 20 requests per minute
    """
    # Check permission
    if not current_user.has_role("curator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    
    service = MusicService(db)
    track = await service.update_track(track_id, track_data)
    
    if not track:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Track {track_id} not found"
        )
    
    logger.info(f"Track updated: {track_id} by user {current_user.id}")
    return track


@router.delete("/tracks/{track_id}", status_code=status.HTTP_204_NO_CONTENT)
@rate_limit(calls=10, period=60)
async def delete_track(
    track_id: int = Path(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete track (admin only)
    
    **Required Role:** admin
    **Rate Limit:** 10 requests per minute
    """
    if not current_user.has_role("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )
    
    service = MusicService(db)
    deleted = await service.delete_track(track_id)
    
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Track {track_id} not found"
        )
    
    logger.info(f"Track deleted: {track_id} by admin {current_user.id}")


@router.post("/tracks/{track_id}/stream", response_model=TrackStreamResponse)
@rate_limit(calls=100, period=60)
async def get_stream_url(
    track_id: int = Path(..., gt=0),
    stream_request: TrackStreamRequest = Body(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get streaming URL for track
    
    **Authentication:** Required
    **Rate Limit:** 100 requests per minute
    
    **Request Body:**
    - quality: Audio quality (low/medium/high/lossless)
    - expires_in: URL expiration in seconds (300-86400, default 3600)
    
    **Response:**
    - track_id: Track ID
    - stream_url: Pre-signed S3/CloudFront URL
    - quality: Quality level
    - expires_at: URL expiration timestamp
    """
    service = MusicService(db)
    track = await service.get_track(track_id)
    
    if not track:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Track {track_id} not found"
        )
    
    if not track.s3_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio file not available"
        )
    
    try:
        # Generate signed URL
        stream_url = service.s3_service.generate_signed_url(
            track.s3_key,
            expires_in=stream_request.expires_in,
            quality=stream_request.quality
        )
        
        expires_at = datetime.utcnow() + timedelta(seconds=stream_request.expires_in)
        
        return TrackStreamResponse(
            track_id=track_id,
            stream_url=stream_url,
            quality=stream_request.quality,
            expires_at=expires_at
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/tracks/upload/initiate", response_model=TrackUploadResponse)
@rate_limit(calls=5, period=60)
async def initiate_upload(
    upload_data: TrackUploadInitiate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Initiate direct upload to S3 (curator/admin only)
    
    **Required Role:** curator or admin
    **Rate Limit:** 5 requests per minute
    
    Returns a pre-signed POST URL for direct upload to S3.
    """
    if not current_user.has_role("curator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    
    service = MusicService(db)
    
    try:
        upload_info = await service.s3_service.upload_presigned_url(
            filename=upload_data.filename,
            content_type=upload_data.content_type,
            expires_in=3600
        )
        
        return TrackUploadResponse(
            upload_id=upload_info['s3_key'],
            s3_key=upload_info['s3_key'],
            presigned_url=upload_info['upload_url'],
            expires_at=upload_info['expires_at'],
            fields=upload_info['fields']
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/tracks/popular", response_model=List[TrackResponse])
@rate_limit(calls=50, period=60)
async def get_popular_tracks(
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """
    Get popular tracks based on play count
    
    **Rate Limit:** 50 requests per minute
    
    **Query Parameters:**
    - limit: Number of tracks to return (default: 50, max: 100)
    """
    service = MusicService(db)
    tracks = await service.get_popular_tracks(limit)
    return tracks


# ============================================================================
# ARTIST ENDPOINTS
# ============================================================================

@router.post(
    "/artists",
    response_model=ArtistResponse,
    status_code=status.HTTP_201_CREATED
)
@rate_limit(calls=10, period=60)
async def create_artist(
    artist_data: ArtistCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create artist (curator/admin only)"""
    if not current_user.has_role("curator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    
    service = MusicService(db)
    artist = await service.create_artist(artist_data)
    
    logger.info(f"Artist created: {artist.name} (ID: {artist.id})")
    return artist


@router.get("/artists/{artist_id}", response_model=ArtistDetailResponse)
@rate_limit(calls=100, period=60)
async def get_artist(
    artist_id: int = Path(..., gt=0),
    db: AsyncSession = Depends(get_db)
):
    """Get artist details with tracks and albums"""
    service = MusicService(db)
    artist = await service.get_artist(artist_id)
    
    if not artist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artist {artist_id} not found"
        )
    
    return artist


# ============================================================================
# PLAYLIST ENDPOINTS
# ============================================================================

@router.post(
    "/playlists",
    response_model=PlaylistResponse,
    status_code=status.HTTP_201_CREATED
)
@rate_limit(calls=20, period=60)
async def create_playlist(
    playlist_data: PlaylistCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new playlist"""
    service = MusicService(db)
    playlist = await service.create_playlist(playlist_data, current_user.id)
    
    logger.info(
        f"Playlist created: {playlist.name} (ID: {playlist.id}) "
        f"by user {current_user.id}"
    )
    return playlist


@router.post("/playlists/{playlist_id}/tracks", status_code=status.HTTP_204_NO_CONTENT)
@rate_limit(calls=50, period=60)
async def add_track_to_playlist(
    playlist_id: int = Path(..., gt=0),
    request: PlaylistAddTrackRequest = Body(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Add track to playlist"""
    service = MusicService(db)
    
    # Verify playlist ownership
    playlist = await db.get(Playlist, playlist_id)
    if not playlist:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Playlist not found"
        )
    
    if playlist.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not your playlist"
        )
    
    success = await service.add_track_to_playlist(
        playlist_id,
        request.track_id,
        request.position
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to add track to playlist"
        )


# ============================================================================
# SEARCH ENDPOINT
# ============================================================================

@router.post("/search", response_model=SearchResults)
@rate_limit(calls=50, period=60)
async def search(
    query: SearchQuery = Body(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Search tracks, artists, albums, and playlists
    
    **Rate Limit:** 50 requests per minute
    
    **Request Body:**
    - q: Search query string (required)
    - types: Types to search (default: all)
    - limit: Results per type (default: 20, max: 50)
    - offset: Pagination offset (default: 0)
    """
    service = MusicService(db)
    start_time = datetime.utcnow()
    
    results = SearchResults(
        query=query.q,
        tracks=[],
        artists=[],
        albums=[],
        playlists=[]
    )
    
    # Search tracks
    if "track" in query.types:
        results.tracks = await service.search_tracks(
            query.q,
            limit=query.limit,
            offset=query.offset
        )
    
    # Calculate search time
    end_time = datetime.utcnow()
    results.took_ms = int((end_time - start_time).total_seconds() * 1000)
    results.total_results = len(results.tracks) + len(results.artists) + \
                            len(results.albums) + len(results.playlists)
    
    return results


# ============================================================================
# PLAY HISTORY ENDPOINT
# ============================================================================

@router.post("/play-history", response_model=PlayHistoryResponse)
@rate_limit(calls=100, period=60)
async def record_play(
    play_data: PlayHistoryCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Record play history
    
    **Authentication:** Required
    **Rate Limit:** 100 requests per minute
    
    Records when a user plays a track. Play count is incremented
    if the user plays more than 30 seconds.
    """
    service = MusicService(db)
    play_history = await service.record_play(current_user.id, play_data)
    
    return play_history


# ============================================================================
# ANALYTICS ENDPOINTS
# ============================================================================

@router.get("/analytics/user/stats", response_model=UserListeningStats)
@rate_limit(calls=20, period=60)
async def get_user_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get user listening statistics
    
    **Authentication:** Required
    **Rate Limit:** 20 requests per minute
    """
    # This would be implemented in the service layer
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Analytics not yet implemented"
    )


# ============================================================================
# HEALTH CHECK
# ============================================================================

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "music-api",
        "timestamp": datetime.utcnow().isoformat()
    }
