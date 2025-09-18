from functools import wraps
from typing import Callable, List, Optional

import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from prometheus_client import Counter

from .jwt import TokenData, jwt_manager

logger = structlog.get_logger()

# Prometheus metrics
RBAC_DENIALS = Counter(
    "rbac_denials_total", 
    "RBAC access denials", 
    ["required_roles", "user_roles", "endpoint"]
)

AUTH_FAILURES = Counter(
    "auth_failures_total",
    "Authentication failures",
    ["reason", "endpoint"]
)

# Security scheme
security = HTTPBearer()


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> TokenData:
    """Extract and validate JWT token, return user data."""
    endpoint = request.url.path
    
    if not credentials:
        AUTH_FAILURES.labels(reason="missing_token", endpoint=endpoint).inc()
        logger.warning("auth_failure_missing_token", endpoint=endpoint)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token_data = jwt_manager.decode_token(credentials.credentials)
    
    if not token_data:
        AUTH_FAILURES.labels(reason="invalid_token", endpoint=endpoint).inc()
        logger.warning("auth_failure_invalid_token", endpoint=endpoint)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if token_data.token_type != "access":
        AUTH_FAILURES.labels(reason="wrong_token_type", endpoint=endpoint).inc()
        logger.warning("auth_failure_wrong_token_type", 
                      endpoint=endpoint, token_type=token_data.token_type)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    logger.info("auth_success", user_id=token_data.user_id, endpoint=endpoint)
    return token_data


def require_roles(*required_roles: str) -> Callable:
    """
    RBAC decorator factory that checks if the current user has any of the required roles.
    
    Args:
        *required_roles: One or more roles that are allowed access
        
    Returns:
        Decorator function
        
    Example:
        @require_roles("admin", "moderator")
        async def admin_endpoint(current_user: TokenData = Depends(get_current_user)):
            return {"message": "Admin access granted"}
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract current_user from kwargs (injected by FastAPI Depends)
            current_user: Optional[TokenData] = None
            request: Optional[Request] = None
            
            # Find current_user and request in function arguments
            for key, value in kwargs.items():
                if isinstance(value, TokenData):
                    current_user = value
                elif isinstance(value, Request):
                    request = value
            
            # Extract request from args if not found in kwargs
            if not request:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break
            
            endpoint = request.url.path if request else func.__name__
            
            if not current_user:
                AUTH_FAILURES.labels(reason="missing_user_data", endpoint=endpoint).inc()
                logger.error("rbac_missing_user_data", endpoint=endpoint, function=func.__name__)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Internal authentication error"
                )
            
            # Check if user has any of the required roles
            user_roles_set = set(current_user.roles)
            required_roles_set = set(required_roles)
            
            if not user_roles_set.intersection(required_roles_set):
                RBAC_DENIALS.labels(
                    required_roles=",".join(sorted(required_roles)),
                    user_roles=",".join(sorted(current_user.roles)),
                    endpoint=endpoint
                ).inc()
                
                logger.warning("rbac_denial",
                             user_id=current_user.user_id,
                             user_roles=current_user.roles,
                             required_roles=list(required_roles),
                             endpoint=endpoint)
                
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions"
                )
            
            logger.info("rbac_success",
                       user_id=current_user.user_id,
                       user_roles=current_user.roles,
                       required_roles=list(required_roles),
                       endpoint=endpoint)
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


def require_admin() -> Callable:
    """Convenience decorator for admin-only endpoints."""
    return require_roles("admin")


def require_user() -> Callable:
    """Convenience decorator for user-level endpoints (user or admin)."""
    return require_roles("user", "admin")


class RBACChecker:
    """Utility class for programmatic role checking."""
    
    @staticmethod
    def has_role(user: TokenData, role: str) -> bool:
        """Check if user has a specific role."""
        return role in user.roles
    
    @staticmethod
    def has_any_role(user: TokenData, roles: List[str]) -> bool:
        """Check if user has any of the specified roles."""
        return bool(set(user.roles).intersection(set(roles)))
    
    @staticmethod
    def has_all_roles(user: TokenData, roles: List[str]) -> bool:
        """Check if user has all of the specified roles."""
        return set(roles).issubset(set(user.roles))
    
    @staticmethod
    def is_admin(user: TokenData) -> bool:
        """Check if user is an admin."""
        return "admin" in user.roles
    
    @staticmethod
    def is_user(user: TokenData) -> bool:
        """Check if user has user role or higher."""
        return "user" in user.roles or "admin" in user.roles