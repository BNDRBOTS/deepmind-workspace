"""
Alembic Migration: Create users and roles tables
Revision ID: 001
Create Date: 2026-02-10 16:37:00
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone

# revision identifiers
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Create users, roles, and user_roles tables.
    """
    # Create roles table
    op.create_table(
        'roles',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('can_execute_code', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('can_generate_images', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('can_manage_users', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('can_access_all_conversations', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_roles_name'), 'roles', ['name'], unique=True)
    
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('username', sa.String(length=50), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('is_locked', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('failed_login_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_failed_login', sa.DateTime(timezone=True), nullable=True),
        sa.Column('locked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('verification_token', sa.String(length=255), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reset_token', sa.String(length=255), nullable=True),
        sa.Column('reset_token_expires', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
        sa.UniqueConstraint('email')
    )
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    
    # Create user_roles association table
    op.create_table(
        'user_roles',
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('role_id', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'role_id')
    )
    
    # Insert default roles
    op.execute(
        """
        INSERT INTO roles (id, name, description, can_execute_code, can_generate_images, can_manage_users, can_access_all_conversations)
        VALUES 
        ('role_admin', 'admin', 'Administrator with full system access', 1, 1, 1, 1),
        ('role_user', 'user', 'Standard user with conversation and connector access', 1, 1, 0, 0),
        ('role_readonly', 'readonly', 'Read-only access to conversations', 0, 0, 0, 0)
        """
    )


def downgrade() -> None:
    """
    Drop users, roles, and user_roles tables.
    """
    op.drop_table('user_roles')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_table('users')
    op.drop_index(op.f('ix_roles_name'), table_name='roles')
    op.drop_table('roles')
