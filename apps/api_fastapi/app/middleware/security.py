import time
from typing import Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ..config import settings

logger = structlog.get_logger()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers to all responses.
    
    Implements OWASP recommended security headers:
    - X-Content-Type-Options: Prevent MIME sniffing
    - X-Frame-Options: Prevent clickjacking  
    - X-XSS-Protection: Enable XSS filtering
    - Strict-Transport-Security: Force HTTPS
    - Referrer-Policy: Control referrer information
    - Permissions-Policy: Control browser features
    """
    
    def __init__(self, app):
        super().__init__(app)
        self.hsts_max_age = 31536000  # 1 year
        self.include_subdomains = True
        
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Process request
        response = await call_next(request)
        
        # Add security headers
        self._add_security_headers(response)
        
        # Log security events if needed
        self._log_security_events(request, response)
        
        return response
    
    def _add_security_headers(self, response: Response) -> None:
        """Add comprehensive security headers to response."""
        
        # Prevent MIME sniffing attacks
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # Prevent clickjacking attacks
        response.headers["X-Frame-Options"] = "DENY"
        
        # Enable XSS filtering (legacy but still useful)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # Force HTTPS in production
        if settings.is_production():
            hsts_value = f"max-age={self.hsts_max_age}"
            if self.include_subdomains:
                hsts_value += "; includeSubDomains"
            hsts_value += "; preload"
            response.headers["Strict-Transport-Security"] = hsts_value
        
        # Control referrer information leakage
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Control browser features (Permissions Policy)
        permissions_policy = [
            "geolocation=()",  # Disable geolocation
            "microphone=()",   # Disable microphone
            "camera=()",       # Disable camera
            "payment=()",      # Disable payment API
            "usb=()",          # Disable USB API
            "magnetometer=()", # Disable magnetometer
            "accelerometer=()", # Disable accelerometer
            "gyroscope=()"     # Disable gyroscope
        ]
        response.headers["Permissions-Policy"] = ", ".join(permissions_policy)
        
        # Content Security Policy (CSP) - restrictive default
        if settings.is_production():
            csp_directives = [
                "default-src 'self'",
                "script-src 'self' 'unsafe-inline'",  # Allow inline scripts for API docs
                "style-src 'self' 'unsafe-inline'",   # Allow inline styles for API docs
                "img-src 'self' data: https:",        # Allow images from self, data URLs, and HTTPS
                "font-src 'self'",
                "connect-src 'self'",
                "media-src 'self'",
                "object-src 'none'",
                "frame-src 'none'",
                "base-uri 'self'",
                "form-action 'self'"
            ]
            response.headers["Content-Security-Policy"] = "; ".join(csp_directives)
        
        # Remove server information disclosure
        response.headers.pop("Server", None)
        
        # Add custom security header for API identification
        response.headers["X-API-Version"] = settings.API_VERSION
        response.headers["X-RateLimit-Policy"] = "See API documentation"
    
    def _log_security_events(self, request: Request, response: Response) -> None:
        """Log security-relevant events."""
        
        # Log potential security issues
        user_agent = request.headers.get("user-agent", "")
        
        # Detect potential malicious requests
        suspicious_patterns = [
            "sqlmap", "nikto", "nmap", "dirb", "gobuster", 
            "burpsuite", "owasp", "zap", "w3af"
        ]
        
        if any(pattern in user_agent.lower() for pattern in suspicious_patterns):
            logger.warning(
                "suspicious_user_agent_detected",
                user_agent=user_agent,
                ip_address=request.client.host if request.client else "unknown",
                path=request.url.path,
                method=request.method
            )
        
        # Log admin access attempts
        if "/admin" in request.url.path:
            logger.info(
                "admin_access_attempt",
                path=request.url.path,
                method=request.method,
                status_code=response.status_code,
                ip_address=request.client.host if request.client else "unknown",
                user_agent=user_agent
            )
        
        # Log authentication endpoints
        if "/auth/" in request.url.path:
            logger.info(
                "auth_endpoint_access",
                path=request.url.path,
                method=request.method,
                status_code=response.status_code,
                ip_address=request.client.host if request.client else "unknown"
            )


class TrustedProxyMiddleware(BaseHTTPMiddleware):
    """
    Middleware to handle trusted proxy headers for getting real client IP.
    
    Processes X-Forwarded-For, X-Real-IP headers from trusted proxies.
    Important for accurate rate limiting and security logging.
    """
    
    def __init__(self, app, trusted_proxies: list = None):
        super().__init__(app)
        self.trusted_proxies = trusted_proxies or settings.TRUSTED_PROXIES
        
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Get real client IP from proxy headers
        real_ip = self._get_real_client_ip(request)
        
        # Store real IP in request state for use by other middleware/endpoints
        if real_ip:
            request.state.real_client_ip = real_ip
        
        return await call_next(request)
    
    def _get_real_client_ip(self, request: Request) -> str:
        """Extract real client IP from proxy headers."""
        
        # Check if request is from trusted proxy
        client_ip = request.client.host if request.client else None
        if not self._is_trusted_proxy(client_ip):
            return client_ip
        
        # Try X-Forwarded-For header (most common)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # X-Forwarded-For can contain multiple IPs: "client, proxy1, proxy2"
            ips = [ip.strip() for ip in forwarded_for.split(",")]
            return ips[0]  # First IP is the original client
        
        # Try X-Real-IP header (Nginx)
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        
        # Try Cloudflare header
        cf_connecting_ip = request.headers.get("CF-Connecting-IP")
        if cf_connecting_ip:
            return cf_connecting_ip.strip()
        
        # Fallback to direct client IP
        return client_ip
    
    def _is_trusted_proxy(self, ip: str) -> bool:
        """Check if IP address is from a trusted proxy."""
        if not ip:
            return False
        
        # Simple implementation - in production, use ipaddress module for CIDR matching
        return ip in self.trusted_proxies or any(
            proxy in ip for proxy in self.trusted_proxies if "/" not in proxy
        )