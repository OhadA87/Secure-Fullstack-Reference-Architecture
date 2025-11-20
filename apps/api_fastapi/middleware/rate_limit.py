"""
Rate Limiting Middleware

File: apps/api_fastapi/middleware/rate_limit.py

Provides rate limiting decorators and middleware.
"""

from functools import wraps
from typing import Callable
import asyncio
from datetime import datetime, timedelta

from fastapi import HTTPException, Request, status
from redis import asyncio as aioredis


class RateLimiter:
    """Rate limiting utility"""

    def __init__(self, redis_url: str = "redis://localhost:6379/1"):
        self.redis_url = redis_url
        self._redis = None

    async def get_redis(self):
        """Get Redis connection"""
        if not self._redis:
            self._redis = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
        return self._redis

    async def check_rate_limit(
        self,
        key: str,
        calls: int,
        period: int
    ) -> bool:
        """
        Check if request is within rate limit

        Args:
            key: Unique identifier for the rate limit
            calls: Number of calls allowed
            period: Period in seconds

        Returns:
            True if within limit, False if exceeded
        """
        redis = await self.get_redis()

        # Use sliding window counter
        now = datetime.utcnow().timestamp()
        window_start = now - period

        # Remove expired entries
        await redis.zremrangebyscore(key, 0, window_start)

        # Count current requests
        current_count = await redis.zcard(key)

        if current_count >= calls:
            return False

        # Add current request
        await redis.zadd(key, {str(now): now})
        await redis.expire(key, period)

        return True


# Global rate limiter instance
rate_limiter = RateLimiter()


def rate_limit(calls: int, period: int):
    """
    Rate limiting decorator

    Args:
        calls: Number of calls allowed
        period: Period in seconds

    Example:
        @rate_limit(calls=10, period=60)
        async def my_endpoint():
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request from arguments
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break

            if not request:
                for value in kwargs.values():
                    if isinstance(value, Request):
                        request = value
                        break

            if request:
                # Create rate limit key
                client_ip = request.client.host if request.client else "unknown"
                endpoint = request.url.path
                key = f"rate_limit:{endpoint}:{client_ip}"

                # Check rate limit
                allowed = await rate_limiter.check_rate_limit(key, calls, period)
                if not allowed:
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=f"Rate limit exceeded: {calls} requests per {period} seconds"
                    )

            return await func(*args, **kwargs)
        return wrapper
    return decorator