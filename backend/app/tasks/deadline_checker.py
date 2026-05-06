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
import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.application import Application, ApplicationStatus
from app.models.email_management import EmailCategory, ScheduledEmail
from app.models.review import ApplicationReview
from app.models.scholarship import ScholarshipConfiguration
from app.services.email_automation_service import email_automation_service
from app.services.email_service import EmailService
from app.services.frontend_email_renderer import render_email_via_frontend

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
                selectinload(Application.student),
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
                    f"Triggered {deadline_type} deadline notification for application {application.id} (student: {application.student.email})"
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
        await self.send_professor_review_deadline_reminders()

    async def send_professor_review_deadline_reminders(self):
        """Send daily reminder emails to professors with pending reviews in the last 3 days before deadline"""
        now = datetime.now(timezone.utc)
        window_end = now + timedelta(days=3)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Find active configs with professor_review_end within next 3 days (not yet passed)
        config_stmt = (
            select(ScholarshipConfiguration)
            .options(selectinload(ScholarshipConfiguration.scholarship_type))
            .where(
                and_(
                    ScholarshipConfiguration.is_active.is_(True),
                    ScholarshipConfiguration.professor_review_end.isnot(None),
                    ScholarshipConfiguration.professor_review_end >= now,
                    ScholarshipConfiguration.professor_review_end <= window_end,
                )
            )
        )
        result = await self.db.execute(config_stmt)
        configs = result.scalars().all()

        logger.info(f"Found {len(configs)} configs with professor review deadline in next 3 days")

        for config in configs:
            await self._send_professor_reminders_for_config(config, now, today_start)

    async def _send_professor_reminders_for_config(
        self, config: ScholarshipConfiguration, now: datetime, today_start: datetime
    ):
        """Find unreviewed applications for a config and schedule reminder emails"""
        app_stmt = (
            select(Application)
            .options(
                selectinload(Application.student),
                selectinload(Application.professor),
                selectinload(Application.scholarship_type_ref),
            )
            .where(
                and_(
                    Application.scholarship_configuration_id == config.id,
                    Application.professor_id.isnot(None),
                    or_(
                        Application.status == ApplicationStatus.submitted.value,
                        Application.status == ApplicationStatus.under_review.value,
                    ),
                    # Professor has not submitted a review yet
                    ~exists(
                        select(ApplicationReview.id).where(
                            and_(
                                ApplicationReview.application_id == Application.id,
                                ApplicationReview.reviewer_id == Application.professor_id,
                            )
                        )
                    ),
                    # No reminder email sent today for this application
                    ~exists(
                        select(ScheduledEmail.id).where(
                            and_(
                                ScheduledEmail.application_id == Application.id,
                                ScheduledEmail.template_key == "professor_review_notification",
                                ScheduledEmail.created_at >= today_start,
                            )
                        )
                    ),
                )
            )
        )

        result = await self.db.execute(app_stmt)
        applications = result.scalars().all()

        logger.info(
            f"Config {config.id}: scheduling {len(applications)} professor review deadline reminders"
        )

        for application in applications:
            try:
                await self._schedule_professor_deadline_reminder(application, config, now)
            except Exception as e:
                logger.error(
                    f"Failed to schedule deadline reminder for application {application.id}: {e}"
                )

    async def _schedule_professor_deadline_reminder(
        self, application: Application, config: ScholarshipConfiguration, now: datetime
    ):
        """Render and schedule one deadline reminder email for a professor"""
        professor = application.professor
        if not professor or not professor.email:
            logger.warning(f"Application {application.id} has no professor email, skipping")
            return

        days_remaining = math.ceil(
            (config.professor_review_end - now).total_seconds() / 86400
        )

        student_data = application.student_data or {}
        student_name = student_data.get("std_cname") or (
            application.student.name if application.student else ""
        )
        scholarship_name = config.scholarship_type.name if config.scholarship_type else ""
        submit_date = (
            application.submitted_at.strftime("%Y-%m-%d") if application.submitted_at else ""
        )
        app_id_str = application.app_id or str(application.id)

        context = {
            "professor_name": professor.name or "",
            "student_name": student_name,
            "app_id": app_id_str,
            "application_id": application.id,
            "scholarship_type": scholarship_name,
            "scholarship_name": scholarship_name,
            "submit_date": submit_date,
            "submission_date": submit_date,
            "system_url": settings.frontend_url,
            "review_url": f"{settings.frontend_url}/applications/{app_id_str}",
            "days_remaining": str(days_remaining),
            "review_deadline": config.professor_review_end.strftime("%Y-%m-%d"),
            "professor_email": professor.email,
            "student_email": "",
            "professor_recommendation": "",
            "review_result": "",
            "semester": "",
            "scholarship_amount": "",
        }

        html_content = None
        try:
            html_content = await render_email_via_frontend(
                frontend_url=settings.frontend_internal_url,
                template_name="professor-review-request",
                context=context,
            )
        except Exception as e:
            logger.error(f"Failed to render deadline reminder HTML for application {application.id}: {e}")

        await EmailService().schedule_email(
            db=self.db,
            to=professor.email,
            subject=f"[提醒] 尚有 {days_remaining} 天 — 請完成審核 {app_id_str}",
            body=f"請完成審核：{app_id_str}（剩餘 {days_remaining} 天）",
            scheduled_for=now,
            html_content=html_content,
            email_category=EmailCategory.recommendation_professor,
            application_id=application.id,
            scholarship_type_id=config.scholarship_type_id,
            template_key="professor_review_notification",
            created_by_user_id=1,
        )

        logger.info(
            f"Scheduled deadline reminder → {professor.email} for application {app_id_str} "
            f"({days_remaining} days remaining)"
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
