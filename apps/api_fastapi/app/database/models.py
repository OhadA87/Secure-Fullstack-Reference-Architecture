import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Column, String, Boolean, DateTime, Text, Integer, Table, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func

Base = declarative_base()

# Association table for user roles (many-to-many)
user_roles = Table(
    'user_roles',
    Base.metadata,
    Column('user_id', UUID(as_uuid=True), ForeignKey('users.id'), primary_key=True),
    Column('role_id', UUID(as_uuid=True), ForeignKey('roles.id'), primary_key=True)
)


class User(Base):
    """User model for authentication and authorization."""
    
    __tablename__ = "users"
    
    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4,
        index=True
    )
    
    # Authentication fields
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Profile information
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String(50), unique=True, index=True, nullable=True)
    
    # Account status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    last_login: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    # Security fields
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    password_changed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    # OAuth fields (for future Spotify integration)
    spotify_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    spotify_access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    spotify_refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Relationships
    roles: Mapped[List["Role"]] = relationship(
        "Role",
        secondary=user_roles,
        back_populates="users",
        lazy="selectin"
    )
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"
    
    def has_role(self, role_name: str) -> bool:
        """Check if user has a specific role."""
        return any(role.name == role_name for role in self.roles)
    
    def get_role_names(self) -> List[str]:
        """Get list of role names for this user."""
        return [role.name for role in self.roles]
    
    def is_account_locked(self) -> bool:
        """Check if account is currently locked."""
        if not self.locked_until:
            return False
        return datetime.utcnow() < self.locked_until


class Role(Base):
    """Role model for RBAC."""
    
    __tablename__ = "roles"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Permissions (stored as array of strings)
    permissions: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(String), 
        nullable=True,
        default=list
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now()
    )
    
    # Relationships
    users: Mapped[List[User]] = relationship(
        "User",
        secondary=user_roles,
        back_populates="roles"
    )
    
    def __repr__(self) -> str:
        return f"<Role(name={self.name})>"


class RefreshToken(Base):
    """Refresh token model for JWT token management."""
    
    __tablename__ = "refresh_tokens"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    token: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey('users.id'),
        nullable=False
    )
    
    # Token metadata
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now()
    )
    
    # Security fields
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    # Client information
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)  # IPv6 compatible
    
    # Relationships
    user: Mapped[User] = relationship("User", back_populates="refresh_tokens")
    
    def __repr__(self) -> str:
        return f"<RefreshToken(id={self.id}, user_id={self.user_id})>"
    
    def is_expired(self) -> bool:
        """Check if refresh token is expired."""
        return datetime.utcnow() > self.expires_at
    
    def is_valid(self) -> bool:
        """Check if refresh token is valid (not expired and not revoked)."""
        return not self.is_expired() and not self.is_revoked


class AuditLog(Base):
    """Audit log for security events."""
    
    __tablename__ = "audit_logs"
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4
    )
    
    # Event information
    event_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    event_description: Mapped[str] = mapped_column(Text, nullable=False)
    
    # User information
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True  # Some events might not have a user
    )
    user_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Request information
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    endpoint: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    request_method: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    
    # Additional metadata
    metadata: Mapped[Optional[dict]] = mapped_column(Text, nullable=True)  # JSON string
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        index=True
    )
    
    def __repr__(self) -> str:
        return f"<AuditLog(event_type={self.event_type}, user_id={self.user_id})>"


# Create default roles (will be inserted during database initialization)
DEFAULT_ROLES = [
    {
        "name": "admin",
        "description": "Full system access",
        "permissions": ["*"]  # Wildcard for all permissions
    },
    {
        "name": "user", 
        "description": "Standard user access",
        "permissions": ["read:own_profile", "update:own_profile", "read:tracks", "create:playlists"]
    },
    {
        "name": "moderator",
        "description": "Content moderation access", 
        "permissions": ["read:all_users", "moderate:content", "read:tracks", "manage:playlists"]
    }
]