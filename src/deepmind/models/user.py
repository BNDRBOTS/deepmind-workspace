"""
User and Role models for authentication system.
Enterprise-grade: bcrypt password hashing, role-based access control, audit fields.
"""
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Table, Column, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from deepmind.models.conversation import Base


# Association table for many-to-many User-Role relationship
user_roles = Table(
    'user_roles',
    Base.metadata,
    Column('user_id', String, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('role_id', String, ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
)


class Role(Base):
    """
    Role model for RBAC (Role-Based Access Control).
    
    Default roles:
    - admin: Full system access, user management
    - user: Standard user access to conversations, connectors
    - readonly: View-only access
    """
    __tablename__ = 'roles'
    
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Permissions (future expansion)
    can_execute_code: Mapped[bool] = mapped_column(Boolean, default=False)
    can_generate_images: Mapped[bool] = mapped_column(Boolean, default=False)
    can_manage_users: Mapped[bool] = mapped_column(Boolean, default=False)
    can_access_all_conversations: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    
    # Relationships
    users: Mapped[list["User"]] = relationship(
        "User",
        secondary=user_roles,
        back_populates="roles"
    )
    
    def __repr__(self) -> str:
        return f"<Role(id={self.id}, name={self.name})>"


class User(Base):
    """
    User model for authentication.
    
    Security features:
    - Bcrypt password hashing (12 rounds)
    - Account locking after failed attempts
    - Email verification support
    - Session tracking
    """
    __tablename__ = 'users'
    
    id: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    
    # Password stored as bcrypt hash
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Account status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Security tracking
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_failed_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Verification
    verification_token: Mapped[Optional[str]] = mapped_column(String(255))
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Password reset
    reset_token: Mapped[Optional[str]] = mapped_column(String(255))
    reset_token_expires: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Audit fields
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    
    # Relationships
    roles: Mapped[list[Role]] = relationship(
        "Role",
        secondary=user_roles,
        back_populates="users"
    )
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username}, email={self.email})>"
    
    def has_role(self, role_name: str) -> bool:
        """Check if user has specific role."""
        return any(role.name == role_name for role in self.roles)
    
    def has_permission(self, permission: str) -> bool:
        """
        Check if user has specific permission through any of their roles.
        
        Supported permissions:
        - execute_code
        - generate_images
        - manage_users
        - access_all_conversations
        """
        permission_map = {
            'execute_code': 'can_execute_code',
            'generate_images': 'can_generate_images',
            'manage_users': 'can_manage_users',
            'access_all_conversations': 'can_access_all_conversations',
        }
        
        attr = permission_map.get(permission)
        if not attr:
            return False
        
        return any(getattr(role, attr, False) for role in self.roles)
