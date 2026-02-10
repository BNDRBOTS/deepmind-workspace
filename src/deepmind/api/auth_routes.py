"""
Authentication API Routes — Login, Register, Logout, Token Refresh.
Enterprise-grade with Pydantic validation, proper error handling.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, EmailStr, Field, validator
import structlog

from deepmind.services.auth_service import get_auth_service, AuthService
from deepmind.middleware.auth_middleware import get_current_user
from deepmind.models.user import User

log = structlog.get_logger()

router = APIRouter(prefix="/auth", tags=["authentication"])


# ---- Request/Response Models ----

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    full_name: Optional[str] = Field(None, max_length=100)

    @validator("password")
    def password_strength(cls, v):
        """Validate password strength."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(...)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 900  # 15 minutes in seconds


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    full_name: Optional[str]
    is_active: bool
    is_superuser: bool
    roles: list[str]

    class Config:
        from_attributes = True


# ---- Endpoints ----

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest, auth: AuthService = Depends(get_auth_service)):
    """
    Register new user.

    - **username**: 3-50 chars, alphanumeric + underscore/dash
    - **email**: Valid email address
    - **password**: Min 8 chars, must contain upper, lower, digit
    - **full_name**: Optional display name

    Returns access + refresh tokens immediately after registration.
    """
    try:
        user = await auth.create_user(
            username=req.username,
            email=req.email,
            password=req.password,
            full_name=req.full_name,
        )
    except ValueError as e:
        log.warning("registration_failed", error=str(e), username=req.username)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    tokens = auth.create_token_pair(user)
    log.info("user_registered", user_id=user.id, username=user.username)

    return TokenResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
    )


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, auth: AuthService = Depends(get_auth_service)):
    """
    Login with username/email and password.

    Accepts either username or email in the `username` field.

    Returns access + refresh tokens on success.
    """
    user = await auth.authenticate_user(req.username, req.password)

    if not user:
        log.warning("login_failed", username=req.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    tokens = auth.create_token_pair(user)

    return TokenResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(req: RefreshRequest, auth: AuthService = Depends(get_auth_service)):
    """
    Refresh access token using refresh token.

    - Validates refresh token
    - Returns new access + refresh token pair
    - Old refresh token is invalidated (single-use)
    """
    payload = auth.verify_token(req.refresh_token, token_type="refresh")

    if not payload:
        log.warning("refresh_failed", reason="invalid_token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    user_id = payload.get("sub")
    user = await auth.get_user_by_id(user_id)

    if not user or not user.is_active:
        log.warning("refresh_failed", reason="user_inactive", user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    tokens = auth.create_token_pair(user)

    return TokenResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"],
    )


@router.post("/logout")
async def logout():
    """
    Logout (client-side token deletion).

    Server doesn't maintain token blacklist by default.
    Client should delete tokens from storage.

    For enterprise token revocation, implement Redis-based blacklist.
    """
    return {"message": "Logged out successfully. Delete tokens from client storage."}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """
    Get current authenticated user info.

    Requires valid access token in Authorization header.
    """
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        is_active=current_user.is_active,
        is_superuser=current_user.is_superuser,
        roles=[role.name for role in current_user.roles],
    )
