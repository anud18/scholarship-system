"""
Email Processor Task

This task processes scheduled emails from the queue and sends them.

Integration:
    - Automatically runs via APScheduler (every 15 seconds) when backend starts
    - Integrated in roster_scheduler_service.py:init_scheduler()
    - No cron configuration needed

Manual Usage:
    # Run manually for testing
    python -m app.tasks.email_processor
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.db.session import AsyncSessionLocal
from app.services.email_automation_service import email_automation_service

logger = logging.getLogger(__name__)

# Track when the module was initialized
_module_start_time = datetime.now(timezone.utc)
_MIN_STARTUP_DELAY_SECONDS = 5  # Minimum seconds to wait after startup before processing


async def run_email_processor():
    """Process scheduled emails that are due"""
    # Skip processing if we're still in the startup grace period
    time_since_start = (datetime.now(timezone.utc) - _module_start_time).total_seconds()
    if time_since_start < _MIN_STARTUP_DELAY_SECONDS:
        logger.debug(
            f"Skipping email processing - too soon after startup ({time_since_start:.1f}s < {_MIN_STARTUP_DELAY_SECONDS}s)"
        )
        return

    async with AsyncSessionLocal() as db:
        try:
            await email_automation_service.process_scheduled_emails(db)
            await db.commit()
        except Exception as e:
            logger.error(f"Error during email processing: {e}", exc_info=True)
            await db.rollback()
            # Don't re-raise - we don't want the scheduler to stop on errors


def main():
    """Main entry point for running email processor as a script"""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info("Starting email processor task...")
    asyncio.run(run_email_processor())
    logger.info("Email processor task completed")


if __name__ == "__main__":
    main()
