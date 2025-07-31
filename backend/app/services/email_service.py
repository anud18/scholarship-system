from app.core.config import settings
import aiosmtplib
from email.message import EmailMessage
from typing import List, Optional
from app.services.system_setting_service import EmailTemplateService
from sqlalchemy.ext.asyncio import AsyncSession

class EmailService:
    def __init__(self):
        self.host = settings.smtp_host
        self.port = settings.smtp_port
        self.username = settings.smtp_user
        self.password = settings.smtp_password
        self.from_addr = settings.email_from

    async def send_email(self, to: str | List[str], subject: str, body: str, cc: Optional[List[str]] = None, bcc: Optional[List[str]] = None):
        if isinstance(to, str):
            to = [to]
        msg = EmailMessage()
        msg["From"] = self.from_addr
        msg["To"] = ", ".join(to)
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = ", ".join(cc)
        if bcc:
            msg["Bcc"] = ", ".join(bcc)
        msg.set_content(body)
        await aiosmtplib.send(
            msg,
            hostname=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            start_tls=True
        )

    async def send_with_template(self, db: AsyncSession, key: str, to: str | List[str], context: dict, default_subject: str, default_body: str, cc: Optional[List[str]] = None, bcc: Optional[List[str]] = None):
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
        await self.send_email(to, subject, body, cc=cc_list, bcc=bcc_list)

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
        if db:
            await self.send_with_template(db, key, to, context, default_subject, default_body)
        else:
            await self.send_email(to, default_subject, default_body)

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
        if db and to:
            await self.send_with_template(db, key, to, context, default_subject, default_body)
        elif to:
            await self.send_email(to, default_subject, default_body) 