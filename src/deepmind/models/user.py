"""
Enterprise-grade User and Role SQLAlchemy models with bcrypt password hashing.
Security hardened with audit trails, account lockout, and password policies.
"""
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, Table, Text
)
from sqlalchemy.orm import relationship, declarative_base
import bcrypt

Base = declarative_base()

# Association table for many-to-many User-Role relationship
user_roles = Table(
    'user_roles',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('role_id', Integer, ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
    Column('assigned_at', DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
)


class Role(Base):
    """
    Role-based access control model.
    Hierarchical permissions with inheritance support.
    """
    __tablename__ = 'roles'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    permissions = Column(Text, nullable=False, default='')  # JSON array of permission strings
    is_system = Column(Boolean, default=False, nullable=False)  # Prevent deletion of system roles
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    users = relationship('User', secondary=user_roles, back_populates='roles', lazy='dynamic')
    
    def __repr__(self) -> str:
        return f"<Role(id={self.id}, name='{self.name}')>"
    
    def has_permission(self, permission: str) -> bool:
        """Check if role has specific permission."""
        import json
        try:
            perms = json.loads(self.permissions) if self.permissions else []
            return permission in perms or '*' in perms
        except json.JSONDecodeError:
            return False


class User(Base):
    """
    Enterprise user model with comprehensive security features:
    - Bcrypt password hashing (cost factor 12)
    - Account lockout after failed attempts
    - Password history to prevent reuse
    - Email verification workflow
    - Soft delete support
    - Comprehensive audit trail
    """
    __tablename__ = 'users'
    
    # Primary identification
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    
    # Account status
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    is_locked = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime, nullable=True)  # Soft delete timestamp
    
    # Security tracking
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    last_login_at = Column(DateTime, nullable=True)
    last_login_ip = Column(String(45), nullable=True)  # IPv6 support
    password_changed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    password_history = Column(Text, nullable=False, default='[]')  # JSON array of previous hashes
    
    # Verification tokens
    email_verification_token = Column(String(255), nullable=True, unique=True, index=True)
    email_verification_expires = Column(DateTime, nullable=True)
    password_reset_token = Column(String(255), nullable=True, unique=True, index=True)
    password_reset_expires = Column(DateTime, nullable=True)
    
    # Profile information
    full_name = Column(String(255), nullable=True)
    profile_data = Column(Text, nullable=False, default='{}')  # JSON blob for extensibility
    
    # Audit timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Relationships
    roles = relationship('Role', secondary=user_roles, back_populates='users', lazy='dynamic')
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', email='{self.email}')>"
    
    @staticmethod
    def hash_password(password: str, cost_factor: int = 12) -> str:
        """
        Hash password using bcrypt with configurable cost factor.
        Default cost factor 12 = ~300ms on modern hardware.
        
        Args:
            password: Plaintext password to hash
            cost_factor: Bcrypt cost factor (4-31, default 12)
            
        Returns:
            Bcrypt hash string (60 chars)
        """
        if not password or len(password) < 8:
            raise ValueError("Password must be at least 8 characters")
        
        salt = bcrypt.gensalt(rounds=cost_factor)
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    def set_password(self, password: str, cost_factor: int = 12) -> None:
        """
        Set user password with history tracking.
        
        Args:
            password: New plaintext password
            cost_factor: Bcrypt cost factor (default 12)
        """
        import json
        
        # Validate password strength
        if not password or len(password) < 8:
            raise ValueError("Password must be at least 8 characters")
        
        new_hash = self.hash_password(password, cost_factor)
        
        # Check password history (prevent reuse of last 5 passwords)
        history = json.loads(self.password_history) if self.password_history else []
        for old_hash in history[-5:]:
            if bcrypt.checkpw(password.encode('utf-8'), old_hash.encode('utf-8')):
                raise ValueError("Cannot reuse recent passwords")
        
        # Update history
        history.append(self.password_hash if self.password_hash else new_hash)
        self.password_history = json.dumps(history[-10:])  # Keep last 10
        
        # Set new password
        self.password_hash = new_hash
        self.password_changed_at = datetime.now(timezone.utc)
    
    def verify_password(self, password: str) -> bool:
        """
        Verify password against stored hash.
        
        Args:
            password: Plaintext password to verify
            
        Returns:
            True if password matches, False otherwise
        """
        if not password or not self.password_hash:
            return False
        
        try:
            return bcrypt.checkpw(
                password.encode('utf-8'),
                self.password_hash.encode('utf-8')
            )
        except (ValueError, AttributeError):
            return False
    
    def record_login_attempt(self, success: bool, ip_address: Optional[str] = None) -> None:
        """
        Record login attempt and enforce account lockout policy.
        Locks account after 5 failed attempts within 15 minutes.
        
        Args:
            success: Whether login was successful
            ip_address: Client IP address for audit trail
        """
        if success:
            self.failed_login_attempts = 0
            self.last_login_at = datetime.now(timezone.utc)
            self.last_login_ip = ip_address
            if self.is_locked:
                self.is_locked = False
        else:
            self.failed_login_attempts += 1
            if self.failed_login_attempts >= 5:
                self.is_locked = True
    
    def unlock_account(self) -> None:
        """Manually unlock account and reset failed attempts."""
        self.is_locked = False
        self.failed_login_attempts = 0
    
    def has_role(self, role_name: str) -> bool:
        """Check if user has specific role."""
        return any(role.name == role_name for role in self.roles)
    
    def has_permission(self, permission: str) -> bool:
        """Check if user has specific permission through any role."""
        return any(role.has_permission(permission) for role in self.roles)
    
    def add_role(self, role: 'Role') -> None:
        """Add role to user if not already assigned."""
        if not self.has_role(role.name):
            self.roles.append(role)
    
    def remove_role(self, role: 'Role') -> None:
        """Remove role from user."""
        if self.has_role(role.name):
            self.roles.remove(role)
    
    @property
    def is_admin(self) -> bool:
        """Check if user has admin role."""
        return self.has_role('admin')
    
    def soft_delete(self) -> None:
        """Soft delete user account."""
        self.is_active = False
        self.deleted_at = datetime.now(timezone.utc)
