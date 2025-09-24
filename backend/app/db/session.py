"""
Database session management
"""

from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from app.core.config import settings

# Enhanced async engine configuration for PostgreSQL with better error handling
async_engine = create_async_engine(
    settings.database_url,
    echo=False,  # 關閉詳細 SQL 日誌
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=5,
    max_overflow=10,
    poolclass=QueuePool,
    # Additional async engine parameters for better connection management
    connect_args={
        "prepared_statement_cache_size": 0,  # Disable prepared statement cache
        "statement_cache_size": 0,  # Disable statement cache
        "command_timeout": 60,  # Command timeout in seconds
    }
    if "postgresql" in settings.database_url
    else {},
)

# Enhanced sync engine configuration for PostgreSQL
sync_engine = create_engine(
    settings.database_url_sync,
    echo=False,  # 關閉詳細 SQL 日誌
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=5,
    max_overflow=10,
    poolclass=QueuePool,
    # Additional sync engine parameters for better connection management
    connect_args={
        "connect_timeout": 30,  # Connection timeout in seconds
    }
    if "postgresql" in settings.database_url_sync
    else {},
)

# Async session maker (SQLAlchemy 2.0 style)
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=True,
    autocommit=False,
)

# Sync session maker for migrations
SessionLocal = sessionmaker(
    bind=sync_engine,
    autoflush=True,
    autocommit=False,
)


# Database connection error handling utilities
async def handle_cached_statement_error(session: AsyncSession, operation_func, *args, **kwargs):
    """
    Handle InvalidCachedStatementError by retrying the operation with a fresh connection

    This function addresses the PostgreSQL asyncpg cached statement plan invalidation
    issue that occurs after schema or configuration changes.
    """
    from sqlalchemy.dialects.postgresql.asyncpg import InvalidCachedStatementError

    try:
        return await operation_func(*args, **kwargs)
    except InvalidCachedStatementError as e:
        # Log the error for monitoring
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(f"Cached statement plan invalidated, retrying operation: {e}")

        # Invalidate the connection and get a fresh one
        await session.invalidate()
        await session.rollback()

        # Retry the operation with fresh connection
        try:
            return await operation_func(*args, **kwargs)
        except Exception as retry_error:
            logger.error(f"Operation failed even after connection refresh: {retry_error}")
            raise
    except Exception as e:
        # Handle other database errors
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Database operation failed: {e}")
        raise


async def get_db_session():
    """
    Get a database session with proper error handling

    This function provides a database session with built-in handling
    for common PostgreSQL connection issues.
    """
    session = AsyncSessionLocal()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def invalidate_connection_pools():
    """
    Invalidate all connection pools to force fresh connections

    Use this function when encountering persistent cached statement errors
    or after significant schema changes.
    """
    import logging

    logger = logging.getLogger(__name__)

    try:
        # For SQLAlchemy 2.0, we need to dispose the engines to invalidate connections
        # This will close all connections and recreate the pool

        # Get current pool stats before disposal
        async_pool = async_engine.pool
        sync_pool = sync_engine.pool

        logger.info(
            f"Before invalidation - Async pool: {async_pool.size()} connections, Sync pool: {sync_pool.size()} connections"
        )

        # Dispose and recreate pools (SQLAlchemy 2.0 approach)
        await async_engine.dispose()
        logger.info("Async engine connection pool disposed and will be recreated")

        sync_engine.dispose()
        logger.info("Sync engine connection pool disposed and will be recreated")

    except Exception as e:
        logger.error(f"Failed to invalidate connection pools: {e}")


def invalidate_connection_pools_sync():
    """
    Synchronous version of connection pool invalidation for use in non-async contexts
    """
    import logging

    logger = logging.getLogger(__name__)

    try:
        # Only dispose sync engine in sync context
        sync_engine.dispose()
        logger.info("Sync engine connection pool disposed and will be recreated")

        # For async engine, we can't dispose it synchronously, but we can log the issue
        logger.warning(
            "Async engine disposal requires async context - consider using invalidate_connection_pools() in async context"
        )

    except Exception as e:
        logger.error(f"Failed to invalidate sync connection pool: {e}")


# Event listeners for connection management
@event.listens_for(async_engine.sync_engine, "connect")
def set_postgresql_connection_options(dbapi_connection, connection_record):
    """
    Set PostgreSQL connection options to prevent cached statement issues
    """
    if hasattr(dbapi_connection, "autocommit"):
        # Configure connection settings for better error handling
        pass  # asyncpg connections are handled differently
