"""
Rate limiting implementation for API endpoints
"""

import asyncio
import json
import time
from functools import wraps
from typing import Optional, Callable, Any
import redis.asyncio as redis
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)

class RateLimiter:
    """Redis-based rate limiter"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis = redis.from_url(redis_url, decode_responses=True)
        
    async def is_rate_limited(
        self, 
        key: str, 
        limit: int, 
        window_seconds: int
    ) -> tuple[bool, int]:
        """
        Check if a key is rate limited using sliding window
        
        Returns:
            (is_limited: bool, remaining_requests: int)
        """
        try:
            now = time.time()
            window_start = now - window_seconds
            
            # Use Redis pipeline for atomic operations
            async with self.redis.pipeline() as pipe:
                # Remove expired entries
                await pipe.zremrangebyscore(key, 0, window_start)
                # Count current requests
                await pipe.zcard(key)
                # Add current request
                await pipe.zadd(key, {str(now): now})
                # Set expiration
                await pipe.expire(key, window_seconds)
                
                results = await pipe.execute()
                
            current_requests = results[1]  # zcard result
            remaining = max(0, limit - current_requests - 1)  # -1 for current request
            
            is_limited = current_requests >= limit
            
            return is_limited, remaining
            
        except Exception as e:
            logger.error(f"Rate limiting check failed: {e}")
            # Fail open - don't block requests if Redis is down
            return False, limit
    
    async def close(self):
        """Close Redis connection"""
        await self.redis.close()

# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None

def get_rate_limiter() -> RateLimiter:
    """Get or create rate limiter instance"""
    global _rate_limiter
    if _rate_limiter is None:
        try:
            from app.core.config import settings
            redis_url = settings.redis_url
            _rate_limiter = RateLimiter(redis_url)
        except Exception as e:
            logger.warning(f"Could not initialize rate limiter: {e}")
            # Create with default URL as fallback
            _rate_limiter = RateLimiter()
    return _rate_limiter

def rate_limit(
    requests: int = 100, 
    window_seconds: int = 3600,  # 1 hour
    key_func: Optional[Callable] = None
):
    """
    Rate limiting decorator for FastAPI endpoints
    
    Args:
        requests: Maximum number of requests allowed
        window_seconds: Time window in seconds
        key_func: Function to generate rate limit key from request
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request and user from FastAPI dependencies
            request = None
            current_user = None
            
            for arg in args:
                if hasattr(arg, 'method') and hasattr(arg, 'url'):  # Request object
                    request = arg
                elif hasattr(arg, 'id') and hasattr(arg, 'role'):  # User object
                    current_user = arg
            
            # Also check kwargs for these objects
            if not request:
                request = kwargs.get('request')
            if not current_user:
                current_user = kwargs.get('current_user')
            
            # Generate rate limit key
            if key_func:
                rate_key = key_func(request, current_user)
            else:
                # Default key generation
                if current_user:
                    rate_key = f"rate_limit:user:{current_user.id}:{func.__name__}"
                elif request:
                    client_ip = request.client.host if request.client else "unknown"
                    rate_key = f"rate_limit:ip:{client_ip}:{func.__name__}"
                else:
                    rate_key = f"rate_limit:global:{func.__name__}"
            
            # Check rate limit
            limiter = get_rate_limiter()
            is_limited, remaining = await limiter.is_rate_limited(
                rate_key, requests, window_seconds
            )
            
            if is_limited:
                logger.warning(f"Rate limit exceeded for {rate_key}")
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "error": "Rate limit exceeded",
                        "limit": requests,
                        "window_seconds": window_seconds,
                        "remaining": remaining,
                        "retry_after": window_seconds
                    }
                )
            
            # Add rate limit headers to response (will be handled by middleware)
            response = await func(*args, **kwargs)
            
            # Try to add headers if response supports it
            if hasattr(response, 'headers'):
                response.headers["X-RateLimit-Limit"] = str(requests)
                response.headers["X-RateLimit-Remaining"] = str(remaining)
                response.headers["X-RateLimit-Window"] = str(window_seconds)
                
            return response
            
        return wrapper
    return decorator

# Predefined rate limiters for common use cases
def professor_rate_limit(requests: int = 60, window_seconds: int = 3600):
    """Rate limiter specifically for professor endpoints"""
    def key_func(request, current_user):
        if current_user:
            return f"professor_api:user:{current_user.id}"
        elif request:
            client_ip = request.client.host if request.client else "unknown"
            return f"professor_api:ip:{client_ip}"
        return "professor_api:anonymous"
    
    return rate_limit(requests, window_seconds, key_func)

def admin_rate_limit(requests: int = 200, window_seconds: int = 3600):
    """Rate limiter specifically for admin endpoints"""
    def key_func(request, current_user):
        if current_user:
            return f"admin_api:user:{current_user.id}"
        elif request:
            client_ip = request.client.host if request.client else "unknown"
            return f"admin_api:ip:{client_ip}"
        return "admin_api:anonymous"
    
    return rate_limit(requests, window_seconds, key_func)

def student_rate_limit(requests: int = 100, window_seconds: int = 3600):
    """Rate limiter specifically for student endpoints"""
    def key_func(request, current_user):
        if current_user:
            return f"student_api:user:{current_user.id}"
        elif request:
            client_ip = request.client.host if request.client else "unknown"
            return f"student_api:ip:{client_ip}"
        return "student_api:anonymous"
    
    return rate_limit(requests, window_seconds, key_func)