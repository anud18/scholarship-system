"""
Deadline Checker Task

Sends the one scheduled reminder the system still has: students whose
application is still an unsubmitted draft, 3 days before the deadline
they need to submit against.

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

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import AsyncSessionLocal
from app.models.application import Application, ApplicationStatus
from app.models.scholarship import ScholarshipConfiguration
from app.services.email_automation_service import email_automation_service

logger = logging.getLogger(__name__)


class DeadlineChecker:
    """Service for checking and notifying about approaching deadlines"""

    # Students are reminded exactly once, this many days before the deadline.
    REMINDER_DAYS_BEFORE = 3

    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_all_deadlines(self):
        """Check all types of deadlines and trigger notifications"""
        logger.info("Starting deadline check...")

        await self.check_submission_deadlines()

        logger.info("Deadline check completed")

    async def check_submission_deadlines(self):
        """Remind students whose application is still a draft 3 days before the deadline.

        Renewal and general applications are matched against their own deadline
        column, so a renewal draft is never reminded about the general deadline
        (or vice versa).
        """
        logger.info("Checking submission deadlines...")

        days_remaining = self.REMINDER_DAYS_BEFORE
        target_date = datetime.now(timezone.utc) + timedelta(days=days_remaining)
        target_date_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        target_date_end = target_date.replace(hour=23, minute=59, second=59, microsecond=999999)

        # (deadline column, deadline_type) — each pairs with its own draft population.
        deadline_columns = (
            (ScholarshipConfiguration.renewal_application_end_date, "renewal"),
            (ScholarshipConfiguration.application_end_date, "general"),
        )

        for deadline_column, deadline_type in deadline_columns:
            stmt = (
                select(ScholarshipConfiguration)
                .options(selectinload(ScholarshipConfiguration.scholarship_type))
                .where(
                    and_(
                        ScholarshipConfiguration.is_active.is_(True),
                        deadline_column.isnot(None),
                        deadline_column >= target_date_start,
                        deadline_column <= target_date_end,
                    )
                )
            )

            result = await self.db.execute(stmt)
            configs = result.scalars().all()

            logger.info(
                f"Found {len(configs)} scholarship configurations with {deadline_type} deadline in {days_remaining} days"
            )

            for config in configs:
                await self._notify_submission_deadline(config, days_remaining, deadline_type=deadline_type)

    async def _notify_submission_deadline(
        self, config: ScholarshipConfiguration, days_remaining: int, deadline_type: str = "general"
    ):
        """Send notifications for approaching submission deadline

        Args:
            config: ScholarshipConfiguration object
            days_remaining: Days remaining until deadline
            deadline_type: Type of deadline - "renewal" or "general"
        """
        # Determine which deadline to use, and which drafts it actually governs.
        is_renewal_deadline = deadline_type == "renewal"
        if is_renewal_deadline:
            deadline = config.renewal_application_end_date
            deadline_label = "renewal_submission"
        else:
            deadline = config.application_end_date
            deadline_label = "submission"

        if not deadline:
            logger.warning(f"No {deadline_type} deadline found for config {config.id}, skipping notification")
            return

        # Find students whose application for this scholarship is still an
        # unsubmitted draft. Renewal drafts answer to the renewal deadline only.
        stmt = (
            select(Application)
            .options(
                selectinload(Application.student),
                selectinload(Application.scholarship_type_ref),
            )
            .where(
                and_(
                    Application.scholarship_type_id == config.scholarship_type_id,
                    Application.academic_year == config.academic_year,
                    Application.semester == config.semester,
                    Application.status == ApplicationStatus.draft.value,
                    Application.is_renewal.is_(is_renewal_deadline),
                )
            )
        )

        result = await self.db.execute(stmt)
        draft_applications = result.scalars().all()

        logger.info(
            f"Found {len(draft_applications)} {deadline_type} draft applications for scholarship "
            f"{config.scholarship_type.name if config.scholarship_type else config.scholarship_type_id}"
        )

        for application in draft_applications:
            try:
                if not application.student:
                    logger.warning(f"Application {application.id} has no user, skipping")
                    continue

                student_data = application.student_data or {}

                await email_automation_service.trigger_deadline_approaching(
                    db=self.db,
                    application_id=application.id,
                    deadline_data={
                        "app_id": application.app_id,
                        "student_name": student_data.get("name") or application.student.name,
                        "student_email": student_data.get("email") or application.student.email,
                        "deadline": deadline.strftime("%Y-%m-%d %H:%M"),
                        "days_remaining": str(days_remaining),
                        "deadline_type": deadline_label,
                        "scholarship_name": config.scholarship_type.name if config.scholarship_type else "Unknown",
                        "scholarship_type_id": config.scholarship_type_id,
                    },
                )

                logger.info(
                    f"Triggered {deadline_type} deadline notification for application {application.id} "
                    f"(student: {application.student.email})"
                )

            except Exception as e:
                logger.exception(
                    "Failed to trigger deadline notification for application %s: %s",
                    application.id,
                    e,
                )


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
