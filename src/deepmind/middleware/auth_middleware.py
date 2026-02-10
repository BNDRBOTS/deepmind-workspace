"""
Authentication Middleware — FastAPI dependency for JWT validation on protected routes.
Enterprise-grade with proper error handling, role-based access control.
"""
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import structlog

from deepmind.services.auth_service import get_auth_service, AuthService
from deepmind.models.user import User

log = structlog.get_logger()

# HTTP Bearer token extractor
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    auth: AuthService = Depends(get_auth_service),
) -> User:
    """
    FastAPI dependency to get current authenticated user from JWT token.

    Usage:
        @router.get("/protected")
        async def protected_route(user: User = Depends(get_current_user)):
            return {"user_id": user.id}

    Raises:
        HTTPException 401: If token is missing, invalid, or expired
    """
    if not credentials:
        log.warning("auth_failed", reason="no_credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    payload = auth.verify_token(token, token_type="access")

    if not payload:
        log.warning("auth_failed", reason="invalid_token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    user = await auth.get_user_by_id(user_id)

    if not user:
        log.warning("auth_failed", reason="user_not_found", user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        log.warning("auth_failed", reason="user_inactive", user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Dependency to require active user (alias for get_current_user for clarity).
    """
    return current_user


async def require_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Dependency to require superuser privileges.

    Usage:
        @router.delete("/admin/users/{user_id}")
        async def delete_user(user_id: str, admin: User = Depends(require_superuser)):
            ...

    Raises:
        HTTPException 403: If user is not superuser
    """
    if not current_user.is_superuser:
        log.warning(
            "authorization_failed",
            reason="not_superuser",
            user_id=current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser privileges required",
        )
    return current_user


def require_role(role_name: str):
    """
    Dependency factory to require specific role.

    Usage:
        @router.post("/admin/backup")
        async def backup_database(user: User = Depends(require_role("admin"))):
            ...

    Args:
        role_name: Required role name

    Returns:
        FastAPI dependency function
    """

    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if not current_user.has_role(role_name):
            log.warning(
                "authorization_failed",
                reason="missing_role",
                required_role=role_name,
                user_id=current_user.id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role_name}' required",
            )
        return current_user

    return role_checker


def require_permission(permission: str):
    """
    Dependency factory to require specific permission.

    Usage:
        @router.post("/api/execute-code")
        async def execute_code(user: User = Depends(require_permission("code:execute"))):
            ...

    Args:
        permission: Required permission string

    Returns:
        FastAPI dependency function
    """

    async def permission_checker(current_user: User = Depends(get_current_user)) -> User:
        if not current_user.has_permission(permission) and not current_user.is_superuser:
            log.warning(
                "authorization_failed",
                reason="missing_permission",
                required_permission=permission,
                user_id=current_user.id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' required",
            )
        return current_user

    return permission_checker


# Optional authentication (returns None if no token)
async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    auth: AuthService = Depends(get_auth_service),
) -> Optional[User]:
    """
    Optional authentication - returns User if valid token present, None otherwise.

    Usage:
        @router.get("/public-or-private")
        async def mixed_route(user: Optional[User] = Depends(get_current_user_optional)):
            if user:
                return {"message": f"Hello {user.username}"}
            return {"message": "Hello anonymous"}
    """
    if not credentials:
        return None

    token = credentials.credentials
    payload = auth.verify_token(token, token_type="access")

    if not payload:
        return None

    user_id = payload.get("sub")
    user = await auth.get_user_by_id(user_id)

    return user if user and user.is_active else None
