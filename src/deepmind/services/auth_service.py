"""
Authentication Service — JWT generation, validation, password verification, token refresh.
Enterprise-grade security with proper expiration, refresh tokens, and secure secret handling.
"""
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import structlog

from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from deepmind.config import get_config
from deepmind.models.user import User
from deepmind.services.database import get_async_session

log = structlog.get_logger()

# JWT Configuration
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7


class AuthService:
    """Enterprise authentication service."""

    def __init__(self):
        self.cfg = get_config()
        self.secret_key = self.cfg.app.secret_key
        if not self.secret_key or len(self.secret_key) < 32:
            raise ValueError(
                "APP_SECRET_KEY must be set and at least 32 characters. "
                "Generate with: python -c 'import secrets; print(secrets.token_urlsafe(64))'"
            )

    def create_access_token(self, user_id: str, username: str, roles: list[str]) -> str:
        """Create JWT access token (short-lived)."""
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode = {
            "sub": user_id,
            "username": username,
            "roles": roles,
            "type": "access",
            "exp": expire,
            "iat": datetime.utcnow(),
            "jti": str(uuid.uuid4()),
        }
        return jwt.encode(to_encode, self.secret_key, algorithm=JWT_ALGORITHM)

    def create_refresh_token(self, user_id: str) -> str:
        """Create JWT refresh token (long-lived)."""
        expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode = {
            "sub": user_id,
            "type": "refresh",
            "exp": expire,
            "iat": datetime.utcnow(),
            "jti": str(uuid.uuid4()),
        }
        return jwt.encode(to_encode, self.secret_key, algorithm=JWT_ALGORITHM)

    def verify_token(self, token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
        """
        Verify and decode JWT token.

        Args:
            token: JWT token string
            token_type: Expected token type ('access' or 'refresh')

        Returns:
            Decoded payload if valid, None otherwise
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[JWT_ALGORITHM])

            # Verify token type
            if payload.get("type") != token_type:
                log.warning("token_type_mismatch", expected=token_type, actual=payload.get("type"))
                return None

            # Verify expiration
            exp = payload.get("exp")
            if exp and datetime.fromtimestamp(exp) < datetime.utcnow():
                log.info("token_expired", user_id=payload.get("sub"))
                return None

            return payload

        except JWTError as e:
            log.warning("jwt_verification_failed", error=str(e))
            return None

    async def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """
        Authenticate user with username and password.

        Args:
            username: Username or email
            password: Plain text password

        Returns:
            User object if authentication succeeds, None otherwise
        """
        async with get_async_session() as session:
            # Try username first, then email
            stmt = select(User).where(
                (User.username == username) | (User.email == username)
            )
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

            if not user:
                log.info("authentication_failed", reason="user_not_found", username=username)
                return None

            if not user.is_active:
                log.info("authentication_failed", reason="user_inactive", user_id=user.id)
                return None

            if not user.verify_password(password):
                log.info("authentication_failed", reason="invalid_password", user_id=user.id)
                return None

            # Update last login
            user.last_login = datetime.utcnow()
            await session.commit()

            log.info("authentication_success", user_id=user.id, username=user.username)
            return user

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Retrieve user by ID."""
        async with get_async_session() as session:
            stmt = select(User).where(User.id == user_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def create_user(
        self,
        username: str,
        email: str,
        password: str,
        full_name: Optional[str] = None,
        is_superuser: bool = False,
    ) -> User:
        """
        Create new user.

        Args:
            username: Unique username
            email: Unique email
            password: Plain text password (will be hashed)
            full_name: Optional full name
            is_superuser: Whether user is superuser

        Returns:
            Created User object

        Raises:
            ValueError: If username or email already exists
        """
        async with get_async_session() as session:
            # Check if username or email exists
            stmt = select(User).where((User.username == username) | (User.email == email))
            result = await session.execute(stmt)
            if result.scalar_one_or_none():
                raise ValueError("Username or email already exists")

            user = User(
                id=str(uuid.uuid4()),
                username=username,
                email=email,
                full_name=full_name,
                is_superuser=is_superuser,
            )
            user.set_password(password)

            session.add(user)
            await session.commit()
            await session.refresh(user)

            log.info("user_created", user_id=user.id, username=user.username)
            return user

    def create_token_pair(self, user: User) -> Dict[str, str]:
        """
        Create access and refresh token pair for user.

        Args:
            user: User object

        Returns:
            Dict with 'access_token' and 'refresh_token'
        """
        roles = [role.name for role in user.roles]
        return {
            "access_token": self.create_access_token(user.id, user.username, roles),
            "refresh_token": self.create_refresh_token(user.id),
        }


# Singleton
_auth_service: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    """Get singleton AuthService instance."""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
