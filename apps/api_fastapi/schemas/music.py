"""
Music API Schemas - Pydantic Models for Request/Response Validation

This module defines Pydantic schemas for the music streaming API,
providing request validation, response serialization, and API documentation.
"""

from datetime import datetime
from typing import List, Optional
from enum import Enum

from pydantic import BaseModel, Field, field_validator, HttpUrl
from pydantic import ConfigDict


# ============================================================================
# ENUMS
# ============================================================================

class AudioQuality(str, Enum):
    """Audio quality levels for streaming"""
    LOW = "low"          # 96 kbps
    MEDIUM = "medium"    # 128 kbps
    HIGH = "high"        # 256 kbps
    LOSSLESS = "lossless"  # FLAC


class PlaylistVisibility(str, Enum):
    """Playlist visibility options"""
    PUBLIC = "public"
    PRIVATE = "private"
    UNLISTED = "unlisted"


# ============================================================================
# BASE SCHEMAS
# ============================================================================

class BaseSchema(BaseModel):
    """Base schema with common configuration"""
    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# ARTIST SCHEMAS
# ============================================================================

class ArtistBase(BaseSchema):
    """Base artist schema"""
    name: str = Field(..., min_length=1, max_length=200)
    bio: Optional[str] = Field(None, max_length=2000)
    image_url: Optional[HttpUrl] = None
    verified: bool = False


class ArtistCreate(ArtistBase):
    """Schema for creating an artist"""
    pass


class ArtistUpdate(BaseSchema):
    """Schema for updating an artist"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    bio: Optional[str] = Field(None, max_length=2000)
    image_url: Optional[HttpUrl] = None
    verified: Optional[bool] = None


class ArtistResponse(ArtistBase):
    """Schema for artist responses"""
    id: int
    follower_count: int = 0
    track_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ArtistDetailResponse(ArtistResponse):
    """Detailed artist response with tracks and albums"""
    top_tracks: List["TrackResponse"] = []
    albums: List["AlbumResponse"] = []


# ============================================================================
# ALBUM SCHEMAS
# ============================================================================

class AlbumBase(BaseSchema):
    """Base album schema"""
    title: str = Field(..., min_length=1, max_length=200)
    artist_id: int
    release_date: Optional[datetime] = None
    cover_url: Optional[HttpUrl] = None
    genre: Optional[str] = Field(None, max_length=50)


class AlbumCreate(AlbumBase):
    """Schema for creating an album"""
    pass


class AlbumUpdate(BaseSchema):
    """Schema for updating an album"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    release_date: Optional[datetime] = None
    cover_url: Optional[HttpUrl] = None
    genre: Optional[str] = Field(None, max_length=50)


class AlbumResponse(AlbumBase):
    """Schema for album responses"""
    id: int
    track_count: int = 0
    total_duration: int = 0  # in seconds
    created_at: datetime
    updated_at: datetime
    artist: Optional[ArtistResponse] = None

    model_config = ConfigDict(from_attributes=True)


class AlbumDetailResponse(AlbumResponse):
    """Detailed album response with tracks"""
    tracks: List["TrackResponse"] = []


# ============================================================================
# TRACK SCHEMAS
# ============================================================================

class TrackBase(BaseSchema):
    """Base track schema"""
    title: str = Field(..., min_length=1, max_length=200)
    album_id: Optional[int] = None
    duration: int = Field(..., gt=0, description="Duration in seconds")
    audio_url: Optional[HttpUrl] = None
    cover_url: Optional[HttpUrl] = None
    genre: Optional[str] = Field(None, max_length=50)
    release_date: Optional[datetime] = None
    is_explicit: bool = False

    @field_validator('duration')
    @classmethod
    def validate_duration(cls, v):
        """Ensure duration is reasonable (max 1 hour)"""
        if v > 3600:
            raise ValueError('Track duration cannot exceed 1 hour')
        return v


class TrackCreate(TrackBase):
    """Schema for creating a track"""
    artist_ids: List[int] = Field(..., min_items=1)
    s3_key: str = Field(..., description="S3 object key for audio file")


