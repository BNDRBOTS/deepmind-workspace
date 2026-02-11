"""
Authentication Service — JWT generation, validation, password verification, token refresh.
Enterprise-grade security with proper expiration, refresh tokens, and secure secret handling.
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import structlog

from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from deepmind.config import get_config
from deepmind.models.user import User, Role, user_roles
from deepmind.services.database import get_session
from deepmind.services.secrets_manager import get_secrets_manager

log = structlog.get_logger()

# JWT Configuration — defaults, overridden by config/app.yaml auth section
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7


class AuthService:
    """Enterprise authentication service with JWT token management."""

    def __init__(self):
        self.cfg = get_config()
        self._sm = get_secrets_manager()
        self.secret_key = self._resolve_secret_key()
        self.refresh_secret_key = self._resolve_refresh_secret_key()

        # Load auth config if available
        auth_cfg = getattr(self.cfg, "auth", None)
        if auth_cfg:
            self.access_expire_minutes = getattr(auth_cfg, "jwt_access_expiry_minutes", ACCESS_TOKEN_EXPIRE_MINUTES)
            self.refresh_expire_days = getattr(auth_cfg, "jwt_refresh_expiry_days", REFRESH_TOKEN_EXPIRE_DAYS)
            self.bcrypt_rounds = getattr(auth_cfg, "bcrypt_rounds", 12)
        else:
            self.access_expire_minutes = ACCESS_TOKEN_EXPIRE_MINUTES
            self.refresh_expire_days = REFRESH_TOKEN_EXPIRE_DAYS
            self.bcrypt_rounds = 12

    def _resolve_secret_key(self) -> str:
        """Resolve JWT secret key via secrets manager."""
        key = self._sm.get("JWT_SECRET_KEY") or self._sm.get("APP_SECRET_KEY")
        if not key or len(key) < 32:
            raise ValueError(
                "JWT_SECRET_KEY (or APP_SECRET_KEY) must be set and at least 32 characters. "
                "Generate with: python scripts/generate_secrets.py"
            )
        return key

    def _resolve_refresh_secret_key(self) -> str:
        """Resolve separate refresh token secret key via secrets manager."""
        key = self._sm.get("JWT_REFRESH_SECRET_KEY")
        if key and len(key) >= 32:
            return key
        # Fall back to primary secret with suffix for separation
        return self.secret_key + "_refresh"

    def create_access_token(self, user_id: str, username: str, roles: list[str]) -> str:
        """Create JWT access token (short-lived, 15 min default)."""
        expire = datetime.now(timezone.utc) + timedelta(minutes=self.access_expire_minutes)
        to_encode = {
            "sub": str(user_id),
            "username": username,
            "roles": roles,
            "type": "access",
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "jti": str(uuid.uuid4()),
        }
        return jwt.encode(to_encode, self.secret_key, algorithm=JWT_ALGORITHM)

    def create_refresh_token(self, user_id: str) -> str:
        """Create JWT refresh token (long-lived, 7 day default)."""
        expire = datetime.now(timezone.utc) + timedelta(days=self.refresh_expire_days)
        to_encode = {
            "sub": str(user_id),
            "type": "refresh",
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "jti": str(uuid.uuid4()),
        }
        return jwt.encode(to_encode, self.refresh_secret_key, algorithm=JWT_ALGORITHM)

    def verify_token(self, token: str, token_type: str = "access") -> Optional[Dict[str, Any]]:
        """
        Verify and decode JWT token.

        Args:
            token: JWT token string
            token_type: Expected token type ('access' or 'refresh')

        Returns:
            Decoded payload if valid, None otherwise
        """
        secret = self.refresh_secret_key if token_type == "refresh" else self.secret_key
        try:
            payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])

            # Verify token type matches expected
            if payload.get("type") != token_type:
                log.warning(
                    "token_type_mismatch",
                    expected=token_type,
                    actual=payload.get("type"),
                )
                return None

            return payload

        except JWTError as e:
            log.warning("jwt_verification_failed", error=str(e))
            return None

    async def authenticate_user(
        self, username: str, password: str, ip_address: Optional[str] = None
    ) -> Optional[User]:
        """
        Authenticate user with username/email and password.
        Records login attempts and enforces account lockout.

        Args:
            username: Username or email
            password: Plain text password
            ip_address: Client IP for audit trail

        Returns:
            User object if authentication succeeds, None otherwise
        """
        async with get_session() as session:
            stmt = (
                select(User)
                .options(selectinload(User.roles))
                .where((User.username == username) | (User.email == username))
            )
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()

            if not user:
                log.info("auth_failed", reason="user_not_found", username=username)
                return None

            if not user.is_active:
                log.info("auth_failed", reason="user_inactive", user_id=user.id)
                return None

            if user.is_locked:
                log.info("auth_failed", reason="account_locked", user_id=user.id)
                return None

            if not user.verify_password(password):
                user.record_login_attempt(success=False, ip_address=ip_address)
                await session.commit()
                log.info("auth_failed", reason="invalid_password", user_id=user.id)
                return None

            # Successful authentication
            user.record_login_attempt(success=True, ip_address=ip_address)
            await session.commit()

            log.info("auth_success", user_id=user.id, username=user.username)
            return user

    async def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Retrieve user by ID with roles eagerly loaded."""
        async with get_session() as session:
            stmt = (
                select(User)
                .options(selectinload(User.roles))
                .where(User.id == str(user_id))
            )
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
        Create new user with hashed password.

        Args:
            username: Unique username
            email: Unique email
            password: Plain text password (will be bcrypt hashed)
            full_name: Optional full name
            is_superuser: Whether user is superuser

        Returns:
            Created User object

        Raises:
            ValueError: If username or email already exists
        """
        async with get_session() as session:
            # Check uniqueness
            stmt = select(User).where(
                (User.username == username) | (User.email == email)
            )
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
            user.set_password(password, cost_factor=self.bcrypt_rounds)

            # Assign default 'user' role if it exists
            role_stmt = select(Role).where(Role.name == "user")
            role_result = await session.execute(role_stmt)
            default_role = role_result.scalar_one_or_none()
            if default_role:
                user.roles.append(default_role)

            session.add(user)
            await session.commit()
            await session.refresh(user)

            log.info("user_created", user_id=user.id, username=user.username)
            return user

    def create_token_pair(self, user: User) -> Dict[str, str]:
        """
        Create access + refresh token pair for user.

        Args:
            user: User object

        Returns:
            Dict with 'access_token' and 'refresh_token'
        """
        roles = [role.name for role in user.roles]
        return {
            "access_token": self.create_access_token(
                str(user.id), user.username, roles
            ),
            "refresh_token": self.create_refresh_token(str(user.id)),
        }


# Singleton
_auth_service: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    """Get singleton AuthService instance."""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
