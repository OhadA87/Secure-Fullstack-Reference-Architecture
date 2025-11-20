import hashlib
import time
from contextlib import asynccontextmanager
from typing import Annotated

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, generate_latest
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .config import settings
from .security.jwt import JWTTokens, jwt_manager
from .security.rbac import get_current_user, require_roles, TokenData, RBAC_DENIALS, AUTH_FAILURES

# Metrics
REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"])
REQUEST_DURATION = Histogram("http_request_duration_seconds", "HTTP request duration")
RATE_LIMIT_HITS = Counter("rate_limit_hits_total", "Rate limit hits", ["endpoint"])

# Auth metrics are imported from security.rbac

# Rate limiting
limiter = Limiter(key_func=get_remote_address)

# Structured logging
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("application_startup", service="api", version="0.1.0")
    yield
    logger.info("application_shutdown", service="api")


app = FastAPI(
    title="Spotify Clone API",
    description="Backend API for Flutter Spotify Clone",
    version="0.1.0",
    lifespan=lifespan
)

# CORS configuration from settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Rate limit tracking middleware
@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    try:
        response = await call_next(request)
        return response
    except RateLimitExceeded:
        RATE_LIMIT_HITS.labels(endpoint=request.url.path).inc()
        logger.warning("rate_limit_hit", endpoint=request.url.path, 
                      client_ip=get_remote_address(request))
        raise


# Models
class HealthResponse(BaseModel):
    status: str
    timestamp: float
    service: str
    version: str


class LoginRequest(BaseModel):
    email: str
    password: str


# AuthTokens model moved to security.jwt


# Mock user database (remove when real DB is implemented)
MOCK_USERS = {
    "demo@example.com": {
        "user_id": "user_123",
        "email": "demo@example.com",
        "password_hash": "demo_hash",  # In production: bcrypt hash
        "roles": ["user"]
    },
    "admin@example.com": {
        "user_id": "admin_456",
        "email": "admin@example.com", 
        "password_hash": "admin_hash",
        "roles": ["admin", "user"]
    }
}

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Mock password verification - replace with bcrypt in production."""
    # In production: return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())
    return plain_password + "_hash" == hashed_password


# Middleware for metrics
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()
    REQUEST_DURATION.observe(duration)
    
    return response


# Health endpoint
@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="healthy",
        timestamp=time.time(),
        service="api",
        version="0.1.0"
    )


# Auth endpoints
@app.post("/auth/login", response_model=JWTTokens)
@limiter.limit("10/minute")
async def login(request: Request, req: LoginRequest):
    """Login endpoint with JWT token generation."""
    logger.info("login_attempt", email=req.email)
    
    # Look up user in mock database
    user = MOCK_USERS.get(req.email)
    if not user:
        AUTH_FAILURES.labels(reason="user_not_found", endpoint="/auth/login").inc()
        logger.warning("login_failure_user_not_found", email=req.email)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Verify password
    if not verify_password(req.password, user["password_hash"]):
        AUTH_FAILURES.labels(reason="invalid_password", endpoint="/auth/login").inc()
        logger.warning("login_failure_invalid_password", email=req.email)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Generate JWT tokens
    tokens = jwt_manager.create_tokens(
        user_id=user["user_id"],
        email=user["email"],
        roles=user["roles"]
    )
    
    # TODO: Store refresh token in Redis with TTL
    
    logger.info("login_success", email=req.email, user_id=user["user_id"])
    return tokens


# Metrics endpoint
@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return generate_latest()


# Protected endpoint examples
@app.get("/protected/user")
@require_roles("user", "admin")
async def user_endpoint(request: Request, current_user: TokenData = Depends(get_current_user)):
    """User-level protected endpoint."""
    return {
        "message": "User access granted",
        "user_id": current_user.user_id,
        "email": current_user.email,
        "roles": current_user.roles
    }

@app.get("/protected/admin")
@require_roles("admin")
async def admin_endpoint(request: Request, current_user: TokenData = Depends(get_current_user)):
    """Admin-only protected endpoint."""
    return {
        "message": "Admin access granted",
        "user_id": current_user.user_id,
        "admin_level": "full"
    }

@app.post("/auth/refresh")
async def refresh_token(request: Request, refresh_token: str):
    """Refresh access token using refresh token."""
    new_access_token = jwt_manager.refresh_access_token(refresh_token)
    
    if not new_access_token:
        AUTH_FAILURES.labels(reason="invalid_refresh_token", endpoint="/auth/refresh").inc()
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    return {"access_token": new_access_token, "token_type": "bearer"}


# Include music routes
try:
    from routes.music import router as music_router
    app.include_router(music_router)
except ImportError as e:
    logger.warning("music_routes_not_loaded", error=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)