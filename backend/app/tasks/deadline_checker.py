"""
Deadline Checker Task

This task checks for approaching deadlines and triggers email notifications.

Integration:
    - Automatically runs via APScheduler (daily at 9 AM) when backend starts
    - Integrated in roster_scheduler_service.py:init_scheduler()
    - No cron configuration needed

Manual Usage:
    # Run manually for testing
    python -m app.tasks.deadline_checker

    # Or use the script
    ./scripts/check_deadlines.sh
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import AsyncSessionLocal
from app.models.application import Application, ApplicationStatus
from app.models.scholarship import ScholarshipConfiguration
from app.services.email_automation_service import email_automation_service

logger = logging.getLogger(__name__)


class DeadlineChecker:
    """Service for checking and notifying about approaching deadlines"""

    # Warning thresholds (days before deadline)
    WARNING_DAYS = [7, 3, 1]

    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_all_deadlines(self):
        """Check all types of deadlines and trigger notifications"""
        logger.info("Starting deadline check...")

        # Check different deadline types
        await self.check_submission_deadlines()
        await self.check_document_request_deadlines()
        await self.check_review_deadlines()

        logger.info("Deadline check completed")

    async def check_submission_deadlines(self):
        """Check for approaching application submission deadlines"""
        logger.info("Checking submission deadlines...")

        for days_remaining in self.WARNING_DAYS:
            target_date = datetime.now(timezone.utc) + timedelta(days=days_remaining)
            target_date_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
            target_date_end = target_date.replace(hour=23, minute=59, second=59, microsecond=999999)

            # Check renewal application deadlines
            renewal_stmt = (
                select(ScholarshipConfiguration)
                .options(selectinload(ScholarshipConfiguration.scholarship_type))
                .where(
                    and_(
                        ScholarshipConfiguration.is_active.is_(True),
                        ScholarshipConfiguration.renewal_application_end_date.isnot(None),
                        ScholarshipConfiguration.renewal_application_end_date >= target_date_start,
                        ScholarshipConfiguration.renewal_application_end_date <= target_date_end,
                    )
                )
            )

            result = await self.db.execute(renewal_stmt)
            renewal_configs = result.scalars().all()

            logger.info(
                f"Found {len(renewal_configs)} scholarship configurations with renewal deadline in {days_remaining} days"
            )

            for config in renewal_configs:
                await self._notify_submission_deadline(config, days_remaining, deadline_type="renewal")

            # Check general application deadlines
            general_stmt = (
                select(ScholarshipConfiguration)
                .options(selectinload(ScholarshipConfiguration.scholarship_type))
                .where(
                    and_(
                        ScholarshipConfiguration.is_active.is_(True),
                        ScholarshipConfiguration.application_end_date.isnot(None),
                        ScholarshipConfiguration.application_end_date >= target_date_start,
                        ScholarshipConfiguration.application_end_date <= target_date_end,
                    )
                )
            )

            result = await self.db.execute(general_stmt)
            general_configs = result.scalars().all()

            logger.info(
                f"Found {len(general_configs)} scholarship configurations with general deadline in {days_remaining} days"
            )

            for config in general_configs:
                await self._notify_submission_deadline(config, days_remaining, deadline_type="general")

    async def _notify_submission_deadline(
        self, config: ScholarshipConfiguration, days_remaining: int, deadline_type: str = "general"
    ):
        """Send notifications for approaching submission deadline

        Args:
            config: ScholarshipConfiguration object
            days_remaining: Days remaining until deadline
            deadline_type: Type of deadline - "renewal" or "general"
        """
        # Determine which deadline to use
        if deadline_type == "renewal":
            deadline = config.renewal_application_end_date
            deadline_label = "renewal_submission"
        else:
            deadline = config.application_end_date
            deadline_label = "submission"

        if not deadline:
            logger.warning(f"No {deadline_type} deadline found for config {config.id}, skipping notification")
            return

        # Find students who have draft applications for this scholarship
        stmt = (
            select(Application)
            .options(
                selectinload(Application.user),
                selectinload(Application.scholarship_type_ref),
            )
            .where(
                and_(
                    Application.scholarship_type_id == config.scholarship_type_id,
                    Application.academic_year == config.academic_year,
                    Application.semester == config.semester,
                    or_(
                        Application.status == ApplicationStatus.draft.value,
                        Application.status == ApplicationStatus.in_progress.value,
                    ),
                )
            )
        )

        result = await self.db.execute(stmt)
        draft_applications = result.scalars().all()

        logger.info(
            f"Found {len(draft_applications)} draft applications for scholarship {config.scholarship_type.name if config.scholarship_type else config.scholarship_type_id}"
        )

        for application in draft_applications:
            try:
                if not application.user:
                    logger.warning(f"Application {application.id} has no user, skipping")
                    continue

                student_data = application.student_data or {}

                await email_automation_service.trigger_deadline_approaching(
                    db=self.db,
                    application_id=application.id,
                    deadline_data={
                        "app_id": application.app_id,
                        "student_name": student_data.get("name") or application.user.name,
                        "student_email": student_data.get("email") or application.user.email,
                        "deadline": deadline.strftime("%Y-%m-%d %H:%M"),
                        "days_remaining": str(days_remaining),
                        "deadline_type": deadline_label,
                        "scholarship_name": config.scholarship_type.name if config.scholarship_type else "Unknown",
                        "scholarship_type": application.main_scholarship_type,
                        "scholarship_type_id": config.scholarship_type_id,
                    },
                )

                logger.info(
                    f"Triggered {deadline_type} deadline notification for application {application.id} (student: {application.user.email})"
                )

            except Exception as e:
                logger.error(f"Failed to trigger deadline notification for application {application.id}: {e}")

    async def check_document_request_deadlines(self):
        """Check for approaching document request deadlines"""
        logger.info("Checking document request deadlines...")

        # Note: Current DocumentRequest model doesn't have a deadline field
        # This is a placeholder for future implementation
        # TODO: Add deadline field to DocumentRequest model

        logger.info("Document request deadline checking not yet implemented (no deadline field)")

    async def check_review_deadlines(self):
        """Check for approaching review deadlines"""
        logger.info("Checking review deadlines...")

        # Note: Current models don't have review deadline fields
        # This could be added to ScholarshipConfiguration in the future
        # TODO: Add professor_review_deadline and college_review_deadline fields

        logger.info("Review deadline checking not yet implemented (no deadline fields)")


async def run_deadline_check():
    """Run the deadline check task"""
    async with AsyncSessionLocal() as db:
        try:
            checker = DeadlineChecker(db)
            await checker.check_all_deadlines()
            await db.commit()
        except Exception as e:
            logger.error(f"Error during deadline check: {e}", exc_info=True)
            await db.rollback()
            raise


def main():
    """Main entry point for running deadline check as a script"""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info("Starting deadline check task...")
    asyncio.run(run_deadline_check())
    logger.info("Deadline check task completed")


if __name__ == "__main__":
    main()