class TrackUpdate(BaseSchema):
    """Schema for updating a track"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    album_id: Optional[int] = None
    duration: Optional[int] = Field(None, gt=0)
    cover_url: Optional[HttpUrl] = None
    genre: Optional[str] = Field(None, max_length=50)
    release_date: Optional[datetime] = None
    is_explicit: Optional[bool] = None


class TrackResponse(TrackBase):
    """Schema for track responses"""
    id: int
    play_count: int = 0
    like_count: int = 0
    created_at: datetime
    updated_at: datetime
    artists: List[ArtistResponse] = []
    album: Optional[AlbumResponse] = None
    signed_url: Optional[str] = None  # Pre-signed S3 URL

    model_config = ConfigDict(from_attributes=True)


class TrackStreamRequest(BaseSchema):
    """Schema for requesting a track stream URL"""
    quality: AudioQuality = AudioQuality.HIGH
    expires_in: int = Field(default=3600, ge=300, le=86400)  # 5 min to 24 hours


class TrackStreamResponse(BaseSchema):
    """Schema for track streaming response"""
    track_id: int
    stream_url: str
    quality: AudioQuality
    expires_at: datetime
    cdn_url: Optional[str] = None  # CloudFront URL if available


# ============================================================================
# PLAYLIST SCHEMAS
# ============================================================================

class PlaylistBase(BaseSchema):
    """Base playlist schema"""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    cover_url: Optional[HttpUrl] = None
    visibility: PlaylistVisibility = PlaylistVisibility.PUBLIC


class PlaylistCreate(PlaylistBase):
    """Schema for creating a playlist"""
    pass


class PlaylistUpdate(BaseSchema):
    """Schema for updating a playlist"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    cover_url: Optional[HttpUrl] = None
    visibility: Optional[PlaylistVisibility] = None


class PlaylistResponse(PlaylistBase):
    """Schema for playlist responses"""
    id: int
    user_id: int
    track_count: int = 0
    total_duration: int = 0  # in seconds
    follower_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PlaylistDetailResponse(PlaylistResponse):
    """Detailed playlist response with tracks"""
    tracks: List[TrackResponse] = []


class PlaylistAddTrackRequest(BaseSchema):
    """Schema for adding track to playlist"""
    track_id: int
    position: Optional[int] = None  # If None, append to end


class PlaylistReorderRequest(BaseSchema):
    """Schema for reordering playlist tracks"""
    track_id: int
    new_position: int = Field(..., ge=0)


# ============================================================================
# PLAY HISTORY SCHEMAS
# ============================================================================

class PlayHistoryCreate(BaseSchema):
    """Schema for recording play history"""
    track_id: int
    played_duration: int = Field(..., ge=0, description="Duration played in seconds")
    quality: AudioQuality = AudioQuality.HIGH


class PlayHistoryResponse(BaseSchema):
    """Schema for play history responses"""
    id: int
    user_id: int
    track_id: int
    track: TrackResponse
    played_at: datetime
    played_duration: int
    quality: AudioQuality
    completed: bool  # True if played > 80% of track

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# SEARCH SCHEMAS
# ============================================================================

class SearchQuery(BaseSchema):
    """Schema for search requests"""
    q: str = Field(..., min_length=1, max_length=200, description="Search query")
    types: List[str] = Field(
        default=["track", "artist", "album", "playlist"],
        description="Types to search: track, artist, album, playlist"
    )
    limit: int = Field(default=20, ge=1, le=50)
    offset: int = Field(default=0, ge=0)

    @field_validator('types')
    @classmethod
    def validate_types(cls, v):
        """Validate search types"""
        valid_types = {"track", "artist", "album", "playlist"}
        invalid = set(v) - valid_types
        if invalid:
            raise ValueError(f"Invalid search types: {invalid}")
        return v


class SearchResults(BaseSchema):
    """Schema for search results"""
    tracks: List[TrackResponse] = []
    artists: List[ArtistResponse] = []
    albums: List[AlbumResponse] = []
    playlists: List[PlaylistResponse] = []
    total_results: int = 0
    query: str
    took_ms: int = 0  # Search execution time


# ============================================================================
# ANALYTICS SCHEMAS
# ============================================================================

