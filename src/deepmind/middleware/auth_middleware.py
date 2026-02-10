"""
Authentication Middleware — FastAPI dependency for JWT validation.
Enterprise-grade: Token validation, role/permission checks, dependency injection.
"""
from typing import Optional, List
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from deepmind.models.user import User
from deepmind.services.auth_service import AuthService, get_auth_service
from deepmind.services.database import get_session

log = structlog.get_logger()

security = HTTPBearer()


# ---- Core Authentication Dependency ----

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: AsyncSession = Depends(get_session),
    auth_service: AuthService = Depends(get_auth_service)
) -> User:
    """
    Get current authenticated user from JWT token.
    
    Usage in route:
        @router.get("/protected")
        async def protected_route(user: User = Depends(get_current_user)):
            return {"user_id": user.id}
    
    Raises:
        HTTPException 401 if token invalid/expired
        HTTPException 403 if user inactive/locked
    """
    token = credentials.credentials
    
    # Validate token
    payload = auth_service.validate_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Fetch user from database
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check account status
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )
    
    if user.is_locked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is locked"
        )
    
    # Load roles for permission checks
    await session.refresh(user, ["roles"])
    
    return user


# ---- Optional Authentication (for public routes with optional user context) ----

async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
    session: AsyncSession = Depends(get_session),
    auth_service: AuthService = Depends(get_auth_service)
) -> Optional[User]:
    """
    Get current user if token provided, otherwise None.
    
    Usage for routes that behave differently based on auth state:
        @router.get("/optional-auth")
        async def optional_route(user: Optional[User] = Depends(get_current_user_optional)):
            if user:
                return {"message": f"Hello {user.username}"}
            return {"message": "Hello guest"}
    """
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials, session, auth_service)
    except HTTPException:
        return None


# ---- Role-Based Access Control ----

class RequireRole:
    """
    Dependency for requiring specific role(s).
    
    Usage:
        @router.delete("/admin/users/{user_id}")
        async def delete_user(
            user_id: str,
            current_user: User = Depends(RequireRole(["admin"]))
        ):
            # Only admins can access
            pass
    """
    def __init__(self, roles: List[str]):
        self.roles = roles
    
    async def __call__(self, user: User = Depends(get_current_user)) -> User:
        if not any(user.has_role(role) for role in self.roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {', '.join(self.roles)}"
            )
        return user


class RequirePermission:
    """
    Dependency for requiring specific permission(s).
    
    Usage:
        @router.post("/execute-code")
        async def execute(
            code: str,
            current_user: User = Depends(RequirePermission("execute_code"))
        ):
            # Only users with execute_code permission
            pass
    """
    def __init__(self, permission: str):
        self.permission = permission
    
    async def __call__(self, user: User = Depends(get_current_user)) -> User:
        if not user.has_permission(self.permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires permission: {self.permission}"
            )
        return user


# ---- Convenience Dependencies ----

RequireAdmin = RequireRole(["admin"])
RequireCodeExecution = RequirePermission("execute_code")
RequireImageGeneration = RequirePermission("generate_images")
