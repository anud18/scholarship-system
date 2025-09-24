"""
Database base configuration and utilities.
Sets up SQLAlchemy async engine and base classes.
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (AsyncSession, async_sessionmaker,
                                    create_async_engine)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# Create async engine for async operations
# Configure pool settings based on database type
engine_kwargs = {
    "echo": False,  # 關閉詳細 SQL 日誌
    "future": True,
}

# Only add pool settings for non-SQLite databases
if not settings.database_url.startswith("sqlite"):
    engine_kwargs.update(
        {
            "pool_pre_ping": True,
            "pool_recycle": 3600,  # Recycle connections after 1 hour
            "pool_size": 10,
            "max_overflow": 20,
        }
    )

async_engine = create_async_engine(settings.database_url, **engine_kwargs)

# Create sync engine for Alembic migrations
sync_engine_kwargs = {
    "echo": False,  # 關閉詳細 SQL 日誌
    "future": True,
}

# Only add pool settings for non-SQLite databases
if not settings.database_url_sync.startswith("sqlite"):
    sync_engine_kwargs.update(
        {
            "pool_pre_ping": True,
            "pool_recycle": 3600,
            "pool_size": 10,
            "max_overflow": 20,
        }
    )

sync_engine = create_engine(settings.database_url_sync, **sync_engine_kwargs)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Create sync session factory for migrations
SessionLocal = sessionmaker(bind=sync_engine, autocommit=False, autoflush=False)

# Create declarative base class
Base = declarative_base()

# Metadata for Alembic
metadata = Base.metadata
