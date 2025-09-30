"""
Production-ready FastAPI application with comprehensive security, observability, and scalability features.

Features:
- JWT authentication with RBAC
- Async database with SQLAlchemy
- Redis for caching and rate limiting
- Comprehensive security headers
- Prometheus metrics and structured logging
- Global exception handling
- Health checks with dependency validation
- Rate limiting and monitoring
"""

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Annotated, Dict, Any

import redis.asyncio as redis
import structlog
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from prometheus_client import generate_latest
from pydantic import ValidationError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import settings
from .database import init_database, get_db, check_database_health, close_database, get_database_pool_info
from .middleware import SecurityHeadersMiddleware, MetricsMiddleware, RateLimitMiddleware, TrustedProxyMiddleware
from .security.jwt import JWTTokens, jwt_manager
from .security.rbac import get_current_user, require_roles, TokenData, RBAC_DENIALS, AUTH_FAILURES

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Redis clients
redis_cache = None
redis_sessions = None

# Rate limiting
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.get_redis_url(settings.REDIS_RATE_LIMIT_DB),
    default_limits=[settings.DEFAULT_RATE_LIMIT]
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events - startup and shutdown."""
    
    # Startup
    logger.info("application_startup_begin", 
                service=settings.API_TITLE, 
                version=settings.API_VERSION,
                environment=settings.ENV)
    
    try:
        # Initialize database
        await init_database()
        logger.info("database_initialized")
        
        # Initialize Redis connections
        global redis_cache, redis_sessions
        redis_cache = redis.from_url(
            settings.get_redis_url(settings.REDIS_CACHE_DB),
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            retry_on_timeout=True
        )
        redis_sessions = redis.from_url(
            settings.get_redis_url(settings.REDIS_SESSION_DB),
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            retry_on_timeout=True
        )
        
        # Test Redis connections
        await redis_cache.ping()
        await redis_sessions.ping()
        logger.info("redis_connections_established", 
                   cache_db=settings.REDIS_CACHE_DB,
                   session_db=settings.REDIS_SESSION_DB)
        
        # Create default roles if they don't exist
        await _create_default_roles()
        
        logger.info("application_startup_complete")
        
    except Exception as e:
        logger.error("application_startup_failed", error=str(e))
        raise
    
    yield
    
    # Shutdown
    logger.info("application_shutdown_begin")
    
    try:
        # Close Redis connections
        if redis_cache:
            await redis_cache.close()
        if redis_sessions:
            await redis_sessions.close()
        logger.info("redis_connections_closed")
        
        # Close database connections
        await close_database()
        
        logger.info("application_shutdown_complete")
        
    except Exception as e:
        logger.error("application_shutdown_error", error=str(e))


async def _create_default_roles():
    """Create default roles in database if they don't exist."""
    try:
        from .database.models import Role, DEFAULT_ROLES
        from .database import AsyncSessionLocal
        
        async with AsyncSessionLocal() as session:
            for role_data in DEFAULT_ROLES:
                # Check if role exists
                from sqlalchemy import select
                result = await session.execute(
                    select(Role).where(Role.name == role_data["name"])
                )
                existing_role = result.scalar_one_or_none()
                
                if not existing_role:
                    # Create new role
                    role = Role(
                        name=role_data["name"],
                        description=role_data["description"],
                        permissions=role_data["permissions"]
                    )
                    session.add(role)
            
            await session.commit()
            logger.info("default_roles_created")
            
    except Exception as e:
        logger.error("default_roles_creation_failed", error=str(e))


# Initialize FastAPI app
app = FastAPI(
    title=settings.API_TITLE,
    description=settings.API_DESCRIPTION,
    version=settings.API_VERSION,
    docs_url=settings.get_docs_url(),
    redoc_url=settings.get_redoc_url(),
    lifespan=lifespan,
    # Disable default exception handlers to use our custom ones
    exception_handlers={}
)

