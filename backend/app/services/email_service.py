import json
import logging
import re
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from html import unescape
from typing import List, Optional

import aiosmtplib
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dynamic_config import dynamic_config
from app.models.email_management import EmailCategory, EmailHistory, EmailStatus, EmailTestModeAudit, ScheduledEmail
from app.services.system_setting_service import EmailTemplateService

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self, db: Optional[AsyncSession] = None):
        """
        Initialize Email Service.

        Args:
            db: Database session for loading dynamic configuration.
                If provided, will use database settings; otherwise falls back to environment variables.
        """
        self.db = db
        self._config_loaded = False
        self.host = None
        self.port = None
        self.username = None
        self.password = None
        self.from_addr = None
        self.from_name = None

    async def _load_config(self):
        """Load email configuration from database or environment variables"""
        if self.db and not self._config_loaded:
            # Load from database with dynamic config
            self.host = await dynamic_config.get_str("smtp_host", self.db, settings.smtp_host)
            self.port = await dynamic_config.get_int("smtp_port", self.db, settings.smtp_port)
            self.username = await dynamic_config.get_str("smtp_user", self.db, settings.smtp_user)
            self.password = await dynamic_config.get_str("smtp_password", self.db, settings.smtp_password)
            self.from_addr = await dynamic_config.get_str("email_from", self.db, settings.email_from)
            self.from_name = await dynamic_config.get_str("email_from_name", self.db, settings.email_from_name)
            self._config_loaded = True
            logger.info("Email configuration loaded from database")
        elif not self.db:
            # Fall back to environment variables
            self.host = settings.smtp_host
            self.port = settings.smtp_port
            self.username = settings.smtp_user
            self.password = settings.smtp_password
            self.from_addr = settings.email_from
            self.from_name = settings.email_from_name

    @staticmethod
    def _html_to_text(html_content: str) -> str:
        """Convert HTML content into a simple plain-text representation"""
        # Remove script/style blocks first to avoid leaking JS/CSS into the body
        sanitized = re.sub(r"<(script|style)[^>]*>.*?</\\1>", "", html_content, flags=re.IGNORECASE | re.DOTALL)
        # Strip remaining tags and collapse whitespace
        sanitized = re.sub(r"<[^>]+>", " ", sanitized)
        sanitized = re.sub(r"\s+", " ", sanitized)
        return unescape(sanitized).strip()

    async def _check_test_mode(self) -> tuple[bool, dict]:
        """
        Check if email test mode is enabled and not expired

        Returns:
            tuple: (is_enabled, config_dict)
        """
        if not self.db:
            return False, {}

        try:
            # Get test mode configuration with row-level locking to prevent race conditions
            from sqlalchemy import select

            from app.models.system_setting import SystemSetting

            # Use SELECT FOR UPDATE to lock the row while checking/updating
            stmt = select(SystemSetting).where(SystemSetting.key == "email_test_mode").with_for_update()
            result = await self.db.execute(stmt)
            config_row = result.scalar_one_or_none()

            if not config_row:
                return False, {}

            # Parse JSON value
            test_mode_config = json.loads(config_row.value) if isinstance(config_row.value, str) else config_row.value

            enabled = test_mode_config.get("enabled", False)
            expires_at_str = test_mode_config.get("expires_at")

            # Check if expired (with row locked, only one request will update)
            if enabled and expires_at_str:
                expires_at = datetime.fromisoformat(expires_at_str)
                if datetime.now(timezone.utc) > expires_at:
                    # Auto-disable if expired
                    test_mode_config["enabled"] = False

                    # Log expiration event
                    audit_log = EmailTestModeAudit.log_expired(test_mode_config)
                    self.db.add(audit_log)

                    # Update configuration
                    config_row.value = json.dumps(test_mode_config)
                    await self.db.commit()
                    enabled = False

            return enabled, test_mode_config

        except Exception as e:
            logger.error(f"Error checking test mode: {e}")
            return False, {}

    def _transform_recipients_for_test(
        self,
        original_to: List[str],
        test_emails: List[str],
        original_cc: Optional[List[str]] = None,
        original_bcc: Optional[List[str]] = None,
    ) -> dict:
        """
        Transform recipients for test mode (supports multiple test emails)

        Args:
            original_to: Original TO recipients
            test_emails: List of test email addresses to redirect to
            original_cc: Original CC recipients
            original_bcc: Original BCC recipients

        Returns:
            dict with transformed recipients and originals
        """
        return {
            "to": test_emails,  # All emails go to test addresses
            "cc": [],  # Clear CC in test mode
            "bcc": [],  # Clear BCC in test mode
            "original_to": original_to,
            "original_cc": original_cc or [],
            "original_bcc": original_bcc or [],
        }

    def _add_test_headers(self, msg: EmailMessage, original_recipients: dict, session_id: str):
        """Add test mode headers to email"""
        msg["X-Test-Mode"] = "true"
        msg["X-Test-Session-ID"] = session_id
        msg["X-Original-To"] = ", ".join(original_recipients.get("original_to", []))
        if original_recipients.get("original_cc"):
            msg["X-Original-CC"] = ", ".join(original_recipients["original_cc"])
        if original_recipients.get("original_bcc"):
            msg["X-Original-BCC"] = ", ".join(original_recipients["original_bcc"])

    def _add_test_banner_to_body(
        self, body: str, html_content: Optional[str], original_recipients: dict
    ) -> tuple[str, Optional[str]]:
        """Add test mode banner to email body"""

        # Create banner text
        banner_text = f"""
⚠️ 郵件測試模式 ⚠️
原收件人: {", ".join(original_recipients.get("original_to", []))}
"""
        if original_recipients.get("original_cc"):
            banner_text += f"原副本: {', '.join(original_recipients['original_cc'])}\n"
        if original_recipients.get("original_bcc"):
            banner_text += f"原密件副本: {', '.join(original_recipients['original_bcc'])}\n"

        banner_text += "此郵件為測試郵件，實際不會寄送給上述收件人。\n"
        banner_text += "=" * 60 + "\n\n"

        # Add to plain text body
        new_body = banner_text + body if body else banner_text

        # Add to HTML body if exists
        new_html = None
        if html_content:
            original_cc_html = (
                f'<p style="margin: 5px 0;"><strong>原副本:</strong> {", ".join(original_recipients["original_cc"])}</p>'
                if original_recipients.get("original_cc")
                else ""
            )
            original_bcc_html = (
                f'<p style="margin: 5px 0;"><strong>原密件副本:</strong> {", ".join(original_recipients["original_bcc"])}</p>'
                if original_recipients.get("original_bcc")
                else ""
            )

            html_banner = f"""
            <div style="background-color: #fff3cd; border: 2px solid #ffc107; padding: 15px; margin-bottom: 20px; border-radius: 5px;">
                <h3 style="color: #856404; margin-top: 0;">⚠️ 郵件測試模式 ⚠️</h3>
                <p style="margin: 5px 0;"><strong>原收件人:</strong> {", ".join(original_recipients.get("original_to", []))}</p>
                {original_cc_html}
                {original_bcc_html}
                <p style="margin: 10px 0 0 0; color: #856404;">此郵件為測試郵件，實際不會寄送給上述收件人。</p>
            </div>
            """
            new_html = html_banner + html_content

        return new_body, new_html

    async def _log_test_mode_interception(
        self, original_recipient: str, test_recipient: str, subject: str, session_id: str, user_id: Optional[int] = None
    ):
        """Log email interception in test mode"""
        if not self.db:
            return

        try:
            audit_log = EmailTestModeAudit.log_email_intercepted(
                original_recipient=original_recipient,
                actual_recipient=test_recipient,
                email_subject=subject,
                session_id=session_id,
                user_id=user_id,
            )
            self.db.add(audit_log)
            await self.db.commit()
        except Exception as e:
            logger.error(f"Failed to log test mode interception: {e}")

    async def send_email(
        self,
        to: str | List[str],
        subject: str,
        body: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        db: Optional[AsyncSession] = None,
        html_content: Optional[str] = None,
        **metadata,
    ):
        """
        Send email with optional history logging

        Args:
            to: Recipient email(s)
            subject: Email subject
            body: Plain-text email body (optional if html_content is provided)
            cc: CC recipients
            bcc: BCC recipients
            db: Database session for logging
            html_content: HTML version of the email body
            **metadata: Additional metadata for logging (template_key, application_id, etc.)
        """
        # Load configuration before sending (picks up any changes from database)
        if db:
            self.db = db
        await self._load_config()

        if body is None and html_content is None:
            raise ValueError("Either body or html_content must be provided when sending an email")

        if isinstance(to, str):
            to = [to]

        # Check test mode
        is_test_mode, test_config = await self._check_test_mode()
        test_session_id = str(uuid.uuid4()) if is_test_mode else None

        # Store original recipients
        original_to = to.copy()
        original_cc = cc.copy() if cc else None
        original_bcc = bcc.copy() if bcc else None

        # Transform recipients if in test mode
        if is_test_mode:
            # Get test emails (support both new array format and old string format for backward compatibility)
            test_emails = test_config.get("redirect_emails", [])

            # Backward compatibility: convert old redirect_email to list
            if not test_emails and "redirect_email" in test_config:
                old_email = test_config.get("redirect_email")
                test_emails = [old_email] if old_email else []

            if not test_emails:
                error_msg = "Test mode enabled but no redirect_emails configured"
                logger.error(error_msg)
                raise ValueError(error_msg)
            else:
                recipient_info = self._transform_recipients_for_test(to, test_emails, cc, bcc)
                to = recipient_info["to"]
                cc = recipient_info["cc"]
                bcc = recipient_info["bcc"]
                subject = f"[TEST] {subject}"

                # Add test banner to body
                plain_body_for_test = body or (self._html_to_text(html_content) if html_content else "")
                body, html_content = self._add_test_banner_to_body(plain_body_for_test, html_content, recipient_info)

                logger.info(
                    f"Test mode: Redirecting email from {', '.join(original_to)} to {', '.join(test_emails)} (session: {test_session_id})"
                )

        primary_recipient = to[0] if to else ""
        status = EmailStatus.sent
        error_message = None
        email_size = None
        plain_body = body or (self._html_to_text(html_content) if html_content else "")
        history_body = html_content or body or ""

        try:
            msg = EmailMessage()
            # Use from_name if available
            if self.from_name:
                msg["From"] = f"{self.from_name} <{self.from_addr}>"
            else:
                msg["From"] = self.from_addr
            msg["To"] = ", ".join(to)
            msg["Subject"] = subject
            if cc:
                msg["Cc"] = ", ".join(cc)
            if bcc:
                msg["Bcc"] = ", ".join(bcc)

            # Add test mode headers if enabled
            if is_test_mode:
                self._add_test_headers(
                    msg,
                    {
                        "original_to": original_to,
                        "original_cc": original_cc,
                        "original_bcc": original_bcc,
                    },
                    test_session_id,
                )

            msg.set_content(plain_body)
            if html_content:
                msg.add_alternative(html_content, subtype="html")

            # Calculate email size
            email_size = len(msg.as_string().encode("utf-8"))

            # Get TLS configuration from database (default: False for plain SMTP like port 25)
            use_tls = await dynamic_config.get_bool("smtp_use_tls", self.db, False)

            await aiosmtplib.send(
                msg,
                hostname=self.host,
                port=self.port,
                username=self.username if self.username else None,
                password=self.password if self.password else None,
                start_tls=use_tls,
            )

            logger.info("Email sent successfully to %s", primary_recipient)

            # Log test mode interception
            if is_test_mode:
                for original_recipient in original_to:
                    await self._log_test_mode_interception(
                        original_recipient=original_recipient,
                        test_recipient=primary_recipient,
                        subject=subject,
                        session_id=test_session_id,
                        user_id=metadata.get("sent_by_user_id"),
                    )

        except Exception as e:
            status = EmailStatus.failed
            error_message = str(e)
            logger.error("Failed to send email to %s: %s", primary_recipient, e)
            # Re-raise the exception so callers can handle it
            raise

        finally:
            # Log email history if database session provided
            if db:
                try:
                    # Log with original recipients for history tracking
                    await self._log_email_history(
                        db=db,
                        recipient_email=original_to[0] if original_to else primary_recipient,
                        cc_emails=original_cc,
                        bcc_emails=original_bcc,
                        subject=subject,
                        body=history_body,
                        status=status,
                        error_message=error_message,
                        email_size_bytes=email_size if status == EmailStatus.sent else None,
                        **metadata,
                    )
                except Exception as log_error:
                    logger.error("Failed to log email history: %s", log_error)

    async def _log_email_history(
        self,
        db: AsyncSession,
        recipient_email: str,
        subject: str,
        body: str,
        status: EmailStatus,
        cc_emails: Optional[List[str]] = None,
        bcc_emails: Optional[List[str]] = None,
        error_message: Optional[str] = None,
        email_size_bytes: Optional[int] = None,
        **metadata,
    ):
        """
        Log email to history table using a separate database session.
        This prevents audit logging failures from affecting the main email transaction.
        """
        # Create a new session for audit logging to avoid transaction interference
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as audit_db:
            try:
                history = EmailHistory(
                    recipient_email=recipient_email,
                    cc_emails=json.dumps(cc_emails) if cc_emails else None,
                    bcc_emails=json.dumps(bcc_emails) if bcc_emails else None,
                    subject=subject,
                    body=body,
                    template_key=metadata.get("template_key"),
                    email_category=metadata.get("email_category"),
                    application_id=metadata.get("application_id"),
                    scholarship_type_id=metadata.get("scholarship_type_id"),
                    sent_by_user_id=metadata.get("sent_by_user_id"),
                    sent_by_system=metadata.get("sent_by_system", True),
                    status=status,
                    error_message=error_message,
                    email_size_bytes=email_size_bytes,
                    retry_count=metadata.get("retry_count", 0),
                )

                audit_db.add(history)
                await audit_db.commit()
                logger.debug(f"Email history logged for {recipient_email}")

            except Exception as e:
                logger.error("Failed to log email history: %s", e)
                await audit_db.rollback()
                # Don't re-raise - audit logging failure shouldn't break email sending

    async def send_with_template(
        self,
        db: AsyncSession,
        key: str,
        to: str | List[str],
        context: dict,
        default_subject: str,
        default_body: str,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        **metadata,
    ):
        """Send email using template with history logging"""
        template = await EmailTemplateService.get_template(db, key)
        subject = (template.subject_template if template else default_subject).format(**context)
        body = (template.body_template if template else default_body).format(**context)
        cc_list = cc
        bcc_list = bcc
        if template:
            if template.cc:
                cc_list = [x.strip() for x in template.cc.split(",") if x.strip()]
            if template.bcc:
                bcc_list = [x.strip() for x in template.bcc.split(",") if x.strip()]

        # Add template key to metadata for logging
        metadata["template_key"] = key

        await self.send_email(to, subject, body, cc=cc_list, bcc=bcc_list, db=db, **metadata)

    async def schedule_email(
        self,
        db: AsyncSession,
        to: str,
        subject: str,
        body: str,
        scheduled_for: datetime,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        requires_approval: bool = False,
        priority: int = 5,
        **metadata,
    ) -> ScheduledEmail:
        """
        Schedule an email to be sent later

        Args:
            db: Database session
            to: Recipient email
            subject: Email subject
            body: Email body
            scheduled_for: When to send the email
            cc: CC recipients
            bcc: BCC recipients
            requires_approval: Whether email needs approval before sending
            priority: Priority level (1-10, 1 being highest)
            **metadata: Additional metadata (template_key, application_id, etc.)
        """
        scheduled_email = ScheduledEmail(
            recipient_email=to,
            cc_emails=json.dumps(cc) if cc else None,
            bcc_emails=json.dumps(bcc) if bcc else None,
            subject=subject,
            body=body,
            template_key=metadata.get("template_key"),
            email_category=metadata.get("email_category"),
            scheduled_for=scheduled_for,
            application_id=metadata.get("application_id"),
            scholarship_type_id=metadata.get("scholarship_type_id"),
            requires_approval=requires_approval,
            created_by_user_id=metadata.get("created_by_user_id"),
            priority=priority,
        )

        db.add(scheduled_email)
        await db.commit()
        await db.refresh(scheduled_email)

        logger.info(f"Email scheduled for {scheduled_for} to {to}")
        return scheduled_email

    async def schedule_with_template(
        self,
        db: AsyncSession,
        key: str,
        to: str,
        context: dict,
        default_subject: str,
        default_body: str,
        scheduled_for: datetime,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        requires_approval: bool = False,
        priority: int = 5,
        **metadata,
    ) -> ScheduledEmail:
        """Schedule an email using template"""
        template = await EmailTemplateService.get_template(db, key)
        subject = (template.subject_template if template else default_subject).format(**context)
        body = (template.body_template if template else default_body).format(**context)
        cc_list = cc
        bcc_list = bcc
        if template:
            if template.cc:
                cc_list = [x.strip() for x in template.cc.split(",") if x.strip()]
            if template.bcc:
                bcc_list = [x.strip() for x in template.bcc.split(",") if x.strip()]

        # Add template key to metadata
        metadata["template_key"] = key

        return await self.schedule_email(
            db=db,
            to=to,
            subject=subject,
            body=body,
            scheduled_for=scheduled_for,
            cc=cc_list,
            bcc=bcc_list,
            requires_approval=requires_approval,
            priority=priority,
            **metadata,
        )

    # New standardized email methods using the redesigned template system

    async def send_application_submitted_notification(self, db: AsyncSession, application_data: dict):
        """Send notification to student when application is submitted"""
        context = {
            "app_id": application_data.get("app_id", ""),
            "student_name": application_data.get("student_name", ""),
            "scholarship_type": application_data.get("scholarship_type", ""),
            "submit_date": application_data.get("submit_date", ""),
            "professor_name": application_data.get("professor_name", ""),
            "system_url": "https://scholarship.nycu.edu.tw",
        }

        default_subject = (
            f"申請已成功送出 - {application_data.get('scholarship_type', '')} ({application_data.get('app_id', '')})"
        )
        default_body = f"您的獎學金申請({application_data.get('app_id', '')})已成功送出，請等候後續通知。"

        metadata = {
            "email_category": EmailCategory.application_student,
            "application_id": application_data.get("id"),
            "scholarship_type_id": application_data.get("scholarship_type_id"),
            "sent_by_system": True,
        }

        await self.send_with_template(
            db,
            "application_submitted_student",
            application_data.get("student_email", ""),
            context,
            default_subject,
            default_body,
            **metadata,
        )

    async def send_professor_review_notification(self, db: AsyncSession, application_data: dict):
        """Send notification to professor when new application needs review"""
        context = {
            "app_id": application_data.get("app_id", ""),
            "professor_name": application_data.get("professor_name", ""),
            "student_name": application_data.get("student_name", ""),
            "scholarship_type": application_data.get("scholarship_type", ""),
            "submit_date": application_data.get("submit_date", ""),
            "system_url": "https://scholarship.nycu.edu.tw",
        }

        default_subject = (
            f"新學生申請待推薦 - {application_data.get('scholarship_type', '')} ({application_data.get('app_id', '')})"
        )
        default_body = f"有一份新的學生申請案({application_data.get('app_id', '')})需要您推薦，請至系統審查。"

        metadata = {
            "email_category": EmailCategory.recommendation_professor,
            "application_id": application_data.get("id"),
            "scholarship_type_id": application_data.get("scholarship_type_id"),
            "sent_by_system": True,
        }

        await self.send_with_template(
            db,
            "application_notify_professor",
            application_data.get("professor_email", ""),
            context,
            default_subject,
            default_body,
            **metadata,
        )

    async def send_college_review_notification(self, db: AsyncSession, application_data: dict):
        """Send notification to college when application needs review"""
        context = {
            "app_id": application_data.get("app_id", ""),
            "student_name": application_data.get("student_name", ""),
            "scholarship_type": application_data.get("scholarship_type", ""),
            "professor_name": application_data.get("professor_name", ""),
            "submit_date": application_data.get("submit_date", ""),
            "professor_recommendation": application_data.get("professor_recommendation", ""),
            "college_name": application_data.get("college_name", ""),
            "review_deadline": application_data.get("review_deadline", ""),
            "system_url": "https://scholarship.nycu.edu.tw",
        }

        default_subject = (
            f"新申請案待審核 - {application_data.get('scholarship_type', '')} ({application_data.get('app_id', '')})"
        )
        default_body = f"有一份新的申請案({application_data.get('app_id', '')})已由教授推薦，請至系統審查。"

        metadata = {
            "email_category": EmailCategory.review_college,
            "application_id": application_data.get("id"),
            "scholarship_type_id": application_data.get("scholarship_type_id"),
            "sent_by_system": True,
        }

        # Send to college reviewers (can be multiple recipients)
        college_emails = application_data.get("college_emails", ["mock_college@nycu.edu.tw"])
        for email in college_emails:
            await self.send_with_template(
                db,
                "college_review_notification",
                email,
                context,
                default_subject,
                default_body,
                **metadata,
            )

    async def send_whitelist_notification(self, db: AsyncSession, scholarship_data: dict, student_emails: list):
        """Send whitelist notification to eligible students"""
        context = {
            "scholarship_type": scholarship_data.get("scholarship_type", ""),
            "academic_year": scholarship_data.get("academic_year", ""),
            "semester": scholarship_data.get("semester", ""),
            "application_period": scholarship_data.get("application_period", ""),
            "deadline": scholarship_data.get("deadline", ""),
            "eligibility_requirements": scholarship_data.get("eligibility_requirements", ""),
            "system_url": "https://scholarship.nycu.edu.tw",
        }

        default_subject = f"獎學金申請開放通知 - {scholarship_data.get('scholarship_type', '')} ({scholarship_data.get('academic_year', '')}學年度{scholarship_data.get('semester', '')}學期)"
        default_body = f"{scholarship_data.get('scholarship_type', '')} 現已開放申請，請至系統進行線上申請。"

        metadata = {
            "email_category": EmailCategory.application_whitelist,
            "scholarship_type_id": scholarship_data.get("scholarship_type_id"),
            "sent_by_system": True,
        }

        # Send BCC to all students, CC to admin
        await self.send_with_template(
            db,
            "whitelist_notification",
            student_emails[0] if student_emails else "noreply@nycu.edu.tw",
            context,
            default_subject,
            default_body,
            cc=["admin@nycu.edu.tw"],
            bcc=student_emails,
            **metadata,
        )

    async def send_deadline_reminder(self, db: AsyncSession, application_data: dict):
        """Send deadline reminder to students with draft applications"""
        context = {
            "student_name": application_data.get("student_name", ""),
            "scholarship_type": application_data.get("scholarship_type", ""),
            "deadline": application_data.get("deadline", ""),
            "system_url": "https://scholarship.nycu.edu.tw",
        }

        default_subject = f"申請截止提醒 - {application_data.get('scholarship_type', '')} (剩餘 3 天)"
        default_body = "您的獎學金申請草稿尚未送出，申請即將截止！請儘快完成申請。"

        metadata = {
            "email_category": EmailCategory.application_student,
            "application_id": application_data.get("id"),
            "scholarship_type_id": application_data.get("scholarship_type_id"),
            "sent_by_system": True,
        }

        await self.send_with_template(
            db,
            "deadline_reminder_draft",
            application_data.get("student_email", ""),
            context,
            default_subject,
            default_body,
            **metadata,
        )

    async def send_supplement_request(self, db: AsyncSession, application_data: dict, supplement_data: dict):
        """Send supplement request to student"""
        context = {
            "student_name": application_data.get("student_name", ""),
            "app_id": application_data.get("app_id", ""),
            "scholarship_type": application_data.get("scholarship_type", ""),
            "supplement_items": supplement_data.get("supplement_items", ""),
            "supplement_notes": supplement_data.get("supplement_notes", ""),
            "supplement_deadline": supplement_data.get("supplement_deadline", ""),
            "system_url": "https://scholarship.nycu.edu.tw",
        }

        default_subject = (
            f"補件通知 - {application_data.get('scholarship_type', '')} ({application_data.get('app_id', '')})"
        )
        default_body = f"您的獎學金申請({application_data.get('app_id', '')})需要補充資料，請儘快補齊。"

        metadata = {
            "email_category": EmailCategory.supplement_student,
            "application_id": application_data.get("id"),
            "scholarship_type_id": application_data.get("scholarship_type_id"),
            "sent_by_system": False,  # Manual supplement requests
        }

        await self.send_with_template(
            db,
            "supplement_request",
            application_data.get("student_email", ""),
            context,
            default_subject,
            default_body,
            **metadata,
        )

    async def send_result_notifications(self, db: AsyncSession, application_data: dict, result_data: dict):
        """Send result notifications to student, professor, and college"""
        base_context = {
            "app_id": application_data.get("app_id", ""),
            "student_name": application_data.get("student_name", ""),
            "professor_name": application_data.get("professor_name", ""),
            "college_name": application_data.get("college_name", ""),
            "scholarship_type": application_data.get("scholarship_type", ""),
            "result_status": result_data.get("result_status", ""),
            "approved_amount": result_data.get("approved_amount", ""),
            "result_message": result_data.get("result_message", ""),
            "next_steps": result_data.get("next_steps", ""),
        }

        base_metadata = {
            "application_id": application_data.get("id"),
            "scholarship_type_id": application_data.get("scholarship_type_id"),
            "sent_by_system": True,
        }

        # Send to student
        await self.send_with_template(
            db,
            "result_notification_student",
            application_data.get("student_email", ""),
            base_context,
            f"獎學金審核結果通知 - {base_context['scholarship_type']} ({base_context['app_id']})",
            f"您的獎學金申請審核結果已出爐：{base_context['result_status']}",
            email_category=EmailCategory.result_student,
            **base_metadata,
        )

        # Send to professor
        if application_data.get("professor_email"):
            await self.send_with_template(
                db,
                "result_notification_professor",
                application_data.get("professor_email", ""),
                base_context,
                f"學生獎學金審核結果 - {base_context['scholarship_type']} ({base_context['app_id']})",
                f"您推薦的學生({base_context['student_name']})獎學金申請結果：{base_context['result_status']}",
                email_category=EmailCategory.result_professor,
                **base_metadata,
            )

        # Send to college
        college_emails = application_data.get("college_emails", ["mock_college@nycu.edu.tw"])
        for email in college_emails:
            await self.send_with_template(
                db,
                "result_notification_college",
                email,
                base_context,
                f"獎學金審核結果確認 - {base_context['scholarship_type']} ({base_context['app_id']})",
                f"獎學金申請({base_context['app_id']})審核程序已完成，結果：{base_context['result_status']}",
                email_category=EmailCategory.result_college,
                **base_metadata,
            )

    async def send_roster_notification(self, db: AsyncSession, application_data: dict, roster_data: dict):
        """Send roster notification to awarded students"""
        context = {
            "student_name": application_data.get("student_name", ""),
            "scholarship_type": application_data.get("scholarship_type", ""),
            "academic_year": roster_data.get("academic_year", ""),
            "semester": roster_data.get("semester", ""),
            "approved_amount": roster_data.get("approved_amount", ""),
            "roster_number": roster_data.get("roster_number", ""),
            "follow_up_items": roster_data.get("follow_up_items", ""),
        }

        default_subject = f"獲獎名冊確認通知 - {application_data.get('scholarship_type', '')} ({roster_data.get('academic_year', '')}學年度{roster_data.get('semester', '')}學期)"
        default_body = f"恭喜您獲得 {application_data.get('scholarship_type', '')}！"

        metadata = {
            "email_category": EmailCategory.roster_student,
            "application_id": application_data.get("id"),
            "scholarship_type_id": application_data.get("scholarship_type_id"),
            "sent_by_system": False,  # Manual roster notifications
        }

        await self.send_with_template(
            db,
            "roster_notification",
            application_data.get("student_email", ""),
            context,
            default_subject,
            default_body,
            **metadata,
        )

    # Legacy methods - kept for backward compatibility but deprecated
    async def send_to_college_reviewers(self, application, db: Optional[AsyncSession] = None):
        """DEPRECATED: Use send_college_review_notification instead"""
        if db:
            application_data = {
                "id": getattr(application, "id", None),
                "app_id": application.app_id,
                "student_name": getattr(application, "student_name", ""),
                "scholarship_type": getattr(application, "scholarship_type", ""),
                "submit_date": application.submitted_at.strftime("%Y-%m-%d")
                if getattr(application, "submitted_at", None)
                else "",
                "professor_name": getattr(application, "professor_name", ""),
                "professor_recommendation": "",
                "college_name": getattr(application, "college_name", ""),
                "review_deadline": getattr(application, "review_deadline", ""),
                "scholarship_type_id": getattr(application, "scholarship_type_id", None),
                "college_emails": ["mock_college@nycu.edu.tw"],
            }
            await self.send_college_review_notification(db, application_data)

    async def send_to_professor(self, application, db: Optional[AsyncSession] = None):
        """DEPRECATED: Use send_professor_review_notification instead"""
        if db:
            professor = getattr(application, "professor", None)
            application_data = {
                "id": getattr(application, "id", None),
                "app_id": application.app_id,
                "student_name": getattr(application, "student_name", ""),
                "scholarship_type": getattr(application, "scholarship_type", ""),
                "submit_date": application.submitted_at.strftime("%Y-%m-%d")
                if getattr(application, "submitted_at", None)
                else "",
                "professor_name": getattr(professor, "name", "") if professor else "",
                "professor_email": getattr(professor, "email", "") if professor else "",
                "scholarship_type_id": getattr(application, "scholarship_type_id", None),
            }
            if application_data["professor_email"]:
                await self.send_professor_review_notification(db, application_data)
