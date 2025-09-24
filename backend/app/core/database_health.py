"""
Database health check and connection management utilities
"""

import asyncio
import logging
from typing import Any, Dict

from sqlalchemy import text

from app.db.session import (AsyncSessionLocal, async_engine,
                            invalidate_connection_pools)

logger = logging.getLogger(__name__)


async def check_database_health() -> Dict[str, Any]:
    """
    Perform comprehensive database health check

    Returns:
        Dict containing health status and connection information
    """
    health_info = {
        "status": "unknown",
        "connection": False,
        "cached_statement_error": False,
        "pool_info": {},
        "error": None,
    }

    try:
        # Test basic connection
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT 1"))
            row = result.fetchone()

            if row and row[0] == 1:
                health_info["connection"] = True
                health_info["status"] = "healthy"

            # Get pool information
            pool = async_engine.pool
            health_info["pool_info"] = {
                "size": pool.size(),
                "checked_in": pool.checkedin(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow(),
                "invalid": pool.invalidated_count()
                if hasattr(pool, "invalidated_count")
                else 0,
            }

    except Exception as e:
        error_message = str(e)
        health_info["error"] = error_message
        health_info["status"] = "unhealthy"

        # Check for specific PostgreSQL cached statement errors
        if (
            "InvalidCachedStatementError" in error_message
            or "cached statement plan is invalid" in error_message
        ):
            health_info["cached_statement_error"] = True
            logger.warning(
                f"Detected cached statement error during health check: {error_message}"
            )

        logger.error(f"Database health check failed: {e}")

    return health_info


async def recover_from_cached_statement_error() -> bool:
    """
    Attempt to recover from cached statement plan errors

    Returns:
        True if recovery was successful, False otherwise
    """
    try:
        logger.info("Attempting recovery from cached statement error...")

        # Step 1: Invalidate all connection pools
        await invalidate_connection_pools()

        # Step 2: Wait briefly for connections to be released
        await asyncio.sleep(1)

        # Step 3: Test connection with a fresh session
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT 1"))
            row = result.fetchone()

            if row and row[0] == 1:
                logger.info("Successfully recovered from cached statement error")
                return True

    except Exception as e:
        logger.error(f"Failed to recover from cached statement error: {e}")

    return False


async def handle_database_operation_with_retry(
    operation_func, max_retries: int = 3, *args, **kwargs
):
    """
    Execute a database operation with automatic retry on cached statement errors

    Args:
        operation_func: The async function to execute
        max_retries: Maximum number of retry attempts
        *args, **kwargs: Arguments to pass to the operation function

    Returns:
        Result of the operation function
    """
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return await operation_func(*args, **kwargs)

        except Exception as e:
            error_message = str(e)
            last_exception = e

            # Check if this is a cached statement error
            if (
                "InvalidCachedStatementError" in error_message
                or "cached statement plan is invalid" in error_message
            ):
                logger.warning(
                    f"Cached statement error on attempt {attempt + 1}/{max_retries + 1}: {error_message}"
                )

                if attempt < max_retries:
                    # Attempt recovery
                    recovery_success = await recover_from_cached_statement_error()
                    if recovery_success:
                        logger.info("Recovery successful, retrying operation...")
                        continue
                    else:
                        logger.error(f"Recovery failed on attempt {attempt + 1}")

            else:
                # For non-cached statement errors, don't retry
                logger.error(f"Non-recoverable database error: {error_message}")
                raise e

    # If we get here, all retry attempts failed
    logger.error(f"All retry attempts failed, raising last exception: {last_exception}")
    raise last_exception


class DatabaseHealthMiddleware:
    """
    Middleware to monitor database health and automatically handle connection issues
    """

    def __init__(self):
        self.last_health_check = 0
        self.health_check_interval = 300  # 5 minutes
        self.consecutive_failures = 0
        self.max_consecutive_failures = 3

    async def check_and_recover(self) -> bool:
        """
        Check database health and attempt recovery if needed

        Returns:
            True if database is healthy, False if unhealthy
        """
        import time

        current_time = time.time()

        # Skip if we checked recently
        if current_time - self.last_health_check < self.health_check_interval:
            return True

        self.last_health_check = current_time

        health_info = await check_database_health()

        if health_info["status"] == "healthy":
            self.consecutive_failures = 0
            return True

        self.consecutive_failures += 1

        # If we have cached statement errors, try to recover
        if health_info["cached_statement_error"]:
            logger.warning(
                "Attempting automatic recovery from cached statement error..."
            )
            recovery_success = await recover_from_cached_statement_error()

            if recovery_success:
                self.consecutive_failures = 0
                return True

        # If we have too many consecutive failures, this is a serious issue
        if self.consecutive_failures >= self.max_consecutive_failures:
            logger.critical(
                f"Database has been unhealthy for {self.consecutive_failures} consecutive checks"
            )

        return False
