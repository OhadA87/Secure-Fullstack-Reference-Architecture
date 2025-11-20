"""
User Models - Authentication and Authorization

File: apps/api_fastapi/models/user_models.py

Database models for user authentication and authorization.
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer,
    String, Table, Text
)
from sqlalchemy.orm import relationship
from passlib.context import CryptContext

from core.database import Base

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ============================================================================
# ASSOCIATION TABLES (Many-to-Many)
# ============================================================================

user_roles = Table(
    'user_roles',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE')),
    Column('role_id', Integer, ForeignKey('roles.id', ondelete='CASCADE'))
)


# ============================================================================
# ROLE MODEL
# ============================================================================

class Role(Base):
    """
    Role model for RBAC (Role-Based Access Control)

    Roles: user, curator, admin
    """
    __tablename__ = 'roles'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    permissions = Column(Text, nullable=True)  # JSON string of permissions
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    users = relationship('User', secondary=user_roles, back_populates='roles')

    def __repr__(self):
        return f"<Role {self.name}>"


# ============================================================================
# USER MODEL
# ============================================================================

class User(Base):
    """
    User model for authentication and authorization

    Supports:
    - Email/password authentication
    - OAuth (Google, Apple, GitHub)
    - Multiple roles
    - Refresh tokens
    """
    __tablename__ = 'users'

    # Primary key
    id = Column(Integer, primary_key=True, index=True)

    # Authentication
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=True)  # Nullable for OAuth users
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)

    # Profile
    full_name = Column(String(255), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    bio = Column(Text, nullable=True)

    # OAuth
    oauth_provider = Column(String(50), nullable=True)  # google, apple, github
    oauth_id = Column(String(255), nullable=True, index=True)

    # Security
    last_login = Column(DateTime, nullable=True)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)

    # Tokens
    refresh_token = Column(String(500), nullable=True)
    refresh_token_expires = Column(DateTime, nullable=True)

    # Verification
    verification_token = Column(String(255), nullable=True)
    verification_token_expires = Column(DateTime, nullable=True)

    # Password reset
    reset_token = Column(String(255), nullable=True)
    reset_token_expires = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)  # Soft delete

    # Relationships
    roles = relationship('Role', secondary=user_roles, back_populates='users')

    # Music relationships (will be added when music models are loaded)
    playlists = relationship('Playlist', back_populates='user', lazy='dynamic')
    play_history = relationship('PlayHistory', back_populates='user', lazy='dynamic')

    def __repr__(self):
        return f"<User {self.email}>"

    # ========================================================================
    # PASSWORD METHODS
    # ========================================================================

    def set_password(self, password: str) -> None:
        """Hash and set password"""
        self.hashed_password = pwd_context.hash(password)

    def verify_password(self, password: str) -> bool:
        """Verify password against hash"""
        if not self.hashed_password:
            return False
        return pwd_context.verify(password, self.hashed_password)

    # ========================================================================
    # ROLE METHODS
    # ========================================================================

    def has_role(self, role_name: str) -> bool:
        """Check if user has a specific role"""
        return any(role.name == role_name for role in self.roles)

    def add_role(self, role: Role) -> None:
        """Add role to user"""
        if role not in self.roles:
            self.roles.append(role)

    def remove_role(self, role: Role) -> None:
        """Remove role from user"""
        if role in self.roles:
            self.roles.remove(role)

    # ========================================================================
    # SECURITY METHODS
    # ========================================================================

    def is_locked(self) -> bool:
        """Check if account is locked due to failed login attempts"""
        if self.locked_until and self.locked_until > datetime.utcnow():
            return True
        return False

    def increment_failed_login(self) -> None:
        """Increment failed login attempts and lock if threshold reached"""
        self.failed_login_attempts += 1

        # Lock account after 5 failed attempts for 30 minutes
        if self.failed_login_attempts >= 5:
            from datetime import timedelta
            self.locked_until = datetime.utcnow() + timedelta(minutes=30)

    def reset_failed_login(self) -> None:
        """Reset failed login attempts on successful login"""
        self.failed_login_attempts = 0
        self.locked_until = None

    # ========================================================================
    # TOKEN METHODS
    # ========================================================================

    def set_refresh_token(self, token: str, expires_at: datetime) -> None:
        """Set refresh token"""
        self.refresh_token = token
        self.refresh_token_expires = expires_at

    def clear_refresh_token(self) -> None:
        """Clear refresh token"""
        self.refresh_token = None
        self.refresh_token_expires = None

    def is_refresh_token_valid(self, token: str) -> bool:
        """Check if refresh token is valid"""
        if not self.refresh_token or not self.refresh_token_expires:
            return False

        if self.refresh_token != token:
            return False

        if self.refresh_token_expires < datetime.utcnow():
            return False

        return True

    # ========================================================================
    # VERIFICATION METHODS
    # ========================================================================

    def set_verification_token(self, token: str, expires_at: datetime) -> None:
        """Set email verification token"""
        self.verification_token = token
        self.verification_token_expires = expires_at

    def verify_email(self, token: str) -> bool:
        """Verify email with token"""
        if not self.verification_token or not self.verification_token_expires:
            return False

        if self.verification_token != token:
            return False

        if self.verification_token_expires < datetime.utcnow():
            return False

        self.is_verified = True
        self.verification_token = None
        self.verification_token_expires = None
        return True

    # ========================================================================
    # PASSWORD RESET METHODS
    # ========================================================================

    def set_reset_token(self, token: str, expires_at: datetime) -> None:
        """Set password reset token"""
        self.reset_token = token
        self.reset_token_expires = expires_at

    def reset_password(self, token: str, new_password: str) -> bool:
        """Reset password with token"""
        if not self.reset_token or not self.reset_token_expires:
            return False

        if self.reset_token != token:
            return False

        if self.reset_token_expires < datetime.utcnow():
            return False

        self.set_password(new_password)
        self.reset_token = None
        self.reset_token_expires = None
        return True

    # ========================================================================
    # SOFT DELETE
    # ========================================================================

    def soft_delete(self) -> None:
        """Soft delete user"""
        self.deleted_at = datetime.utcnow()
        self.is_active = False

    def is_deleted(self) -> bool:
        """Check if user is soft deleted"""
        return self.deleted_at is not None