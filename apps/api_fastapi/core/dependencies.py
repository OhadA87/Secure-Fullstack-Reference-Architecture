"""
Core Dependencies for FastAPI Application

File: apps/api_fastapi/core/dependencies.py

Common dependencies used across the application.
"""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from .database import get_db
from models.user_models import User
from app.security.rbac import get_current_user as rbac_get_current_user

# Re-export for convenience
get_current_user = rbac_get_current_user


def require_role(role: str):
    """
    Dependency factory for role-based access control.

    Args:
        role: Required role name

    Returns:
        Dependency function
    """
    async def dependency(current_user: User = Depends(get_current_user)):
        if not current_user.has_role(role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' required"
            )
        return current_user
    return dependency


def require_any_role(*roles: str):
    """
    Dependency factory for multiple role access control.

    Args:
        *roles: Any of these roles are allowed

    Returns:
        Dependency function
    """
    async def dependency(current_user: User = Depends(get_current_user)):
        if not any(current_user.has_role(role) for role in roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"One of these roles required: {', '.join(roles)}"
            )
        return current_user
    return dependency


def require_admin():
    """Convenience dependency for admin access"""
    return require_role("admin")


def require_curator():
    """Convenience dependency for curator access"""
    return require_any_role("curator", "admin")