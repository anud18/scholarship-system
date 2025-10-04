"""
Email automation service for handling automated email triggers
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_management import EmailAutomationRule, EmailCategory, TriggerEvent
from app.services.email_service import EmailService
from app.services.system_setting_service import EmailTemplateService

logger = logging.getLogger(__name__)


class EmailAutomationService:
    """Service for handling automated email sending based on triggers"""

    def __init__(self):
        self.email_service = EmailService()

    async def get_automation_rules(self, db: AsyncSession, trigger_event: str) -> List[EmailAutomationRule]:
        """Get active automation rules for a specific trigger event"""
        try:
            # Use ORM query with enum value
            stmt = (
                select(EmailAutomationRule)
                .where(EmailAutomationRule.trigger_event == TriggerEvent(trigger_event))
                .where(EmailAutomationRule.is_active == True)
            )

            result = await db.execute(stmt)
            rules = result.scalars().all()

            return list(rules)

        except Exception as e:
            logger.error(f"Error fetching automation rules for trigger '{trigger_event}': {e}")
            return []

    async def process_trigger(self, db: AsyncSession, trigger_event: str, context: Dict[str, Any]):
        """Process a trigger event and send appropriate automated emails"""
        try:
            rules = await self.get_automation_rules(db, trigger_event)
            logger.info(f"Processing trigger '{trigger_event}' with {len(rules)} rules")

            for rule in rules:
                try:
                    await self._process_single_rule(db, rule, context)
                except Exception as e:
                    logger.error(f"Failed to process rule {rule.template_key}: {e}")
                    # Continue processing other rules even if one fails

        except Exception as e:
            logger.error(f"Failed to process trigger '{trigger_event}': {e}")
            raise

    async def _process_single_rule(self, db: AsyncSession, rule: EmailAutomationRule, context: Dict[str, Any]):
        """Process a single automation rule"""
        logger.info(f"Processing rule: {rule.template_key} for trigger: {rule.trigger_event}")

        # Get recipients based on condition query
        recipients = await self._get_recipients(db, rule, context)
        if not recipients:
            logger.warning(f"No recipients found for rule {rule.template_key}")
            return

        # Get email template
        template = await EmailTemplateService.get_template(db, rule.template_key)
        if not template:
            logger.error(f"Template not found: {rule.template_key}")
            return

        # Determine email category from template key
        email_category = self._get_email_category_from_template_key(rule.template_key)

        # Send emails (immediate or scheduled based on delay)
        for recipient in recipients:
            try:
                recipient_context = {**context, **recipient}

                if rule.delay_hours > 0:
                    # Schedule email for later
                    scheduled_for = datetime.now(timezone.utc) + timedelta(hours=rule.delay_hours)
                    await self._schedule_automated_email(
                        db,
                        rule.template_key,
                        recipient["email"],
                        recipient_context,
                        scheduled_for,
                        email_category,
                        context,
                    )
                else:
                    # Send immediately
                    await self._send_automated_email(
                        db,
                        rule.template_key,
                        recipient["email"],
                        recipient_context,
                        email_category,
                        context,
                    )

            except Exception as e:
                logger.error(f"Failed to send email to {recipient.get('email', 'unknown')}: {e}")

    async def _get_recipients(
        self, db: AsyncSession, rule: EmailAutomationRule, context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Get email recipients based on the rule's condition query"""
        if not rule.condition_query:
            return []

        try:
            # Replace placeholders in the query with context values
            formatted_query = rule.condition_query.format(**context)
            result = await db.execute(text(formatted_query))

            recipients = []
            for row in result:
                # Convert row to dict - assuming first column is email
                if row:
                    recipients.append({"email": row[0]})

            return recipients

        except Exception as e:
            logger.error(f"Failed to execute condition query for rule {rule.template_key}: {e}")
            return []

    async def _send_automated_email(
        self,
        db: AsyncSession,
        template_key: str,
        recipient_email: str,
        context: Dict[str, Any],
        email_category: EmailCategory,
        trigger_context: Dict[str, Any],
    ):
        """Send an automated email immediately"""
        try:
            # Prepare default subject and body (fallbacks)
            default_subject = f"Automated notification - {template_key}"
            default_body = "This is an automated notification from the scholarship system."

            # Email metadata for logging
            metadata = {
                "email_category": email_category,
                "application_id": trigger_context.get("application_id"),
                "scholarship_type_id": trigger_context.get("scholarship_type_id"),
                "sent_by_system": True,
                "template_key": template_key,
            }

            await self.email_service.send_with_template(
                db=db,
                key=template_key,
                to=recipient_email,
                context=context,
                default_subject=default_subject,
                default_body=default_body,
                **metadata,
            )

            logger.info(f"Sent automated email using template {template_key} to {recipient_email}")

        except Exception as e:
            logger.error(f"Failed to send automated email: {e}")
            raise

    async def _schedule_automated_email(
        self,
        db: AsyncSession,
        template_key: str,
        recipient_email: str,
        context: Dict[str, Any],
        scheduled_for: datetime,
        email_category: EmailCategory,
        trigger_context: Dict[str, Any],
    ):
        """Schedule an automated email for later sending"""
        try:
            template = await EmailTemplateService.get_template(db, template_key)
            if not template:
                raise ValueError(f"Template not found: {template_key}")

            # Format subject and body with context
            subject = template.subject_template.format(**context)
            body = template.body_template.format(**context)

            # Email metadata for logging
            metadata = {
                "email_category": email_category,
                "application_id": trigger_context.get("application_id"),
                "scholarship_type_id": trigger_context.get("scholarship_type_id"),
                "template_key": template_key,
                "created_by_user_id": 1,  # System user ID
            }

            scheduled_email = await self.email_service.schedule_email(
                db=db,
                to=recipient_email,
                subject=subject,
                body=body,
                scheduled_for=scheduled_for,
                cc=template.cc.split(",") if template.cc else None,
                bcc=template.bcc.split(",") if template.bcc else None,
                requires_approval=False,  # Automated emails don't need approval
                priority=3,  # Medium priority for automated emails
                **metadata,
            )

            logger.info(f"Scheduled automated email {template_key} for {recipient_email} at {scheduled_for}")
            return scheduled_email

        except Exception as e:
            logger.error(f"Failed to schedule automated email: {e}")
            raise

    def _get_email_category_from_template_key(self, template_key: str) -> EmailCategory:
        """Map template key to appropriate email category"""
        category_mapping = {
            "application_submitted_student": EmailCategory.application_student,
            "application_notify_professor": EmailCategory.recommendation_professor,
            "review_submitted_professor": EmailCategory.recommendation_professor,
            "whitelist_notification": EmailCategory.application_whitelist,
            "deadline_reminder_draft": EmailCategory.application_student,
            "college_review_notification": EmailCategory.review_college,
            "supplement_request": EmailCategory.supplement_student,
            "result_notification_student": EmailCategory.result_student,
            "result_notification_professor": EmailCategory.result_professor,
            "result_notification_college": EmailCategory.result_college,
            "roster_notification": EmailCategory.roster_student,
        }

        return category_mapping.get(template_key, EmailCategory.system)

    # Trigger methods for common events
    async def trigger_application_submitted(
        self, db: AsyncSession, application_id: int, application_data: Dict[str, Any]
    ):
        """Trigger emails when an application is submitted"""
        context = {
            "application_id": application_id,
            "app_id": application_data.get("app_id", ""),
            "student_name": application_data.get("student_name", ""),
            "student_email": application_data.get("student_email", ""),
            "professor_name": application_data.get("professor_name", ""),
            "professor_email": application_data.get("professor_email", ""),
            "scholarship_type": application_data.get("scholarship_type", ""),
            "scholarship_type_id": application_data.get("scholarship_type_id"),
            "submit_date": application_data.get("submit_date", datetime.now().strftime("%Y-%m-%d")),
            "system_url": "https://scholarship.nycu.edu.tw",  # Replace with actual URL
        }

        await self.process_trigger(db, "application_submitted", context)

    async def trigger_professor_review_submitted(
        self, db: AsyncSession, application_id: int, review_data: Dict[str, Any]
    ):
        """Trigger emails when professor submits review"""
        context = {
            "application_id": application_id,
            "app_id": review_data.get("app_id", ""),
            "student_name": review_data.get("student_name", ""),
            "professor_name": review_data.get("professor_name", ""),
            "professor_email": review_data.get("professor_email", ""),
            "scholarship_type": review_data.get("scholarship_type", ""),
            "scholarship_type_id": review_data.get("scholarship_type_id"),
            "review_result": review_data.get("review_result", ""),
            "review_date": review_data.get("review_date", datetime.now().strftime("%Y-%m-%d")),
            "professor_recommendation": review_data.get("professor_recommendation", ""),
            "college_name": review_data.get("college_name", ""),
            "review_deadline": review_data.get("review_deadline", ""),
            "system_url": "https://scholarship.nycu.edu.tw",
        }

        await self.process_trigger(db, "professor_review_submitted", context)

    async def trigger_final_result_decided(self, db: AsyncSession, application_id: int, result_data: Dict[str, Any]):
        """Trigger emails when final result is decided"""
        context = {
            "application_id": application_id,
            "app_id": result_data.get("app_id", ""),
            "student_name": result_data.get("student_name", ""),
            "student_email": result_data.get("student_email", ""),
            "professor_name": result_data.get("professor_name", ""),
            "professor_email": result_data.get("professor_email", ""),
            "college_name": result_data.get("college_name", ""),
            "scholarship_type": result_data.get("scholarship_type", ""),
            "scholarship_type_id": result_data.get("scholarship_type_id"),
            "result_status": result_data.get("result_status", ""),
            "approved_amount": result_data.get("approved_amount", ""),
            "result_message": result_data.get("result_message", ""),
            "next_steps": result_data.get("next_steps", ""),
            "system_url": "https://scholarship.nycu.edu.tw",
        }

        await self.process_trigger(db, "final_result_decided", context)

    async def process_scheduled_emails(self, db: AsyncSession):
        """Process and send scheduled emails that are due"""
        try:
            # Get scheduled emails that are ready to send
            query = text(
                """
                SELECT id, recipient_email, subject, body, cc_emails, bcc_emails, template_key,
                       email_category, application_id, scholarship_type_id, priority
                FROM scheduled_emails
                WHERE status = 'PENDING'
                AND scheduled_for <= NOW()
                AND (requires_approval = false OR approved_by_user_id IS NOT NULL)
                ORDER BY priority ASC, scheduled_for ASC
                LIMIT 50
            """
            )

            result = await db.execute(query)
            scheduled_emails = result.fetchall()

            logger.info(f"Processing {len(scheduled_emails)} scheduled emails")

            for email_row in scheduled_emails:
                try:
                    # Parse CC and BCC
                    import json

                    cc_emails = json.loads(email_row.cc_emails) if email_row.cc_emails else None
                    bcc_emails = json.loads(email_row.bcc_emails) if email_row.bcc_emails else None

                    # Send the email
                    metadata = {
                        "email_category": EmailCategory(email_row.email_category)
                        if email_row.email_category
                        else EmailCategory.system,
                        "application_id": email_row.application_id,
                        "scholarship_type_id": email_row.scholarship_type_id,
                        "sent_by_system": True,
                        "template_key": email_row.template_key,
                    }

                    await self.email_service.send_email(
                        to=email_row.recipient_email,
                        subject=email_row.subject,
                        body=email_row.body,
                        cc=cc_emails,
                        bcc=bcc_emails,
                        db=db,
                        **metadata,
                    )

                    # Mark as sent
                    update_query = text(
                        """
                        UPDATE scheduled_emails
                        SET status = 'SENT', updated_at = NOW()
                        WHERE id = :email_id
                    """
                    )
                    await db.execute(update_query, {"email_id": email_row.id})

                    logger.info(f"Sent scheduled email {email_row.id} to {email_row.recipient_email}")

                except Exception as e:
                    logger.error(f"Failed to send scheduled email {email_row.id}: {e}")

                    # Mark as failed
                    fail_query = text(
                        """
                        UPDATE scheduled_emails
                        SET status = 'FAILED', last_error = :error, retry_count = retry_count + 1, updated_at = NOW()
                        WHERE id = :email_id
                    """
                    )
                    await db.execute(fail_query, {"email_id": email_row.id, "error": str(e)})

            await db.commit()

        except Exception as e:
            logger.error(f"Failed to process scheduled emails: {e}")
            await db.rollback()
            raise


# Singleton instance
email_automation_service = EmailAutomationService()
