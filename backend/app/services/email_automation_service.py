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
from app.services.frontend_email_renderer import render_email_via_frontend
from app.services.system_setting_service import EmailTemplateService

logger = logging.getLogger(__name__)


class EmailAutomationService:
    """Service for handling automated email sending based on triggers"""

    def __init__(self):
        self.email_service = EmailService()

    async def get_automation_rules(self, db: AsyncSession, trigger_event: str) -> List[EmailAutomationRule]:
        """Get active automation rules for a specific trigger event"""
        try:
            logger.info(f"🔍 Fetching automation rules for trigger event: '{trigger_event}'")
            # Use ORM query with enum value
            stmt = (
                select(EmailAutomationRule)
                .where(EmailAutomationRule.trigger_event == TriggerEvent(trigger_event))
                .where(EmailAutomationRule.is_active)
            )

            result = await db.execute(stmt)
            rules = result.scalars().all()

            logger.info(f"✓ Found {len(rules)} active rules for '{trigger_event}'")
            for rule in rules:
                logger.info(f"  - Rule: {rule.name}, template: {rule.template_key}, delay: {rule.delay_hours}h")

            return list(rules)

        except Exception as e:
            logger.error(f"❌ Error fetching automation rules for trigger '{trigger_event}': {e}")
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

            # Use fallback email for testing and record keeping
            import os

            fallback_email = os.getenv("FALLBACK_EMAIL", "jotp.cs12@nycu.edu.tw")
            logger.warning(f"Using fallback email: {fallback_email}")
            recipients = [{"email": fallback_email}]

        # Get email template
        template = await EmailTemplateService.get_template(db, rule.template_key)
        if not template:
            logger.error(f"Template not found: {rule.template_key}")
            return

        # Determine email category from template key
        email_category = self._get_email_category_from_template_key(rule.template_key)

        # Schedule all emails (immediate or delayed) - async processing
        for recipient in recipients:
            try:
                recipient_context = {**context, **recipient}

                # Calculate scheduled time based on delay_hours
                scheduled_for = datetime.now(timezone.utc)
                if rule.delay_hours > 0:
                    scheduled_for += timedelta(hours=rule.delay_hours)
                    logger.info(
                        f"Scheduling email for {recipient['email']} at {scheduled_for} ({rule.delay_hours}h delay)"
                    )
                else:
                    logger.info(f"Scheduling email for immediate processing: {recipient['email']}")

                # Always use scheduled_emails table for async processing
                await self._schedule_automated_email(
                    db,
                    rule.template_key,
                    recipient["email"],
                    recipient_context,
                    scheduled_for,
                    email_category,
                    context,
                )

            except Exception as e:
                logger.error(f"Failed to schedule email to {recipient.get('email', 'unknown')}: {e}")

    async def _get_recipients(
        self, db: AsyncSession, rule: EmailAutomationRule, context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Get email recipients based on the rule's condition query.

        SECURITY: Uses parameterized queries to prevent SQL injection.
        Context values are passed as bound parameters, not string-formatted into SQL.
        """
        if not rule.condition_query:
            logger.warning(f"⚠️  No condition_query defined for rule {rule.template_key}")
            return []

        try:
            # SECURITY FIX: Use parameterized query instead of string formatting
            # Convert condition_query placeholders from {key} to :key format for bindparams
            parameterized_query = rule.condition_query

            # Replace {placeholder} with :placeholder for SQLAlchemy bindparams
            import re

            placeholders = re.findall(r"\{(\w+)\}", rule.condition_query)
            for placeholder in placeholders:
                parameterized_query = parameterized_query.replace(f"{{{placeholder}}}", f":{placeholder}")

            logger.info(f"📧 Executing recipient query for {rule.template_key}:")
            logger.info(f"   Query template: {parameterized_query[:200]}...")
            logger.info(f"   Parameters: {context}")

            # Execute with bound parameters (prevents SQL injection)
            result = await db.execute(text(parameterized_query), context)

            recipients = []
            for row in result:
                # Convert row to dict - assuming first column is email
                if row:
                    recipients.append({"email": row[0]})

            logger.info(f"✓ Found {len(recipients)} recipients: {[r['email'] for r in recipients]}")
            return recipients

        except Exception as e:
            logger.error(f"❌ Failed to execute condition query for rule {rule.template_key}: {e}")
            logger.error(f"   Context: {context}")
            logger.error(f"   Query: {rule.condition_query}")
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
            logger.info("📨 Sending automated email:")
            logger.info(f"   Template: {template_key}")
            logger.info(f"   To: {recipient_email}")
            logger.info(f"   Category: {email_category}")

            # Email metadata for logging
            metadata = {
                "email_category": email_category,
                "application_id": trigger_context.get("application_id"),
                "scholarship_type_id": trigger_context.get("scholarship_type_id"),
                "sent_by_system": True,
                "template_key": template_key,
            }

            # Get database template for subject
            template = await EmailTemplateService.get_template(db, template_key)
            if not template:
                logger.warning(f"Template not found in database: {template_key}, using defaults")
                subject = f"Automated notification - {template_key}"
            else:
                # Format subject with context
                subject = template.subject_template.format(**context)

            # Check if React Email template exists
            react_template_name = self._get_react_email_template_name(template_key)

            if react_template_name:
                # Use React Email template (HTML)
                logger.info(f"   Using React Email template: {react_template_name}")
                await self.email_service.send_with_react_template(
                    template_name=react_template_name,
                    to=recipient_email,
                    context=context,
                    subject=subject,
                    db=db,
                    **metadata,
                )
                logger.info(
                    f"✓ Successfully sent HTML email using React template {react_template_name} to {recipient_email}"
                )
            else:
                # Fall back to database template (plain text)
                logger.info("   No React Email template found, falling back to database template")
                default_subject = f"Automated notification - {template_key}"
                default_body = "This is an automated notification from the scholarship system."

                await self.email_service.send_with_template(
                    db=db,
                    key=template_key,
                    to=recipient_email,
                    context=context,
                    default_subject=default_subject,
                    default_body=default_body,
                    **metadata,
                )
                logger.info(
                    f"✓ Successfully sent plain text email using database template {template_key} to {recipient_email}"
                )

        except Exception as e:
            logger.error(f"❌ Failed to send automated email: {e}")
            logger.error(f"   Template: {template_key}, Recipient: {recipient_email}")
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

            # Check if React Email template exists
            react_template_name = self._get_react_email_template_name(template_key)

            # Email metadata for logging
            metadata = {
                "email_category": email_category,
                "application_id": trigger_context.get("application_id"),
                "scholarship_type_id": trigger_context.get("scholarship_type_id"),
                "template_key": template_key,
                "created_by_user_id": 1,  # System user ID
            }

            # Render HTML via frontend if React Email template exists
            html_content = None
            if react_template_name:
                try:
                    # Get frontend INTERNAL URL for API calls (Docker network)
                    from app.core.config import settings

                    frontend_url = settings.frontend_internal_url

                    logger.info(f"Rendering email via frontend: {react_template_name}")
                    logger.debug(f"Frontend internal URL: {frontend_url}")
                    logger.debug(f"Context keys: {list(context.keys())}")

                    # Call frontend API to render email
                    html_content = await render_email_via_frontend(
                        frontend_url=frontend_url, template_name=react_template_name, context=context
                    )

                    if html_content:
                        logger.info(
                            f"✓ Successfully rendered HTML for template '{react_template_name}' ({len(html_content)} chars)"
                        )
                    else:
                        logger.warning(f"⚠️  Frontend rendering returned no HTML for template '{react_template_name}'")

                except Exception as e:
                    logger.error(f"❌ Failed to render email via frontend: {e}")
                    # Continue without HTML - will fall back to plain text
                    html_content = None

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
                html_content=html_content,  # Pass rendered HTML
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

    def _get_react_email_template_name(self, template_key: str) -> str | None:
        """Map database template keys to React Email template names"""
        mapping = {
            "application_submitted_student": "application-submitted",
            "professor_review_notification": "professor-review-request",
            "college_review_notification": "college-review-request",
            "application_deadline_reminder": "deadline-reminder",
            "document_request_notification": "document-request",
            "result_notification_student": "result-notification",
            "roster_notification": "roster-notification",
            "whitelist_notification": "whitelist-notification",
        }
        return mapping.get(template_key)

    # Trigger methods for common events
    async def trigger_application_submitted(
        self, db: AsyncSession, application_id: int, application_data: Dict[str, Any]
    ):
        """Trigger emails when an application is submitted"""
        logger.info("🚀 EMAIL AUTOMATION TRIGGERED: application_submitted")
        logger.info(f"   Application ID: {application_id}")
        logger.info(f"   Student: {application_data.get('student_name')} ({application_data.get('student_email')})")
        logger.info(f"   Scholarship: {application_data.get('scholarship_type')}")

        # Extract student ID from student_data JSON
        student_data = application_data.get("student_data", {})
        if isinstance(student_data, str):
            import json

            student_data = json.loads(student_data) if student_data else {}

        # Prepare common values
        scholarship_type_value = application_data.get("scholarship_type", "")
        app_id_value = application_data.get("app_id", "")
        submit_date_value = application_data.get("submit_date", datetime.now().strftime("%Y-%m-%d"))

        # Get system URL from settings (environment-specific)
        from app.core.config import settings

        system_url_value = settings.frontend_url

        context = {
            # Basic information
            "application_id": application_id,  # Numeric ID for SQL queries (e.g., 5)
            "app_id": app_id_value,  # Formatted ID for templates (e.g., APP-2025-379885)
            "student_name": application_data.get("student_name", ""),
            "student_id": student_data.get("std_stdcode", ""),  # Extract student number from student_data
            "student_email": application_data.get("student_email", ""),
            "professor_name": application_data.get("professor_name", ""),
            "professor_email": application_data.get("professor_email", ""),
            # Scholarship information
            "scholarship_type": scholarship_type_value,
            "scholarship_name": scholarship_type_value,  # Alias for templates
            "scholarship_type_id": application_data.get("scholarship_type_id"),
            "scholarship_amount": application_data.get("scholarship_amount", ""),  # Optional
            # Date information (provide both aliases)
            "submit_date": submit_date_value,
            "submission_date": submit_date_value,  # Alias for templates
            # Semester information (optional)
            "semester": application_data.get("semester", ""),
            # URL information
            "system_url": system_url_value,
            "review_url": f"{system_url_value}/applications/{app_id_value}",
            "admin_portal_url": f"{system_url_value}/admin/applications",
            # Review-related fields (defaults to avoid KeyError)
            "review_deadline": application_data.get("review_deadline", ""),
            "professor_recommendation": "",
            "review_result": "",
        }

        await self.process_trigger(db, "application_submitted", context)
        logger.info(f"✓ Email automation trigger completed for application {application_id}")

    async def trigger_professor_review_submitted(
        self, db: AsyncSession, application_id: int, review_data: Dict[str, Any]
    ):
        """Trigger emails when professor submits review"""
        from app.core.config import settings

        scholarship_type_value = review_data.get("scholarship_type", "")
        context = {
            "application_id": application_id,
            "app_id": review_data.get("app_id", ""),
            "student_name": review_data.get("student_name", ""),
            "professor_name": review_data.get("professor_name", ""),
            "professor_email": review_data.get("professor_email", ""),
            "scholarship_type": scholarship_type_value,
            "scholarship_name": scholarship_type_value,  # Alias for backward compatibility with templates
            "scholarship_type_id": review_data.get("scholarship_type_id"),
            "review_result": review_data.get("review_result", ""),
            "review_date": review_data.get("review_date", datetime.now().strftime("%Y-%m-%d")),
            "professor_recommendation": review_data.get("professor_recommendation", ""),
            "college_name": review_data.get("college_name", ""),
            "review_deadline": review_data.get("review_deadline", ""),
            "system_url": settings.frontend_url,
        }

        await self.process_trigger(db, "professor_review_submitted", context)

    async def trigger_final_result_decided(self, db: AsyncSession, application_id: int, result_data: Dict[str, Any]):
        """Trigger emails when final result is decided"""
        from app.core.config import settings

        scholarship_type_value = result_data.get("scholarship_type", "")
        context = {
            "application_id": application_id,
            "app_id": result_data.get("app_id", ""),
            "student_name": result_data.get("student_name", ""),
            "student_email": result_data.get("student_email", ""),
            "professor_name": result_data.get("professor_name", ""),
            "professor_email": result_data.get("professor_email", ""),
            "college_name": result_data.get("college_name", ""),
            "scholarship_type": scholarship_type_value,
            "scholarship_name": scholarship_type_value,  # Alias for backward compatibility with templates
            "scholarship_type_id": result_data.get("scholarship_type_id"),
            "result_status": result_data.get("result_status", ""),
            "approved_amount": result_data.get("approved_amount", ""),
            "result_message": result_data.get("result_message", ""),
            "next_steps": result_data.get("next_steps", ""),
            "system_url": settings.frontend_url,
        }

        await self.process_trigger(db, "final_result_decided", context)

    async def trigger_college_review_submitted(
        self, db: AsyncSession, application_id: int, review_data: Dict[str, Any]
    ):
        """Trigger emails when college submits review"""
        from app.core.config import settings

        scholarship_type_value = review_data.get("scholarship_type", "")
        context = {
            "application_id": application_id,
            "app_id": review_data.get("app_id", ""),
            "student_name": review_data.get("student_name", ""),
            "student_email": review_data.get("student_email", ""),
            "college_name": review_data.get("college_name", ""),
            # Note: college_ranking_score removed - use final_rank instead
            "college_final_rank": review_data.get("final_rank"),
            "college_recommendation": review_data.get("recommendation", ""),
            "college_comments": review_data.get("comments", ""),
            "reviewer_name": review_data.get("reviewer_name", ""),
            "scholarship_type": scholarship_type_value,
            "scholarship_name": scholarship_type_value,  # Alias for backward compatibility with templates
            "scholarship_type_id": review_data.get("scholarship_type_id"),
            "review_date": review_data.get("review_date", datetime.now().strftime("%Y-%m-%d")),
            "system_url": settings.frontend_url,
        }

        await self.process_trigger(db, "college_review_submitted", context)

    async def trigger_supplement_requested(self, db: AsyncSession, application_id: int, request_data: Dict[str, Any]):
        """Trigger emails when supplement documents are requested"""
        from app.core.config import settings

        scholarship_type_value = request_data.get("scholarship_type", "")
        context = {
            "application_id": application_id,
            "app_id": request_data.get("app_id", ""),
            "student_name": request_data.get("student_name", ""),
            "student_email": request_data.get("student_email", ""),
            "requested_documents": ", ".join(request_data.get("requested_documents", [])),
            "reason": request_data.get("reason", ""),
            "notes": request_data.get("notes", ""),
            "requester_name": request_data.get("requester_name", ""),
            "deadline": request_data.get("deadline", ""),
            "scholarship_type": scholarship_type_value,
            "scholarship_name": scholarship_type_value,  # Alias for backward compatibility with templates
            "scholarship_type_id": request_data.get("scholarship_type_id"),
            "request_date": request_data.get("request_date", datetime.now().strftime("%Y-%m-%d")),
            "system_url": settings.frontend_url,
        }

        await self.process_trigger(db, "supplement_requested", context)

    async def trigger_deadline_approaching(self, db: AsyncSession, application_id: int, deadline_data: Dict[str, Any]):
        """Trigger emails when deadline is approaching"""
        from app.core.config import settings

        scholarship_type_value = deadline_data.get("scholarship_type", "")
        context = {
            "application_id": application_id,
            "app_id": deadline_data.get("app_id", ""),
            "student_name": deadline_data.get("student_name", ""),
            "student_email": deadline_data.get("student_email", ""),
            "deadline": deadline_data.get("deadline", ""),
            "days_remaining": deadline_data.get("days_remaining", ""),
            "deadline_type": deadline_data.get("deadline_type", ""),  # e.g., "submission", "supplement"
            "scholarship_type": scholarship_type_value,
            "scholarship_name": scholarship_type_value,  # Alias for backward compatibility with templates
            "scholarship_type_id": deadline_data.get("scholarship_type_id"),
            "system_url": settings.frontend_url,
        }

        await self.process_trigger(db, "deadline_approaching", context)

    async def process_scheduled_emails(self, db: AsyncSession):
        """Process and send scheduled emails that are due"""
        try:
            # Get scheduled emails that are ready to send
            query = text(
                """
                SELECT id, recipient_email, subject, body, html_body, cc_emails, bcc_emails, template_key,
                       email_category, application_id, scholarship_type_id, priority
                FROM scheduled_emails
                WHERE status = 'pending'
                AND scheduled_for <= NOW()
                AND (requires_approval = false OR approved_by_user_id IS NOT NULL)
                ORDER BY priority ASC, scheduled_for ASC
                LIMIT 50
            """
            )

            result = await db.execute(query)
            scheduled_emails = result.fetchall()

            logger.info(f"📬 Processing {len(scheduled_emails)} scheduled emails")

            for email_row in scheduled_emails:
                try:
                    # Parse CC and BCC
                    import json

                    cc_emails = json.loads(email_row.cc_emails) if email_row.cc_emails else None
                    bcc_emails = json.loads(email_row.bcc_emails) if email_row.bcc_emails else None

                    # Prepare metadata
                    metadata = {
                        "email_category": (
                            EmailCategory(email_row.email_category)
                            if email_row.email_category
                            else EmailCategory.system
                        ),
                        "application_id": email_row.application_id,
                        "scholarship_type_id": email_row.scholarship_type_id,
                        "sent_by_system": True,
                        "template_key": email_row.template_key,
                    }

                    # Preferred path: Use pre-rendered HTML if available
                    if email_row.html_body:
                        logger.info(f"   Using pre-rendered HTML for email {email_row.id}")
                        await self.email_service.send_email(
                            to=email_row.recipient_email,
                            subject=email_row.subject,
                            body=email_row.body,
                            html_content=email_row.html_body,  # Use stored pre-rendered HTML
                            cc=cc_emails,
                            bcc=bcc_emails,
                            db=db,
                            **metadata,
                        )
                        logger.info(f"✓ Sent pre-rendered HTML email {email_row.id} to {email_row.recipient_email}")

                    # Fallback path: Check if React Email template exists for this template_key
                    elif (
                        react_template_name := (
                            self._get_react_email_template_name(email_row.template_key)
                            if email_row.template_key
                            else None
                        )
                    ) and email_row.application_id:
                        # Use React Email template with fresh application data (backward compatible)
                        logger.info(
                            f"   Using React Email template '{react_template_name}' for email {email_row.id} (fallback)"
                        )

                        try:
                            # Re-query application data for fresh context
                            from sqlalchemy import select

                            from app.models.application import Application

                            app_query = select(Application).where(Application.id == email_row.application_id)
                            app_result = await db.execute(app_query)
                            application = app_result.scalar_one_or_none()

                            if application:
                                # Build context from application data
                                from app.core.config import settings

                                student_data = application.student_data if application.student_data else {}
                                context = {
                                    "app_id": application.app_id,
                                    "student_name": student_data.get("std_cname", ""),
                                    "student_id": student_data.get("std_stdcode", ""),
                                    "scholarship_type_id": application.scholarship_type_id or "",
                                    "scholarship_name": application.scholarship_name or "",
                                    "submit_date": (
                                        application.submitted_at.strftime("%Y-%m-%d")
                                        if application.submitted_at
                                        else ""
                                    ),
                                    "submission_date": (
                                        application.submitted_at.strftime("%Y-%m-%d")
                                        if application.submitted_at
                                        else ""
                                    ),
                                    "professor_name": application.professor.name if application.professor else "",
                                    "system_url": settings.frontend_url,
                                }

                                # Send with React template (no html_content, will use fallback template loader)
                                await self.email_service.send_with_react_template(
                                    template_name=react_template_name,
                                    to=email_row.recipient_email,
                                    context=context,
                                    subject=email_row.subject,
                                    cc=cc_emails,
                                    bcc=bcc_emails,
                                    db=db,
                                    **metadata,
                                )
                                logger.info(
                                    f"✓ Sent React Email {email_row.id} to {email_row.recipient_email} using {react_template_name} (fallback)"
                                )
                            else:
                                # Application not found, fall back to plain text
                                logger.warning(
                                    f"Application {email_row.application_id} not found, falling back to plain text"
                                )
                                await self.email_service.send_email(
                                    to=email_row.recipient_email,
                                    subject=email_row.subject,
                                    body=email_row.body,
                                    cc=cc_emails,
                                    bcc=bcc_emails,
                                    db=db,
                                    **metadata,
                                )

                        except Exception as react_error:
                            logger.error(f"Failed to send React Email, falling back to plain text: {react_error}")
                            # Fall back to plain text if React template fails
                            await self.email_service.send_email(
                                to=email_row.recipient_email,
                                subject=email_row.subject,
                                body=email_row.body,
                                cc=cc_emails,
                                bcc=bcc_emails,
                                db=db,
                                **metadata,
                            )
                    else:
                        # No HTML available, use plain text
                        logger.info(f"   Sending plain text email {email_row.id}")
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
                        SET status = 'sent', updated_at = NOW()
                        WHERE id = :email_id
                    """
                    )
                    await db.execute(update_query, {"email_id": email_row.id})

                except Exception as e:
                    logger.error(f"Failed to send scheduled email {email_row.id}: {e}")

                    # Mark as failed
                    fail_query = text(
                        """
                        UPDATE scheduled_emails
                        SET status = 'failed', last_error = :error, retry_count = retry_count + 1, updated_at = NOW()
                        WHERE id = :email_id
                    """
                    )
                    await db.execute(fail_query, {"email_id": email_row.id, "error": str(e)})

            await db.commit()
            logger.info(f"✓ Completed processing {len(scheduled_emails)} scheduled emails")

        except Exception as e:
            logger.error(f"Failed to process scheduled emails: {e}")
            await db.rollback()
            raise


# Singleton instance
email_automation_service = EmailAutomationService()
