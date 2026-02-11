"""
Rate Limiting Middleware using SlowAPI.

Provides per-user, per-endpoint rate limiting with Redis backend (falls back to in-memory).
Integrates with JWT authentication to identify users and apply separate quotas.

Features:
- Redis backend for distributed rate limiting across multiple instances
- In-memory fallback for development/testing
- Per-user quotas based on JWT user_id
- Per-endpoint limit configuration
- 429 responses with Retry-After header
- Graceful Redis connection failure handling
"""
import structlog
from typing import Optional
from fastapi import Request
from jose import jwt, JWTError
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from deepmind.config import get_config

log = structlog.get_logger()


def get_user_identifier(request: Request) -> str:
    """
    Extract user identifier for rate limiting.
    
    Priority:
    1. User ID from JWT token (if authenticated)
    2. IP address (for unauthenticated requests)
    
    This ensures:
    - Each authenticated user has separate quota
    - Multiple users behind same IP don't share quota
    - Unauthenticated requests rate limited by IP
    
    Args:
        request: FastAPI Request object
        
    Returns:
        String identifier for rate limiting (user_id or IP)
    """
    # Try to extract user_id from JWT token in Authorization header
    auth_header = request.headers.get("Authorization", "")
    
    if auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "").strip()
        
        try:
            cfg = get_config()
            # Decode JWT without verification (we just need the user_id)
            # Verification happens in auth middleware, this is just for rate limiting
            payload = jwt.decode(
                token,
                cfg.app.secret_key,
                algorithms=[cfg.auth.jwt_algorithm],
                options={"verify_signature": False}  # Already verified by auth middleware
            )
            
            user_id = payload.get("sub")  # 'sub' claim contains user_id
            
            if user_id:
                log.debug(
                    "rate_limit_key_extracted",
                    user_id=user_id,
                    method=request.method,
                    path=request.url.path,
                )
                return f"user:{user_id}"
        
        except (JWTError, KeyError, AttributeError) as e:
            # JWT decode failed, fall back to IP
            log.debug(
                "rate_limit_jwt_decode_failed",
                error=str(e),
                method=request.method,
                path=request.url.path,
            )
    
    # Fallback: use IP address for unauthenticated requests
    ip_address = get_remote_address(request)
    
    log.debug(
        "rate_limit_key_ip",
        ip=ip_address,
        method=request.method,
        path=request.url.path,
    )
    
    return f"ip:{ip_address}"


def create_limiter() -> Limiter:
    """
    Create and configure SlowAPI Limiter with appropriate storage backend.
    
    Storage backends:
    - Redis: Production, distributed across multiple instances
    - Memory: Development, single process only
    
    Returns:
        Configured Limiter instance
    """
    cfg = get_config()
    
    # Check if rate limiting is enabled
    rate_limits_config = getattr(cfg, 'rate_limits', None)
    
    if rate_limits_config is None or not getattr(rate_limits_config, 'enabled', True):
        log.warning("rate_limiting_disabled", reason="not enabled in config")
        # Create limiter with very high default limit (effectively disabled)
        return Limiter(
            key_func=get_user_identifier,
            storage_uri="memory://",
            default_limits=["10000/minute"],
        )
    
    # Get storage configuration
    storage = getattr(rate_limits_config, 'storage', 'memory')
    
    if storage == 'redis':
        # Try to use Redis backend
        redis_url = getattr(rate_limits_config, 'redis_url', '')
        
        if not redis_url:
            log.warning(
                "redis_url_not_configured",
                fallback="memory",
                message="REDIS_URL not set, falling back to in-memory rate limiting"
            )
            storage_uri = "memory://"
        else:
            try:
                # Test Redis connection
                import redis
                client = redis.from_url(redis_url, decode_responses=True)
                client.ping()
                client.close()
                
                storage_uri = redis_url
                log.info(
                    "rate_limiter_redis_connected",
                    redis_url=redis_url.split('@')[-1],  # Hide credentials
                )
            
            except ImportError:
                log.warning(
                    "redis_package_not_installed",
                    fallback="memory",
                    message="Install redis package for distributed rate limiting: pip install 'deepmind[redis]'"
                )
                storage_uri = "memory://"
            
            except Exception as e:
                log.warning(
                    "redis_connection_failed",
                    error=str(e),
                    fallback="memory",
                    message="Failed to connect to Redis, falling back to in-memory rate limiting"
                )
                storage_uri = "memory://"
    else:
        # Use in-memory storage
        storage_uri = "memory://"
        log.info("rate_limiter_memory_backend")
    
    # Get default limits from config
    default_limit = getattr(rate_limits_config, 'default_limit', '100/minute')
    
    limiter = Limiter(
        key_func=get_user_identifier,
        storage_uri=storage_uri,
        default_limits=[default_limit],
        headers_enabled=True,  # Send X-RateLimit-* headers
    )
    
    log.info(
        "rate_limiter_initialized",
        storage=storage_uri.split(':')[0],
        default_limit=default_limit,
    )
    
    return limiter


# Singleton limiter instance
_limiter: Optional[Limiter] = None


def get_limiter() -> Limiter:
    """
    Get singleton rate limiter instance.
    
    Returns:
        Configured Limiter for use in route decorators
    """
    global _limiter
    if _limiter is None:
        _limiter = create_limiter()
    return _limiter


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """
    Custom handler for rate limit exceeded exceptions.
    
    Returns 429 response with Retry-After header indicating when limit resets.
    
    Args:
        request: FastAPI Request
        exc: RateLimitExceeded exception from SlowAPI
        
    Returns:
        JSONResponse with 429 status code
    """
    from fastapi.responses import JSONResponse
    
    # Extract user identifier for logging
    identifier = get_user_identifier(request)
    
    log.warning(
        "rate_limit_exceeded",
        identifier=identifier,
        path=request.url.path,
        method=request.method,
        limit=exc.detail if hasattr(exc, 'detail') else 'unknown',
    )
    
    # Calculate Retry-After header (seconds until limit resets)
    retry_after = getattr(exc, 'retry_after', 60)  # Default 60 seconds
    
    response = JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "message": "Too many requests. Please slow down.",
            "detail": str(exc),
            "retry_after_seconds": retry_after,
        },
        headers={
            "Retry-After": str(retry_after),
        },
    )
    
    return response
