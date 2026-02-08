"""Database initialization and session management."""
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine
)
from sqlalchemy import text

from deepmind.models.conversation import Base
from deepmind.config import get_config


_engine = None
_session_factory = None


async def init_database():
    """Initialize the database engine and create tables."""
    global _engine, _session_factory
    
    cfg = get_config()
    db_path = cfg.database.sqlite_path
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    db_url = f"sqlite+aiosqlite:///{db_path}"
    _engine = create_async_engine(
        db_url,
        echo=cfg.app.env == "development",
        pool_pre_ping=True,
    )
    
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if cfg.database.wal_mode:
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text(f"PRAGMA busy_timeout={cfg.database.busy_timeout_ms}"))
            await conn.execute(text("PRAGMA synchronous=NORMAL"))
            await conn.execute(text("PRAGMA cache_size=-64000"))
    
    _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session."""
    if _session_factory is None:
        await init_database()
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def close_database():
    """Gracefully close the database engine."""
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
