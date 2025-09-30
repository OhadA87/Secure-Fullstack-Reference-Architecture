import time
from typing import Callable

import structlog
from fastapi import Request, Response
from prometheus_client import Counter, Histogram
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from ..config import settings

logger = structlog.get_logger()

# Enhanced Prometheus metrics
REQUEST_COUNT = Counter(
    "http_requests_total", 
    "Total HTTP requests", 
    ["method", "endpoint", "status_code", "version"]
)

REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint", "status_code"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

REQUEST_SIZE = Histogram(
    "http_request_size_bytes",
    "HTTP request size in bytes",
    ["method", "endpoint"]
)

RESPONSE_SIZE = Histogram(
    "http_response_size_bytes", 
    "HTTP response size in bytes",
    ["method", "endpoint", "status_code"]
)

ACTIVE_REQUESTS = Counter(
    "http_active_requests",
    "Currently active HTTP requests",
    ["method", "endpoint"]
)

ERROR_COUNT = Counter(
    "http_errors_total",
    "Total HTTP errors",
    ["method", "endpoint", "status_code", "error_type"]
)

RATE_LIMIT_HITS = Counter(
    "rate_limit_hits_total",
    "Rate limit hits by endpoint and client",
    ["endpoint", "client_type"]
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Enhanced middleware for comprehensive request/response metrics and structured logging.
    
    Tracks:
    - Request/response times
    - Request/response sizes  
    - Status codes and error types
    - Active request counts
    - Detailed structured logs
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Start timing
        start_time = time.time()
        
        # Extract request information
        method = request.method
        path = self._normalize_path(request.url.path)
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "unknown")
        request_id = self._generate_request_id()
        
        # Calculate request size
        request_size = self._get_request_size(request)
        
        # Increment active requests
        ACTIVE_REQUESTS.labels(method=method, endpoint=path).inc()
        
        # Log request start
        logger.info(
            "request_started",
            request_id=request_id,
            method=method,
            path=path,
            client_ip=client_ip,
            user_agent=user_agent,
            request_size=request_size,
            timestamp=start_time
        )
        
        try:
            # Process request
            response = await call_next(request)
            
            # Calculate metrics
            duration = time.time() - start_time
            response_size = self._get_response_size(response)
            status_code = response.status_code
            
            # Update Prometheus metrics
            REQUEST_COUNT.labels(
                method=method,
                endpoint=path, 
                status_code=status_code,
                version=settings.API_VERSION
            ).inc()
            
            REQUEST_DURATION.labels(
                method=method,
                endpoint=path,
                status_code=status_code
            ).observe(duration)
            
            REQUEST_SIZE.labels(
                method=method,
                endpoint=path
            ).observe(request_size)
            
            RESPONSE_SIZE.labels(
                method=method,
                endpoint=path,
                status_code=status_code
            ).observe(response_size)
            
            # Log successful request
            logger.info(
                "request_completed",
                request_id=request_id,
                method=method,
                path=path,
                status_code=status_code,
                duration_seconds=duration,
                response_size=response_size,
                client_ip=client_ip
            )
            
            # Add performance headers
            response.headers["X-Response-Time"] = f"{duration:.3f}s"
            response.headers["X-Request-ID"] = request_id
            
            return response
            
        except Exception as e:
            # Calculate error metrics
            duration = time.time() - start_time
            error_type = type(e).__name__
            
            # Determine status code for error
            if isinstance(e, RateLimitExceeded):
                status_code = 429
            else:
                status_code = 500
            
            # Update error metrics
            ERROR_COUNT.labels(
                method=method,
                endpoint=path,
                status_code=status_code,
                error_type=error_type
            ).inc()
            
            # Log error
            logger.error(
                "request_failed",
                request_id=request_id,
                method=method,
                path=path,
                error_type=error_type,
                error_message=str(e),
                duration_seconds=duration,
                client_ip=client_ip
            )
            
            raise
        
        finally:
            # Decrement active requests
            ACTIVE_REQUESTS.labels(method=method, endpoint=path).dec()
    
    def _normalize_path(self, path: str) -> str:
        """Normalize URL path for metrics (remove IDs, etc.)."""
        # Replace UUIDs and numeric IDs with placeholders
        import re
        
        # Replace UUIDs
        path = re.sub(
            r'/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', 
            '/{uuid}', 
            path, 
            flags=re.IGNORECASE
        )
        
        # Replace numeric IDs
        path = re.sub(r'/\d+', '/{id}', path)
        
        # Limit path length for metrics
        if len(path) > 100:
            path = path[:97] + "..."
        
        return path
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address, considering proxy headers."""
        # Check if real IP was set by TrustedProxyMiddleware
        if hasattr(request.state, 'real_client_ip'):
            return request.state.real_client_ip
        
        # Fallback to direct client IP
        return request.client.host if request.client else "unknown"
    
    def _get_request_size(self, request: Request) -> int:
        """Calculate request size in bytes."""
        try:
            content_length = request.headers.get("content-length")
            return int(content_length) if content_length else 0
        except (ValueError, TypeError):
            return 0
    
    def _get_response_size(self, response: Response) -> int:
        """Calculate response size in bytes."""
        try:
            content_length = response.headers.get("content-length")
            if content_length:
                return int(content_length)
            
            # Estimate size from response body if available
            if hasattr(response, 'body') and response.body:
                return len(response.body)
            
            return 0
        except (ValueError, TypeError, AttributeError):
            return 0
    
    def _generate_request_id(self) -> str:
        """Generate unique request ID for tracing."""
        import uuid
        return str(uuid.uuid4())[:8]


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware to track rate limit hits and enhance rate limiting metrics.
    
    Works with SlowAPI to provide better observability of rate limiting.
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            response = await call_next(request)
            return response
        except RateLimitExceeded as e:
            # Extract rate limit information
            endpoint = self._normalize_path(request.url.path)
            client_type = self._get_client_type(request)
            
            # Update rate limit metrics
            RATE_LIMIT_HITS.labels(
                endpoint=endpoint,
                client_type=client_type
            ).inc()
            
            # Log rate limit hit
            logger.warning(
                "rate_limit_exceeded",
                endpoint=endpoint,
                client_ip=self._get_client_ip(request),
                client_type=client_type,
                user_agent=request.headers.get("user-agent", "unknown"),
                limit=str(e.detail) if hasattr(e, 'detail') else "unknown"
            )
            
            raise
    
    def _normalize_path(self, path: str) -> str:
        """Normalize path for rate limit metrics."""
        # Same normalization as MetricsMiddleware
        import re
        path = re.sub(
            r'/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', 
            '/{uuid}', 
            path, 
            flags=re.IGNORECASE
        )
        path = re.sub(r'/\d+', '/{id}', path)
        return path
    
    def _get_client_type(self, request: Request) -> str:
        """Determine client type for rate limiting categorization."""
        user_agent = request.headers.get("user-agent", "").lower()
        
        # Categorize based on User-Agent
        if any(bot in user_agent for bot in ["bot", "crawler", "spider", "scraper"]):
            return "bot"
        elif any(app in user_agent for app in ["mobile", "android", "ios", "flutter"]):
            return "mobile_app"
        elif any(browser in user_agent for browser in ["chrome", "firefox", "safari", "edge"]):
            return "browser"
        elif "postman" in user_agent or "insomnia" in user_agent:
            return "api_client"
        else:
            return "unknown"
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP for rate limiting."""
        if hasattr(request.state, 'real_client_ip'):
            return request.state.real_client_ip
        return request.client.host if request.client else "unknown"