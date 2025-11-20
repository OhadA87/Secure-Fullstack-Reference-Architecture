"""
Permissions and RBAC Support

File: apps/api_fastapi/app/security/permissions.py

Defines permissions and role-based access control utilities.
"""

from enum import Enum
from typing import List, Set
from functools import wraps

from fastapi import HTTPException, status, Depends
from models.user_models import User
from .rbac import get_current_user


class Permission(str, Enum):
    """System permissions"""
    # Track permissions
    TRACK_CREATE = "track:create"
    TRACK_READ = "track:read"
    TRACK_UPDATE = "track:update"
    TRACK_DELETE = "track:delete"
    TRACK_UPLOAD = "track:upload"

    # Artist permissions
    ARTIST_CREATE = "artist:create"
    ARTIST_READ = "artist:read"
    ARTIST_UPDATE = "artist:update"
    ARTIST_DELETE = "artist:delete"

    # Album permissions
    ALBUM_CREATE = "album:create"
    ALBUM_READ = "album:read"
    ALBUM_UPDATE = "album:update"
    ALBUM_DELETE = "album:delete"

    # Playlist permissions
    PLAYLIST_CREATE = "playlist:create"
    PLAYLIST_READ = "playlist:read"
    PLAYLIST_UPDATE = "playlist:update"
    PLAYLIST_DELETE = "playlist:delete"

    # User permissions
    USER_CREATE = "user:create"
    USER_READ = "user:read"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"

    # Admin permissions
    ADMIN_READ = "admin:read"
    ADMIN_WRITE = "admin:write"
    ADMIN_DELETE = "admin:delete"

    # Analytics permissions
    ANALYTICS_READ = "analytics:read"
    ANALYTICS_WRITE = "analytics:write"


# Role-based permissions mapping
USER_PERMISSIONS = {
    Permission.TRACK_READ,
    Permission.ARTIST_READ,
    Permission.ALBUM_READ,
    Permission.PLAYLIST_CREATE,
    Permission.PLAYLIST_READ,
    Permission.PLAYLIST_UPDATE,
    Permission.PLAYLIST_DELETE,
}

CURATOR_PERMISSIONS = {
    *USER_PERMISSIONS,
    Permission.TRACK_CREATE,
    Permission.TRACK_UPDATE,
    Permission.TRACK_UPLOAD,
    Permission.ARTIST_CREATE,
    Permission.ARTIST_UPDATE,
    Permission.ALBUM_CREATE,
    Permission.ALBUM_UPDATE,
}

ADMIN_PERMISSIONS = {
    # All permissions
    *[p for p in Permission]
}

ROLE_PERMISSIONS: dict[str, Set[Permission]] = {
    "user": USER_PERMISSIONS,
    "curator": CURATOR_PERMISSIONS,
    "admin": ADMIN_PERMISSIONS,
}


def get_user_permissions(user: User) -> Set[Permission]:
    """Get all permissions for a user based on their roles"""
    permissions = set()
    for role in user.roles:
        role_permissions = ROLE_PERMISSIONS.get(role.name, set())
        permissions.update(role_permissions)
    return permissions


def has_permission(user: User, permission: Permission) -> bool:
    """Check if user has a specific permission"""
    user_permissions = get_user_permissions(user)
    return permission in user_permissions


def require_permission(permission: Permission):
    """
    Dependency factory that requires a specific permission

    Args:
        permission: Required permission

    Returns:
        Dependency function that validates the permission
    """
    async def dependency(current_user: User = Depends(get_current_user)):
        if not has_permission(current_user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission.value}' required"
            )
        return current_user
    return dependency


def require_any_permission(*permissions: Permission):
    """
    Dependency factory that requires any of the specified permissions

    Args:
        *permissions: Any of these permissions are acceptable

    Returns:
        Dependency function that validates permissions
    """
    async def dependency(current_user: User = Depends(get_current_user)):
        user_permissions = get_user_permissions(current_user)
        if not any(p in user_permissions for p in permissions):
            permission_names = [p.value for p in permissions]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"One of these permissions required: {', '.join(permission_names)}"
            )
        return current_user
    return dependency


def require_all_permissions(*permissions: Permission):
    """
    Dependency factory that requires all specified permissions

    Args:
        *permissions: All of these permissions are required

    Returns:
        Dependency function that validates permissions
    """
    async def dependency(current_user: User = Depends(get_current_user)):
        user_permissions = get_user_permissions(current_user)
        missing_permissions = set(permissions) - user_permissions
        if missing_permissions:
            permission_names = [p.value for p in missing_permissions]
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permissions: {', '.join(permission_names)}"
            )
        return current_user
    return dependency