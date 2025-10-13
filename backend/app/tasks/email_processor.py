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

from app.db.session import AsyncSessionLocal
from app.services.email_automation_service import email_automation_service

logger = logging.getLogger(__name__)


async def run_email_processor():
    """Process scheduled emails that are due"""
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