# Security middleware (order matters!)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)
app.add_middleware(TrustedProxyMiddleware, trusted_proxies=settings.TRUSTED_PROXIES)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(MetricsMiddleware)
app.add_middleware(RateLimitMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Response-Time", "X-RateLimit-Limit", "X-RateLimit-Remaining"]
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# =====================================
# GLOBAL EXCEPTION HANDLERS
# =====================================

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle HTTP exceptions with structured logging."""
    
    logger.warning(
        "http_exception",
        status_code=exc.status_code,
        detail=exc.detail,
        path=request.url.path,
        method=request.method,
        client_ip=getattr(request.state, 'real_client_ip', 'unknown'),
        user_agent=request.headers.get("user-agent", "unknown")
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "timestamp": time.time(),
            "path": request.url.path
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors."""
    
    logger.warning(
        "validation_error",
        errors=exc.errors(),
        path=request.url.path,
        method=request.method,
        client_ip=getattr(request.state, 'real_client_ip', 'unknown')
    )
    
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation failed",
            "details": exc.errors(),
            "status_code": 422,
            "timestamp": time.time()
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    
    logger.error(
        "internal_server_error",
        error_type=type(exc).__name__,
        error_message=str(exc),
        path=request.url.path,
        method=request.method,
        client_ip=getattr(request.state, 'real_client_ip', 'unknown'),
        exc_info=True
    )
    
    # Don't expose internal error details in production
    if settings.is_production():
        error_detail = "Internal server error"
    else:
        error_detail = f"{type(exc).__name__}: {str(exc)}"
    
    return JSONResponse(
        status_code=500,
        content={
            "error": error_detail,
            "status_code": 500,
            "timestamp": time.time()
        }
    )


# =====================================
# HEALTH CHECK ENDPOINTS
# =====================================

@app.get("/health")
@limiter.limit("60/minute")
async def health_check(request: Request):
    """
    Comprehensive health check with dependency validation.
    Used by load balancers, Kubernetes probes, and monitoring systems.
    """
    start_time = time.time()
    
    checks = {
        "status": "healthy",
        "timestamp": start_time,
        "service": settings.API_TITLE,
        "version": settings.API_VERSION,
        "environment": settings.ENV
    }
    
    overall_healthy = True
    
    # Check database
    try:
        db_healthy = await check_database_health()
        checks["database"] = "healthy" if db_healthy else "unhealthy"
        if not db_healthy:
            overall_healthy = False
            
        # Add database pool info
        pool_info = get_database_pool_info()
        checks["database_pool"] = pool_info
        
    except Exception as e:
        logger.error("health_check_database_failed", error=str(e))
        checks["database"] = "unhealthy"
        overall_healthy = False
    
    # Check Redis cache
    try:
        if redis_cache:
            await redis_cache.ping()
            checks["redis_cache"] = "healthy"
        else:
            checks["redis_cache"] = "not_configured"
    except Exception as e:
        logger.error("health_check_redis_cache_failed", error=str(e))
        checks["redis_cache"] = "unhealthy"
        overall_healthy = False
    
    # Check Redis sessions
    try:
        if redis_sessions:
            await redis_sessions.ping()
            checks["redis_sessions"] = "healthy"
        else:
            checks["redis_sessions"] = "not_configured"
    except Exception as e:
        logger.error("health_check_redis_sessions_failed", error=str(e))
        checks["redis_sessions"] = "unhealthy"
        overall_healthy = False
    
    # Overall status
    checks["status"] = "healthy" if overall_healthy else "degraded"
    checks["response_time_ms"] = round((time.time() - start_time) * 1000, 2)
    
    status_code = 200 if overall_healthy else 503
    
    return JSONResponse(
        status_code=status_code,
        content=checks
    )


@app.get("/health/live")
async def liveness_probe():
    """Kubernetes liveness probe - simple check that app is running."""
    return {"status": "alive", "timestamp": time.time()}


@app.get("/health/ready")
async def readiness_probe():
    """Kubernetes readiness probe - check if app is ready to serve traffic."""
    try:
        # Quick database check
        db_healthy = await check_database_health()
        if not db_healthy:
            raise HTTPException(status_code=503, detail="Database not ready")
        
        return {"status": "ready", "timestamp": time.time()}
    
    except Exception as e:
        logger.error("readiness_probe_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Not ready")


# =====================================
# METRICS ENDPOINT
# =====================================

@app.get("/metrics")
async def get_metrics():
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_latest(),
        media_type="text/plain; version=0.0.4; charset=utf-8"
    )


# =====================================
# AUTHENTICATION ENDPOINTS
# =====================================

from .database.models import User
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str


