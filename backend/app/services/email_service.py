from app.core.config import settings
import aiosmtplib
from email.message import EmailMessage
from typing import List, Optional
from datetime import datetime, timezone
import json
import logging
from app.services.system_setting_service import EmailTemplateService
from app.models.email_management import EmailHistory, ScheduledEmail, EmailStatus, ScheduleStatus, EmailCategory
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        self.host = settings.smtp_host
        self.port = settings.smtp_port
        self.username = settings.smtp_user
        self.password = settings.smtp_password
        self.from_addr = settings.email_from

    async def send_email(
        self, 
        to: str | List[str], 
        subject: str, 
        body: str, 
        cc: Optional[List[str]] = None, 
        bcc: Optional[List[str]] = None,
        db: Optional[AsyncSession] = None,
        **metadata
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
        if isinstance(to, str):
            to = [to]
        
        primary_recipient = to[0] if to else ""
        status = EmailStatus.SENT
        error_message = None
        
        try:
            msg = EmailMessage()
            msg["From"] = self.from_addr
            msg["To"] = ", ".join(to)
            msg["Subject"] = subject
            if cc:
                msg["Cc"] = ", ".join(cc)
            if bcc:
                msg["Bcc"] = ", ".join(bcc)
            msg.set_content(body)
            
            # Calculate email size
            email_size = len(msg.as_string().encode('utf-8'))
            
            await aiosmtplib.send(
                msg,
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                start_tls=True
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
                        **metadata
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
        **metadata
    ):
        """Log email to history table"""
        try:
            history = EmailHistory(
                recipient_email=recipient_email,
                cc_emails=json.dumps(cc_emails) if cc_emails else None,
                bcc_emails=json.dumps(bcc_emails) if bcc_emails else None,
                subject=subject,
                body=body,
                template_key=metadata.get('template_key'),
                email_category=metadata.get('email_category'),
                application_id=metadata.get('application_id'),
                scholarship_type_id=metadata.get('scholarship_type_id'),
                sent_by_user_id=metadata.get('sent_by_user_id'),
                sent_by_system=metadata.get('sent_by_system', True),
                status=status,
                error_message=error_message,
                email_size_bytes=email_size_bytes,
                retry_count=metadata.get('retry_count', 0)
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
        **metadata
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
        metadata['template_key'] = key
        
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
        **metadata
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
            template_key=metadata.get('template_key'),
            email_category=metadata.get('email_category'),
            scheduled_for=scheduled_for,
            application_id=metadata.get('application_id'),
            scholarship_type_id=metadata.get('scholarship_type_id'),
            requires_approval=requires_approval,
            created_by_user_id=metadata.get('created_by_user_id'),
            priority=priority
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
        **metadata
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
        metadata['template_key'] = key
        
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
            **metadata
        )

    async def send_to_college_reviewers(self, application, db: Optional[AsyncSession] = None):
        key = "college_notify"
        context = {
            "app_id": application.app_id,
            "student_name": getattr(application, 'student_name', ''),
            "scholarship_type": getattr(application, 'scholarship_type', ''),
            "submit_date": application.submitted_at.strftime('%Y-%m-%d') if getattr(application, 'submitted_at', None) else '',
            "review_deadline": getattr(application, 'review_deadline', ''),
            "college_name": getattr(application, 'college_name', ''),
        }
        default_subject = f"新申請案待審核: {application.app_id}"
        default_body = f"有一份新的申請案({application.app_id})已由教授推薦，請至系統審查。\n\n--\n獎學金申請與簽核作業管理系統"
        # reviewers = ...
        # to = [r.email for r in reviewers]
        to = ["mock_college@nycu.edu.tw"]
        
        # Email metadata for logging
        metadata = {
            'email_category': EmailCategory.REVIEW_COLLEGE,
            'application_id': getattr(application, 'id', None),
            'scholarship_type_id': getattr(application, 'scholarship_type_id', None),
            'sent_by_system': True
        }
        
        if db:
            await self.send_with_template(db, key, to, context, default_subject, default_body, **metadata)
        else:
            await self.send_email(to, default_subject, default_body, **metadata)

    async def send_to_professor(self, application, db: Optional[AsyncSession] = None):
        key = "professor_notify"
        professor = getattr(application, 'professor', None)
        context = {
            "app_id": application.app_id,
            "professor_name": getattr(professor, 'name', '') if professor else '',
            "student_name": getattr(application, 'student_name', ''),
            "scholarship_type": getattr(application, 'scholarship_type', ''),
            "submit_date": application.submitted_at.strftime('%Y-%m-%d') if getattr(application, 'submitted_at', None) else '',
            "professor_email": getattr(professor, 'email', '') if professor else '',
        }
        default_subject = f"新學生申請待推薦: {application.app_id}"
        default_body = f"有一份新的學生申請案({application.app_id})需要您推薦，請至系統審查。\n\n--\n獎學金申請與簽核作業管理系統"
        to = professor.email if professor else None
        
        # Email metadata for logging
        metadata = {
            'email_category': EmailCategory.RECOMMENDATION_PROFESSOR,
            'application_id': getattr(application, 'id', None),
            'scholarship_type_id': getattr(application, 'scholarship_type_id', None),
            'sent_by_system': True
        }
        
        if db and to:
            await self.send_with_template(db, key, to, context, default_subject, default_body, **metadata)
        elif to:
            await self.send_email(to, default_subject, default_body, **metadata) 