class TrackAnalytics(BaseSchema):
    """Schema for track analytics"""
    track_id: int
    play_count: int
    unique_listeners: int
    total_duration_played: int  # in seconds
    skip_rate: float = Field(..., ge=0, le=1)
    completion_rate: float = Field(..., ge=0, le=1)
    trending_score: float = 0.0
    period_start: datetime
    period_end: datetime


class ArtistAnalytics(BaseSchema):
    """Schema for artist analytics"""
    artist_id: int
    follower_count: int
    total_plays: int
    unique_listeners: int
    trending_tracks: List[TrackResponse] = []
    period_start: datetime
    period_end: datetime


class UserListeningStats(BaseSchema):
    """Schema for user listening statistics"""
    user_id: int
    total_plays: int
    total_listening_time: int  # in seconds
    favorite_genre: Optional[str] = None
    top_artists: List[ArtistResponse] = []
    top_tracks: List[TrackResponse] = []
    recently_played: List[PlayHistoryResponse] = []


# ============================================================================
# RECOMMENDATION SCHEMAS
# ============================================================================

class RecommendationRequest(BaseSchema):
    """Schema for recommendation requests"""
    seed_tracks: List[int] = Field(default=[], max_items=5)
    seed_artists: List[int] = Field(default=[], max_items=5)
    seed_genres: List[str] = Field(default=[], max_items=5)
    limit: int = Field(default=20, ge=1, le=50)
    
    @field_validator('seed_tracks', 'seed_artists', 'seed_genres')
    @classmethod
    def validate_seeds(cls, v, info):
        """Ensure at least one seed is provided"""
        # Check if we have any seeds across all fields
        values = info.data if info.data else {}
        total = len(v) + sum(
            len(values.get(field, []))
            for field in ['seed_tracks', 'seed_artists', 'seed_genres']
        )
        if total == 0:
            raise ValueError('At least one seed (track, artist, or genre) is required')
        return v


class RecommendationResponse(BaseSchema):
    """Schema for recommendation responses"""
    tracks: List[TrackResponse]
    seed_info: dict  # Information about seeds used
    algorithm: str  # Algorithm used for recommendations


# ============================================================================
# PAGINATION SCHEMAS
# ============================================================================

class PaginatedResponse(BaseSchema):
    """Generic paginated response"""
    items: List[BaseSchema]
    total: int
    page: int
    page_size: int
    total_pages: int


class PaginatedTracks(BaseSchema):
    """Paginated track response"""
    items: List[TrackResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class PaginatedArtists(BaseSchema):
    """Paginated artist response"""
    items: List[ArtistResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class PaginatedAlbums(BaseSchema):
    """Paginated album response"""
    items: List[AlbumResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class PaginatedPlaylists(BaseSchema):
    """Paginated playlist response"""
    items: List[PlaylistResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============================================================================
# UPLOAD SCHEMAS
# ============================================================================

class TrackUploadInitiate(BaseSchema):
    """Schema for initiating track upload"""
    filename: str = Field(..., max_length=255)
    file_size: int = Field(..., gt=0)
    content_type: str = Field(..., pattern=r'^audio/')

    @field_validator('file_size')
    @classmethod
    def validate_file_size(cls, v):
        """Ensure file size is reasonable (max 100MB)"""
        max_size = 100 * 1024 * 1024  # 100MB
        if v > max_size:
            raise ValueError(f'File size cannot exceed {max_size} bytes')
        return v


class TrackUploadResponse(BaseSchema):
    """Schema for track upload response"""
    upload_id: str
    s3_key: str
    presigned_url: str
    expires_at: datetime
    fields: dict  # Additional fields for multipart upload


# ============================================================================
# BULK OPERATION SCHEMAS
# ============================================================================

class BulkTrackCreate(BaseSchema):
    """Schema for bulk track creation"""
    tracks: List[TrackCreate] = Field(..., max_items=50)


class BulkOperationResponse(BaseSchema):
    """Schema for bulk operation response"""
    success_count: int
    failure_count: int
    errors: List[dict] = []
    created_ids: List[int] = []


# ============================================================================
# FORWARD REFERENCES
# ============================================================================

# Update forward references for circular dependencies
ArtistDetailResponse.model_rebuild()
AlbumDetailResponse.model_rebuild()
PlaylistDetailResponse.model_rebuild()