@app.post("/auth/login", response_model=JWTTokens)
@limiter.limit("10/minute")
async def login(request: Request, credentials: LoginRequest, db: AsyncSession = Depends(get_db)):
    """User authentication with database validation."""
    
    logger.info("login_attempt", email=credentials.email)
    
    try:
        # Look up user in database
        from sqlalchemy import select
        result = await db.execute(
            select(User).where(User.email == credentials.email)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            AUTH_FAILURES.labels(reason="user_not_found", endpoint="/auth/login").inc()
            logger.warning("login_failure_user_not_found", email=credentials.email)
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Check if account is locked
        if user.is_account_locked():
            AUTH_FAILURES.labels(reason="account_locked", endpoint="/auth/login").inc()
            logger.warning("login_failure_account_locked", email=credentials.email)
            raise HTTPException(status_code=423, detail="Account is locked")
        
        # Verify password
        if not pwd_context.verify(credentials.password, user.password_hash):
            # Increment failed attempts
            user.failed_login_attempts += 1
            await db.commit()
            
            AUTH_FAILURES.labels(reason="invalid_password", endpoint="/auth/login").inc()
            logger.warning("login_failure_invalid_password", 
                          email=credentials.email,
                          failed_attempts=user.failed_login_attempts)
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        # Reset failed attempts on successful login
        user.failed_login_attempts = 0
        user.last_login = time.time()
        await db.commit()
        
        # Generate JWT tokens
        tokens = jwt_manager.create_tokens(
            user_id=str(user.id),
            email=user.email,
            roles=user.get_role_names()
        )
        
        # Store refresh token in database
        from .database.models import RefreshToken
        from datetime import datetime, timedelta
        
        refresh_token_record = RefreshToken(
            token=tokens.refresh_token,
            user_id=user.id,
            expires_at=datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            user_agent=request.headers.get("user-agent"),
            ip_address=getattr(request.state, 'real_client_ip', 'unknown')
        )
        db.add(refresh_token_record)
        await db.commit()
        
        logger.info("login_success", email=credentials.email, user_id=str(user.id))
        return tokens
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("login_error", email=credentials.email, error=str(e))
        raise HTTPException(status_code=500, detail="Login failed")


@app.post("/auth/refresh")
@limiter.limit("20/minute") 
async def refresh_token(request: Request, refresh_token: str, db: AsyncSession = Depends(get_db)):
    """Refresh access token using refresh token."""
    
    try:
        # Validate refresh token in database
        from sqlalchemy import select
        result = await db.execute(
            select(User).join(User.refresh_tokens).where(
                User.refresh_tokens.any(token=refresh_token, is_revoked=False)
            )
        )
        user = result.scalar_one_or_none()
        
        if not user:
            AUTH_FAILURES.labels(reason="invalid_refresh_token", endpoint="/auth/refresh").inc()
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        
        # Generate new access token
        new_access_token = jwt_manager.create_access_token(
            user_id=str(user.id),
            email=user.email,
            roles=user.get_role_names()
        )
        
        return {
            "access_token": new_access_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("refresh_token_error", error=str(e))
        raise HTTPException(status_code=500, detail="Token refresh failed")


# =====================================
# PROTECTED ENDPOINTS
# =====================================

@app.get("/protected/user")
@limiter.limit("60/minute")
@require_roles("user", "admin")
async def user_endpoint(request: Request, current_user: TokenData = Depends(get_current_user)):
    """User-level protected endpoint."""
    return {
        "message": "User access granted",
        "user_id": current_user.user_id,
        "email": current_user.email,
        "roles": current_user.roles,
        "timestamp": time.time()
    }


@app.get("/protected/admin")
@limiter.limit("30/minute")
@require_roles("admin")
async def admin_endpoint(request: Request, current_user: TokenData = Depends(get_current_user)):
    """Admin-only protected endpoint."""
    return {
        "message": "Admin access granted",
        "user_id": current_user.user_id,
        "admin_level": "full",
        "timestamp": time.time()
    }


# =====================================
# DEMO DATA ENDPOINTS
# =====================================

@app.get("/api/tracks")
@limiter.limit("100/minute")
async def get_tracks(
    request: Request,
    limit: int = 20,
    offset: int = 0,
    current_user: TokenData = Depends(get_current_user)
):
    """Get tracks - demo endpoint for Flutter app."""
    
    # Demo data
    tracks = [
        {
            "id": i + offset,
            "title": f"Track {i + offset}",
            "artist": f"Artist {(i + offset) % 10}",
            "album": f"Album {(i + offset) % 5}",
            "duration": 180 + ((i + offset) * 10),
            "popularity": max(0, 100 - (i + offset)),
            "preview_url": f"https://cdn.example.com/preview/{i + offset}.mp3",
            "cover_url": f"https://cdn.example.com/covers/{i + offset}.jpg"
        }
        for i in range(1, min(limit + 1, 51))
    ]
    
    return {
        "tracks": tracks,
        "total": len(tracks),
        "limit": limit,
        "offset": offset,
        "user_id": current_user.user_id
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        access_log=True,
        log_config=None  # Use our structured logging
    )