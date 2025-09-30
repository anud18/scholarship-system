import json
import logging
from datetime import datetime
from email.message import EmailMessage
from typing import List, Optional

import aiosmtplib
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dynamic_config import dynamic_config
from app.models.email_management import EmailCategory, EmailHistory, EmailStatus, ScheduledEmail
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

    async def send_email(
        self,
        to: str | List[str],
        subject: str,
        body: str,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        db: Optional[AsyncSession] = None,
        **metadata,
    ):
        """
        Send email with optional history logging

        Args:
            to: Recipient email(s)
            subject: Email subject
            body: Email body
            cc: CC recipients
            bcc: BCC recipients
            db: Database session for logging
            **metadata: Additional metadata for logging (template_key, application_id, etc.)
        """
        # Load configuration before sending (picks up any changes from database)
        if db:
            self.db = db
        await self._load_config()

        if isinstance(to, str):
            to = [to]

        primary_recipient = to[0] if to else ""
        status = EmailStatus.SENT
        error_message = None

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
            msg.set_content(body)

            # Calculate email size
            email_size = len(msg.as_string().encode("utf-8"))

            await aiosmtplib.send(
                msg,
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                start_tls=True,
            )

            logger.info(f"Email sent successfully to {primary_recipient}")

        except Exception as e:
            status = EmailStatus.FAILED
            error_message = str(e)
            logger.error(f"Failed to send email to {primary_recipient}: {e}")
            # Re-raise the exception so callers can handle it
            raise

        finally:
            # Log email history if database session provided
            if db:
                try:
                    await self._log_email_history(
                        db=db,
                        recipient_email=primary_recipient,
                        cc_emails=cc,
                        bcc_emails=bcc,
                        subject=subject,
                        body=body,
                        status=status,
                        error_message=error_message,
                        email_size_bytes=email_size if status == EmailStatus.SENT else None,
                        **metadata,
                    )
                except Exception as log_error:
                    logger.error(f"Failed to log email history: {log_error}")

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
        """Log email to history table"""
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

            db.add(history)
            await db.commit()
            logger.debug(f"Email history logged for {recipient_email}")

        except Exception as e:
            logger.error(f"Failed to log email history: {e}")
            await db.rollback()

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
            "email_category": EmailCategory.APPLICATION_STUDENT,
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
            "email_category": EmailCategory.RECOMMENDATION_PROFESSOR,
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
            "email_category": EmailCategory.REVIEW_COLLEGE,
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
            "email_category": EmailCategory.APPLICATION_WHITELIST,
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
            "email_category": EmailCategory.APPLICATION_STUDENT,
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
            "email_category": EmailCategory.SUPPLEMENT_STUDENT,
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
            email_category=EmailCategory.RESULT_STUDENT,
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
                email_category=EmailCategory.RESULT_PROFESSOR,
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
                email_category=EmailCategory.RESULT_COLLEGE,
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
            "email_category": EmailCategory.ROSTER_STUDENT,
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
