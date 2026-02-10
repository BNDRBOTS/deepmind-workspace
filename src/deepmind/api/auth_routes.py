"""
Authentication API Routes — Login, Register, Token Refresh, Logout.
Enterprise-grade: Pydantic validation, secure token handling, proper HTTP status codes.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, status, Depends, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field, field_validator
import structlog

from deepmind.services.auth_service import get_auth_service, AuthService

log = structlog.get_logger()

router = APIRouter(prefix="/auth", tags=["authentication"])
security = HTTPBearer()


# ---- Request/Response Models ----

class RegisterRequest(BaseModel):
    """User registration request."""
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    
    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Enforce strong password: 8+ chars, 1 upper, 1 lower, 1 digit."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class RegisterResponse(BaseModel):
    """User registration response."""
    user_id: str
    username: str
    email: str
    message: str = "Registration successful. Please verify your email."


class LoginRequest(BaseModel):
    """User login request."""
    username: str
    password: str


class TokenResponse(BaseModel):
    """JWT token response."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    """Token refresh request."""
    refresh_token: str


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str


# ---- Endpoints ----

@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    req: RegisterRequest,
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Register new user account.
    
    Password requirements:
    - Minimum 8 characters
    - At least 1 uppercase letter
    - At least 1 lowercase letter
    - At least 1 digit
    
    Username requirements:
    - 3-50 characters
    - Alphanumeric, underscores, hyphens only
    """
    user = await auth_service.register_user(
        username=req.username,
        email=req.email,
        password=req.password,
        assign_default_role=True
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already exists"
        )
    
    log.info("user_registered_via_api", user_id=user.id, username=user.username)
    
    return RegisterResponse(
        user_id=user.id,
        username=user.username,
        email=user.email
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Login user and return JWT tokens.
    
    Returns:
    - access_token: Short-lived token (15 minutes) for API requests
    - refresh_token: Long-lived token (7 days) for refreshing access token
    
    Security:
    - Account locked after 5 failed attempts
    - Tokens signed with HS256
    - Bcrypt password verification
    """
    tokens = await auth_service.login(req.username, req.password)
    
    if not tokens:
        # Generic error message to prevent username enumeration
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials or account locked",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Set httpOnly cookie for refresh token (additional security layer)
    response.set_cookie(
        key="refresh_token",
        value=tokens["refresh_token"],
        httponly=True,
        secure=True,  # HTTPS only in production
        samesite="strict",
        max_age=7 * 24 * 60 * 60,  # 7 days
    )
    
    log.info("user_logged_in_via_api", username=req.username)
    
    return TokenResponse(**tokens)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    req: RefreshRequest,
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Refresh access token using valid refresh token.
    
    Returns new access token + new refresh token.
    Old refresh token is invalidated (via jti rotation).
    """
    tokens = await auth_service.refresh_access_token(req.refresh_token)
    
    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    log.info("token_refreshed_via_api")
    
    return TokenResponse(**tokens)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    response: Response,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Logout user.
    
    Currently:
    - Clears refresh token cookie
    - Client should discard access token
    
    Future enhancement:
    - Token revocation list (Redis)
    """
    # Clear refresh token cookie
    response.delete_cookie(key="refresh_token")
    
    log.info("user_logged_out_via_api")
    
    return MessageResponse(message="Logged out successfully")


@router.get("/me")
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    auth_service: AuthService = Depends(get_auth_service)
):
    """
    Get current authenticated user profile.
    
    Requires valid access token in Authorization header:
    Authorization: Bearer <access_token>
    """
    token = credentials.credentials
    payload = auth_service.validate_access_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return {
        "user_id": payload.get("sub"),
        "username": payload.get("username"),
        "roles": payload.get("roles", []),
    }
