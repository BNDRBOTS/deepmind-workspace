"""
Rate Limiting Middleware using SlowAPI.

Provides per-user rate limiting for expensive endpoints using Redis
for distributed storage (with in-memory fallback for development).

Features:
- Per-user quota enforcement (extracted from JWT)
- Falls back to IP-based limiting for unauthenticated requests
- Redis backend for production (distributed, persistent)
- In-memory backend for development (simple, no setup required)
- Automatic Retry-After header in 429 responses
- Comprehensive logging of rate limit events
"""
import structlog
from typing import Optional
from fastapi import Request

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from deepmind.config import get_config

log = structlog.get_logger()


def get_rate_limit_key(request: Request) -> str:
    """
    Generate rate limit key from request.
    
    Strategy:
    1. If user is authenticated (JWT), use user ID → "user:{user_id}"
    2. If not authenticated, use IP address → "ip:{ip_address}"
    
    This enables:
    - Per-user quotas for authenticated requests
    - IP-based limiting for unauthenticated requests (e.g., login attempts)
    
    Args:
        request: FastAPI Request object
        
    Returns:
        Rate limit key string
    """
    # Check if user is authenticated via middleware
    # The auth middleware sets request.state.user
    user = getattr(request.state, "user", None)
    
    if user and hasattr(user, "id"):
        # Authenticated user — rate limit by user ID
        key = f"user:{user.id}"
        log.debug("rate_limit_key_user", user_id=user.id, key=key)
        return key
    
    # Not authenticated — rate limit by IP address
    ip = get_remote_address(request)
    key = f"ip:{ip}"
    log.debug("rate_limit_key_ip", ip=ip, key=key)
    return key


# Global limiter instance
_limiter: Optional[Limiter] = None


def get_limiter() -> Limiter:
    """
    Get or create singleton Limiter instance.
    
    Configures SlowAPI with:
    - Redis backend if available (production)
    - In-memory backend as fallback (development)
    - Custom key function for per-user limiting
    - Storage URI from config
    
    Returns:
        Configured Limiter instance
    """
    global _limiter
    
    if _limiter is not None:
        return _limiter
    
    cfg = get_config()
    
    # Determine storage URI
    if hasattr(cfg, 'rate_limits') and cfg.rate_limits.enabled:
        storage_uri = cfg.rate_limits.redis_url if cfg.rate_limits.storage == "redis" else "memory://"
    else:
        # Rate limiting disabled in config, use in-memory
        storage_uri = "memory://"
    
    log.info(
        "rate_limiter_initializing",
        storage=storage_uri.split("://")[0],
        enabled=hasattr(cfg, 'rate_limits') and cfg.rate_limits.enabled,
    )
    
    try:
        _limiter = Limiter(
            key_func=get_rate_limit_key,
            storage_uri=storage_uri,
            # Enable automatic Retry-After header
            headers_enabled=True,
            # Swallow errors if Redis unavailable (fall back to no limiting)
            swallow_errors=True,
        )
        
        log.info(
            "rate_limiter_initialized",
            storage=storage_uri.split("://")[0],
        )
        
    except Exception as e:
        # If Redis connection fails, fall back to in-memory
        log.warning(
            "rate_limiter_fallback_to_memory",
            error=str(e),
            original_storage=storage_uri,
        )
        
        _limiter = Limiter(
            key_func=get_rate_limit_key,
            storage_uri="memory://",
            headers_enabled=True,
            swallow_errors=True,
        )
    
    return _limiter


def create_rate_limit_handler():
    """
    Create custom rate limit exceeded handler.
    
    Returns handler function that:
    - Logs rate limit violations
    - Returns 429 with Retry-After header
    - Includes user-friendly error message
    """
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
        """
        Handle rate limit exceeded exceptions.
        
        Logs the violation and returns 429 response with Retry-After header.
        """
        user = getattr(request.state, "user", None)
        user_id = user.id if user and hasattr(user, "id") else None
        ip = get_remote_address(request)
        
        log.warning(
            "rate_limit_exceeded",
            user_id=user_id,
            ip=ip,
            path=request.url.path,
            limit=exc.detail,
        )
        
        return await _rate_limit_exceeded_handler(request, exc)
    
    return rate_limit_handler
