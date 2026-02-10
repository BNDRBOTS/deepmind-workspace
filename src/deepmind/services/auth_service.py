"""
Authentication Service — JWT generation/validation, password hashing, token refresh.
Enterprise-grade: bcrypt (12 rounds), secure token generation, account locking.
"""
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from passlib.context import CryptContext
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from deepmind.config import get_config
from deepmind.models.user import User, Role
from deepmind.services.database import get_session

log = structlog.get_logger()

# Bcrypt context - 12 rounds (OWASP recommendation)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

# Constants from config
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7
MAX_FAILED_ATTEMPTS = 5


class AuthService:
    """Enterprise authentication service."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.cfg = get_config()
        self.secret_key = self.cfg.app.secret_key
    
    # ---- Password Hashing ----
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash password using bcrypt (12 rounds)."""
        return pwd_context.hash(password)
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify password against bcrypt hash."""
        return pwd_context.verify(plain_password, hashed_password)
    
    # ---- JWT Token Generation ----
    
    def create_access_token(self, user_id: str, username: str, roles: list[str]) -> str:
        """
        Create JWT access token (15min expiry).
        
        Claims:
        - sub: user_id
        - username: username
        - roles: list of role names
        - type: access
        - exp: expiration timestamp
        - iat: issued at timestamp
        """
        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        
        payload = {
            "sub": user_id,
            "username": username,
            "roles": roles,
            "type": "access",
            "exp": expires,
            "iat": now,
        }
        
        return jwt.encode(payload, self.secret_key, algorithm=ALGORITHM)
    
    def create_refresh_token(self, user_id: str) -> str:
        """
        Create JWT refresh token (7 day expiry).
        
        Claims:
        - sub: user_id
        - type: refresh
        - exp: expiration timestamp
        - iat: issued at timestamp
        - jti: unique token ID (for revocation support)
        """
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        
        payload = {
            "sub": user_id,
            "type": "refresh",
            "exp": expires,
            "iat": now,
            "jti": secrets.token_urlsafe(32),
        }
        
        return jwt.encode(payload, self.secret_key, algorithm=ALGORITHM)
    
    # ---- Token Validation ----
    
    def decode_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Decode and validate JWT token.
        
        Returns:
            Dict with claims if valid, None if invalid/expired
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[ALGORITHM])
            return payload
        except JWTError as e:
            log.warning("jwt_decode_failed", error=str(e))
            return None
    
    def validate_access_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate access token and return claims."""
        payload = self.decode_token(token)
        if not payload or payload.get("type") != "access":
            return None
        return payload
    
    def validate_refresh_token(self, token: str) -> Optional[str]:
        """Validate refresh token and return user_id."""
        payload = self.decode_token(token)
        if not payload or payload.get("type") != "refresh":
            return None
        return payload.get("sub")
    
    # ---- User Authentication ----
    
    async def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """
        Authenticate user by username/password.
        
        Security features:
        - Account locking after 5 failed attempts
        - Failed attempt tracking
        - Timing-safe password comparison
        
        Returns:
            User object if authenticated, None otherwise
        """
        # Fetch user
        stmt = select(User).where(User.username == username)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            log.info("auth_user_not_found", username=username)
            return None
        
        # Check if account is locked
        if user.is_locked:
            log.warning("auth_account_locked", user_id=user.id, username=username)
            return None
        
        # Verify password
        if not self.verify_password(password, user.password_hash):
            # Increment failed attempts
            user.failed_login_attempts += 1
            user.last_failed_login = datetime.now(timezone.utc)
            
            # Lock account if threshold exceeded
            if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
                user.is_locked = True
                user.locked_at = datetime.now(timezone.utc)
                log.error(
                    "auth_account_auto_locked",
                    user_id=user.id,
                    failed_attempts=user.failed_login_attempts
                )
            
            await self.session.commit()
            log.info("auth_invalid_password", username=username, attempts=user.failed_login_attempts)
            return None
        
        # Check if account is active
        if not user.is_active:
            log.warning("auth_account_inactive", user_id=user.id)
            return None
        
        # Success - reset failed attempts
        user.failed_login_attempts = 0
        user.last_login = datetime.now(timezone.utc)
        await self.session.commit()
        
        log.info("auth_success", user_id=user.id, username=username)
        return user
    
    async def login(self, username: str, password: str) -> Optional[Dict[str, str]]:
        """
        Login user and return tokens.
        
        Returns:
            Dict with access_token, refresh_token, token_type, or None if auth fails
        """
        user = await self.authenticate_user(username, password)
        if not user:
            return None
        
        # Load user roles
        await self.session.refresh(user, ["roles"])
        role_names = [role.name for role in user.roles]
        
        # Generate tokens
        access_token = self.create_access_token(user.id, user.username, role_names)
        refresh_token = self.create_refresh_token(user.id)
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }
    
    async def refresh_access_token(self, refresh_token: str) -> Optional[Dict[str, str]]:
        """
        Refresh access token using valid refresh token.
        
        Returns:
            New token pair or None if refresh token invalid
        """
        user_id = self.validate_refresh_token(refresh_token)
        if not user_id:
            return None
        
        # Fetch user
        stmt = select(User).where(User.id == user_id)
        result = await self.session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user or not user.is_active or user.is_locked:
            return None
        
        # Load roles
        await self.session.refresh(user, ["roles"])
        role_names = [role.name for role in user.roles]
        
        # Generate new tokens
        access_token = self.create_access_token(user.id, user.username, role_names)
        new_refresh_token = self.create_refresh_token(user.id)
        
        return {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
            "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }
    
    # ---- User Registration ----
    
    async def register_user(
        self,
        username: str,
        email: str,
        password: str,
        assign_default_role: bool = True
    ) -> Optional[User]:
        """
        Register new user.
        
        Args:
            username: Unique username
            email: Unique email
            password: Plain password (will be hashed)
            assign_default_role: Assign 'user' role by default
        
        Returns:
            User object if created, None if username/email exists
        """
        # Check if username exists
        stmt = select(User).where(User.username == username)
        result = await self.session.execute(stmt)
        if result.scalar_one_or_none():
            log.warning("register_username_exists", username=username)
            return None
        
        # Check if email exists
        stmt = select(User).where(User.email == email)
        result = await self.session.execute(stmt)
        if result.scalar_one_or_none():
            log.warning("register_email_exists", email=email)
            return None
        
        # Create user
        user = User(
            id=str(uuid.uuid4()),
            username=username,
            email=email,
            password_hash=self.hash_password(password),
            verification_token=secrets.token_urlsafe(32),
        )
        
        # Assign default role
        if assign_default_role:
            stmt = select(Role).where(Role.name == "user")
            result = await self.session.execute(stmt)
            default_role = result.scalar_one_or_none()
            if default_role:
                user.roles.append(default_role)
        
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        
        log.info("user_registered", user_id=user.id, username=username, email=email)
        return user


async def get_auth_service() -> AuthService:
    """Get AuthService instance with database session."""
    async with get_session() as session:
        return AuthService(session)
