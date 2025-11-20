"""
Music Models - Track, Artist, Album, Playlist database models

File: apps/api_fastapi/app/models/music.py

Database models for the music streaming platform.
"""

from datetime import datetime
from typing import List

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer,
    String, Table, Text, CheckConstraint, Index
)
from sqlalchemy.orm import relationship

from core.database import Base


# ============================================================================
# ASSOCIATION TABLES (Many-to-Many)
# ============================================================================

track_artists = Table(
    'track_artists',
    Base.metadata,
    Column('track_id', Integer, ForeignKey('tracks.id', ondelete='CASCADE')),
    Column('artist_id', Integer, ForeignKey('artists.id', ondelete='CASCADE')),
    Index('ix_track_artists_track_id', 'track_id'),
    Index('ix_track_artists_artist_id', 'artist_id')
)

playlist_tracks = Table(
    'playlist_tracks',
    Base.metadata,
    Column('playlist_id', Integer, ForeignKey('playlists.id', ondelete='CASCADE')),
    Column('track_id', Integer, ForeignKey('tracks.id', ondelete='CASCADE')),
    Column('position', Integer, nullable=False, default=0),
    Column('added_at', DateTime, default=datetime.utcnow),
    Index('ix_playlist_tracks_playlist_id', 'playlist_id'),
    Index('ix_playlist_tracks_track_id', 'track_id')
)


# ============================================================================
# ARTIST MODEL
# ============================================================================

class Artist(Base):
    """Artist model - represents music artists"""
    __tablename__ = 'artists'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    bio = Column(Text, nullable=True)
    image_url = Column(String(500), nullable=True)
    verified = Column(Boolean, default=False)
    follower_count = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    tracks = relationship('Track', secondary=track_artists, back_populates='artists')
    albums = relationship('Album', back_populates='artist', lazy='dynamic')

    # Indexes
    __table_args__ = (
        Index('ix_artists_name', 'name'),
        Index('ix_artists_verified', 'verified'),
    )

    def __repr__(self):
        return f"<Artist {self.name}>"


# ============================================================================
# ALBUM MODEL
# ============================================================================

class Album(Base):
    """Album model - collection of tracks"""
    __tablename__ = 'albums'

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False, index=True)
    artist_id = Column(Integer, ForeignKey('artists.id', ondelete='CASCADE'), nullable=False)
    release_date = Column(DateTime, nullable=True)
    cover_url = Column(String(500), nullable=True)
    genre = Column(String(50), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    artist = relationship('Artist', back_populates='albums')
    tracks = relationship('Track', back_populates='album', lazy='dynamic')

    # Indexes
    __table_args__ = (
        Index('ix_albums_title', 'title'),
        Index('ix_albums_artist_id', 'artist_id'),
        Index('ix_albums_genre', 'genre'),
        Index('ix_albums_release_date', 'release_date'),
    )

    def __repr__(self):
        return f"<Album {self.title}>"


# ============================================================================
# TRACK MODEL
# ============================================================================

class Track(Base):
    """Track model - individual music tracks"""
    __tablename__ = 'tracks'

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False, index=True)
    album_id = Column(Integer, ForeignKey('albums.id', ondelete='SET NULL'), nullable=True)
    duration = Column(Integer, nullable=False)  # Duration in seconds
    
    # File storage
    s3_key = Column(String(500), nullable=False)  # S3 object key
    audio_url = Column(String(500), nullable=True)  # Public URL if any
    cover_url = Column(String(500), nullable=True)
    
    # Metadata
    genre = Column(String(50), nullable=True, index=True)
    release_date = Column(DateTime, nullable=True)
    is_explicit = Column(Boolean, default=False)
    
    # Analytics
    play_count = Column(Integer, default=0)
    like_count = Column(Integer, default=0)
    
    # Uploader
    uploaded_by_user_id = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    artists = relationship('Artist', secondary=track_artists, back_populates='tracks')
    album = relationship('Album', back_populates='tracks')
    playlists = relationship('Playlist', secondary=playlist_tracks, back_populates='tracks')
    play_history = relationship('PlayHistory', back_populates='track', lazy='dynamic')

    # Constraints
    __table_args__ = (
        CheckConstraint('duration > 0', name='check_duration_positive'),
        CheckConstraint('play_count >= 0', name='check_play_count_non_negative'),
        CheckConstraint('like_count >= 0', name='check_like_count_non_negative'),
        Index('ix_tracks_title', 'title'),
        Index('ix_tracks_genre', 'genre'),
        Index('ix_tracks_play_count', 'play_count'),
        Index('ix_tracks_created_at', 'created_at'),
    )

    def __repr__(self):
        return f"<Track {self.title}>"


# ============================================================================
# PLAYLIST MODEL
# ============================================================================

class Playlist(Base):
    """Playlist model - user-created track collections"""
    __tablename__ = 'playlists'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)
    cover_url = Column(String(500), nullable=True)
    
    # Ownership
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    
    # Visibility
    visibility = Column(String(20), default='public')  # public, private, unlisted
    
    # Analytics
    follower_count = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship('User', back_populates='playlists')
    tracks = relationship('Track', secondary=playlist_tracks, back_populates='playlists')

    # Indexes
    __table_args__ = (
        Index('ix_playlists_user_id', 'user_id'),
        Index('ix_playlists_visibility', 'visibility'),
        Index('ix_playlists_name', 'name'),
    )

    def __repr__(self):
        return f"<Playlist {self.name}>"


# ============================================================================
# PLAY HISTORY MODEL
# ============================================================================

class PlayHistory(Base):
    """Play history - tracks when users play songs"""
    __tablename__ = 'play_history'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    track_id = Column(Integer, ForeignKey('tracks.id', ondelete='CASCADE'), nullable=False)
    
    played_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    played_duration = Column(Integer, nullable=False)  # How long they listened in seconds
    quality = Column(String(20), default='high')  # low, medium, high, lossless
    
    # Did they complete the track? (>80% played)
    completed = Column(Boolean, default=False)

    # Relationships
    user = relationship('User', back_populates='play_history')
    track = relationship('Track', back_populates='play_history')

    # Indexes
    __table_args__ = (
        Index('ix_play_history_user_id', 'user_id'),
        Index('ix_play_history_track_id', 'track_id'),
        Index('ix_play_history_played_at', 'played_at'),
        Index('ix_play_history_user_track', 'user_id', 'track_id'),
    )

    def __repr__(self):
        return f"<PlayHistory user={self.user_id} track={self.track_id}>"
