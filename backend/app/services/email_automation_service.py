"""
Email automation service for handling automated email triggers
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.sql_read_only_guard import UnsafeConditionQueryError, assert_read_only_select, mask_literals
from app.models.email_management import EmailAutomationRule, EmailCategory, TriggerEvent
from app.services.email_service import EmailService
from app.services.frontend_email_renderer import render_email_via_frontend
from app.services.system_setting_service import EmailTemplateService

logger = logging.getLogger(__name__)

# ``{placeholder}`` -> ``:placeholder`` rewriting for admin-authored recipient queries.
_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")

# Hard ceiling for a single recipient query (PostgreSQL only).
RECIPIENT_QUERY_TIMEOUT_MS = 5000


def _dialect_name(db: AsyncSession) -> str:
    """Dialect of the session's bind.

    FAILS CLOSED. An earlier revision wrapped this in ``except Exception: return
    ""``, which meant a bind-resolution failure silently skipped BOTH
    ``statement_timeout`` and ``transaction_read_only`` — the admin-authored query
    then ran unbounded and write-enabled with no log line saying the control had
    been skipped. A security control must not degrade quietly.

    The only tolerated case is a session object with no ``get_bind`` at all (unit
    test stubs), where there is no real database to protect.
    """
    get_bind = getattr(db, "get_bind", None)
    if get_bind is None:
        return ""
    name = getattr(getattr(get_bind(), "dialect", None), "name", None)
    if not name:
        raise UnsafeConditionQueryError("could not determine the database dialect to apply read-only guards")
    return name


def bind_placeholders(sql: str, context: Dict[str, Any]) -> str:
    """Rewrite ``{key}`` to ``:key`` so values bind as parameters, never as SQL text.

    Occurrences are located on the MASKED copy, so a ``{...}`` sitting inside a
    string literal or a comment is left alone — rewriting it would corrupt the
    literal. The substitution itself is applied to the ORIGINAL by offset, which
    is why the mask must be the same length.

    A placeholder with no matching context key raises: silently leaving a literal
    ``{key}`` in the SQL would send a malformed statement to the database.
    """
    masked = mask_literals(sql)
    result: list[str] = []
    cursor = 0
    for match in _PLACEHOLDER_RE.finditer(masked):
        key = match.group(1)
        if key not in context:
            raise UnsafeConditionQueryError(f"references unknown context key: {{{key}}}")
        result.append(sql[cursor : match.start()])
        result.append(f":{key}")
        cursor = match.end()
    result.append(sql[cursor:])
    return "".join(result)


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

        except Exception:
            logger.exception(f"❌ Error fetching automation rules for trigger '{trigger_event}'")
            return []

    async def process_trigger(self, db: AsyncSession, trigger_event: str, context: Dict[str, Any]):
        """Process a trigger event and send appropriate automated emails"""
        try:
            rules = await self.get_automation_rules(db, trigger_event)
            logger.info(f"Processing trigger '{trigger_event}' with {len(rules)} rules")

            for rule in rules:
                try:
                    await self._process_single_rule(db, rule, context)
                except Exception:
                    logger.exception(f"Failed to process rule {rule.template_key}")
                    # Continue processing other rules even if one fails

        except Exception:
            logger.exception(f"Failed to process trigger '{trigger_event}'")
            raise

    async def _process_single_rule(self, db: AsyncSession, rule: EmailAutomationRule, context: Dict[str, Any]):
        """Process a single automation rule"""
        logger.info(f"Processing rule: {rule.template_key} for trigger: {rule.trigger_event}")

        # Get recipients based on condition query
        recipients = await self._get_recipients(db, rule, context)
        if not recipients:
            logger.warning(
                f"No recipients found for rule {rule.template_key} — skipping send. "
                f"Check advisor_email is set in user_profiles for this application."
            )
            return

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

            except Exception:
                logger.exception(f"Failed to schedule email to {recipient.get('email', 'unknown')}")

    async def _get_recipients(
        self, db: AsyncSession, rule: EmailAutomationRule, context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Resolve email recipients from the rule's admin-configured condition query.

        SECURITY (#1223 A): ``condition_query`` is free-form SQL stored in the
        database and previously executed verbatim. It is now re-validated HERE, not
        only when an admin saves it — seeds, Alembic migrations, direct DB writes and
        the ``PATCH /{id}/toggle`` endpoint all bypass the write-time validator — and
        executed inside a SAVEPOINT that is always rolled back with
        ``transaction_read_only`` set. A rule therefore cannot write, and a broken
        rule cannot poison the caller's transaction.

        Failures RAISE rather than returning []: ``process_trigger`` already isolates
        each rule in its own try/except, so raising surfaces the misconfiguration in
        the logs without stopping the other rules or the surrounding business
        transaction. Returning [] silently turned a broken rule into "nobody was
        supposed to be notified".
        """
        if not rule.condition_query:
            logger.warning(f"⚠️  No condition_query defined for rule {rule.template_key}")
            return []

        # Validate BEFORE any database work, so an unsafe rule never reaches the DB.
        try:
            assert_read_only_select(rule.condition_query)
            parameterized_query = bind_placeholders(rule.condition_query, context)
        except UnsafeConditionQueryError:
            logger.exception(
                f"❌ Refusing to run unsafe condition_query for rule {rule.template_key}",
            )
            raise

        logger.info(f"📧 Executing recipient query for {rule.template_key}")
        logger.debug(f"   Query template: {parameterized_query[:200]}")

        rows = await self._execute_read_only(db, parameterized_query, context)

        recipients = [{"email": row[0]} for row in rows if row]
        logger.info(f"✓ Found {len(recipients)} recipients for rule {rule.template_key}")
        return recipients

    async def _execute_read_only(self, db: AsyncSession, sql: str, params: Dict[str, Any]) -> List[Any]:
        """Run *sql* inside a SAVEPOINT that is ALWAYS rolled back.

        Two reasons the savepoint is rolled back rather than released:
        ``RELEASE SAVEPOINT`` does not revert ``SET LOCAL``, so releasing would leave
        the whole outer transaction read-only and the caller's later
        ``scheduled_emails`` INSERT would fail; and rolling back guarantees a
        misbehaving query leaves no trace in the caller's transaction.

        A savepoint (rather than a separate connection) keeps read-your-own-writes
        semantics, so a future caller that triggers before committing still resolves
        the rows it just wrote.

        ``nested`` is initialised to None and checked in ``finally`` because
        ``begin_nested()`` performs an implicit flush that can itself raise — without
        the null guard that failure would skip the rollback and leave the session in
        PendingRollbackError, which is exactly the transaction-abort bug this method
        exists to fix.
        """
        nested = None
        try:
            nested = await db.begin_nested()
            if _dialect_name(db) == "postgresql":
                # statement_timeout caps a pathological query; transaction_read_only
                # blocks writes. Neither stops pg_read_file — that is what the
                # identifier deny-list in sql_read_only_guard is for.
                await db.execute(text(f"SET LOCAL statement_timeout = '{RECIPIENT_QUERY_TIMEOUT_MS}ms'"))
                await db.execute(text("SET LOCAL transaction_read_only = ON"))
            result = await db.execute(text(sql), params)
            return list(result.fetchall())
        finally:
            if nested is not None:
                await nested.rollback()

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

        except Exception:
            logger.exception("❌ Failed to send automated email")
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

                except Exception:
                    logger.exception("❌ Failed to render email via frontend")
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

        except Exception:
            logger.exception("Failed to schedule automated email")
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
            "college_ranking_submitted": EmailCategory.review_college,
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
            "college_ranking_submitted": "college-ranking-submitted",
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

    async def trigger_college_ranking_submitted(self, db: AsyncSession, ranking_data: Dict[str, Any]):
        """Trigger emails when a college submits (finalizes) its ranking.

        Unlike the other triggers this one is ranking-scoped, not
        application-scoped: one mail per finalized ranking, addressed to the
        reviewers of the college that owns it. ``college_code`` is therefore the
        key the rule's condition_query binds against — it is passed through even
        when None so that a global (admin) ranking resolves to no recipients
        rather than raising on an unknown placeholder.
        """
        from app.core.config import settings

        scholarship_type_value = ranking_data.get("scholarship_type", "")
        context = {
            "ranking_id": ranking_data.get("ranking_id"),
            "college_code": ranking_data.get("college_code"),
            "college_name": ranking_data.get("college_name", ""),
            "ranking_name": ranking_data.get("ranking_name", ""),
            "scholarship_type": scholarship_type_value,
            "scholarship_name": scholarship_type_value,  # Alias for templates
            "scholarship_type_id": ranking_data.get("scholarship_type_id"),
            "sub_type_code": ranking_data.get("sub_type_code", ""),
            "academic_year": ranking_data.get("academic_year", ""),
            "semester": ranking_data.get("semester", ""),
            "total_applications": ranking_data.get("total_applications", ""),
            "finalized_by": ranking_data.get("finalized_by", ""),
            "finalized_at": ranking_data.get("finalized_at", datetime.now().strftime("%Y-%m-%d %H:%M")),
            "system_url": settings.frontend_url,
        }

        logger.info(
            "🚀 EMAIL AUTOMATION TRIGGERED: college_review_submitted (ranking %s, college %s)",
            context["ranking_id"],
            context["college_code"],
        )
        await self.process_trigger(db, "college_review_submitted", context)

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
            query = text("""
                SELECT id, recipient_email, subject, body, html_body, cc_emails, bcc_emails, template_key,
                       email_category, application_id, scholarship_type_id, priority
                FROM scheduled_emails
                WHERE status = 'pending'
                AND scheduled_for <= NOW()
                AND (requires_approval = false OR approved_by_user_id IS NOT NULL)
                ORDER BY priority ASC, scheduled_for ASC
                LIMIT 50
            """)

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
                    update_query = text("""
                        UPDATE scheduled_emails
                        SET status = 'sent', updated_at = NOW()
                        WHERE id = :email_id
                    """)
                    await db.execute(update_query, {"email_id": email_row.id})

                except Exception as e:
                    logger.exception(f"Failed to send scheduled email {email_row.id}")

                    # Mark as failed
                    fail_query = text("""
                        UPDATE scheduled_emails
                        SET status = 'failed', last_error = :error, retry_count = retry_count + 1, updated_at = NOW()
                        WHERE id = :email_id
                    """)
                    await db.execute(fail_query, {"email_id": email_row.id, "error": str(e)})

            await db.commit()
            logger.info(f"✓ Completed processing {len(scheduled_emails)} scheduled emails")

        except Exception:
            logger.exception("Failed to process scheduled emails")
            await db.rollback()
            raise


# Singleton instance
email_automation_service = EmailAutomationService()
