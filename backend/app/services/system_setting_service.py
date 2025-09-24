from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_setting import EmailTemplate, SystemSetting


class SystemSettingService:
    @staticmethod
    async def get_setting(db: AsyncSession, key: str) -> Optional[SystemSetting]:
        stmt = select(SystemSetting).where(SystemSetting.key == key)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def set_setting(db: AsyncSession, key: str, value: str) -> SystemSetting:
        setting = await SystemSettingService.get_setting(db, key)
        if setting:
            setting.value = value
            setting.updated_at = datetime.utcnow()
        else:
            setting = SystemSetting(key=key, value=value, updated_at=datetime.utcnow())
            db.add(setting)
        await db.commit()
        await db.refresh(setting)
        return setting

    @staticmethod
    async def get_or_create_setting(
        db: AsyncSession, key: str, default_value: str
    ) -> SystemSetting:
        setting = await SystemSettingService.get_setting(db, key)
        if setting:
            return setting
        return await SystemSettingService.set_setting(db, key, default_value)


class EmailTemplateService:
    @staticmethod
    async def get_template(db: AsyncSession, key: str) -> Optional[EmailTemplate]:
        stmt = select(EmailTemplate).where(EmailTemplate.key == key)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def set_template(
        db: AsyncSession,
        key: str,
        subject: str,
        body: str,
        cc: Optional[str] = None,
        bcc: Optional[str] = None,
    ) -> EmailTemplate:
        template = await EmailTemplateService.get_template(db, key)
        if template:
            template.subject_template = subject
            template.body_template = body
            template.cc = cc
            template.bcc = bcc
            template.updated_at = datetime.utcnow()
        else:
            template = EmailTemplate(
                key=key,
                subject_template=subject,
                body_template=body,
                cc=cc,
                bcc=bcc,
                updated_at=datetime.utcnow(),
            )
            db.add(template)
        await db.commit()
        await db.refresh(template)
        return template

    @staticmethod
    async def get_or_create_template(
        db: AsyncSession, key: str, default_subject: str, default_body: str
    ) -> EmailTemplate:
        template = await EmailTemplateService.get_template(db, key)
        if template:
            return template
        return await EmailTemplateService.set_template(
            db, key, default_subject, default_body
        )
