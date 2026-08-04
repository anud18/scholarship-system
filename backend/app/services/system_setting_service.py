from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_setting import EmailTemplate, SendingType, SystemSetting


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
            setting.updated_at = datetime.now(timezone.utc)
        else:
            setting = SystemSetting(key=key, value=value, updated_at=datetime.now(timezone.utc))
            db.add(setting)
        await db.commit()
        await db.refresh(setting)
        return setting

    @staticmethod
    async def get_or_create_setting(db: AsyncSession, key: str, default_value: str) -> SystemSetting:
        setting = await SystemSettingService.get_setting(db, key)
        if setting:
            return setting
        return await SystemSettingService.set_setting(db, key, default_value)


class EmailTemplateService:
    @staticmethod
    async def get_template(db: AsyncSession, key: str) -> Optional[EmailTemplate]:
        """Return the GENERIC (scholarship_type_id IS NULL) template for ``key``.

        Per-scholarship templates are read via
        :meth:`get_scholarship_template`.
        """
        stmt = select(EmailTemplate).where(
            EmailTemplate.key == key,
            EmailTemplate.scholarship_type_id.is_(None),
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    # ── Per-scholarship templates (issue #647) ──────────────────────

    @staticmethod
    async def list_scholarship_templates(db: AsyncSession, scholarship_type_id: int) -> List[EmailTemplate]:
        """List all templates whose ``scholarship_type_id`` matches.

        Generic templates (NULL ``scholarship_type_id``) are NOT returned —
        callers explicitly asking for per-scholarship overrides shouldn't
        get the fallback set.
        """
        stmt = (
            select(EmailTemplate)
            .where(EmailTemplate.scholarship_type_id == scholarship_type_id)
            .order_by(EmailTemplate.key)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_scholarship_template(db: AsyncSession, scholarship_type_id: int, key: str) -> Optional[EmailTemplate]:
        """Return the per-scholarship override of ``key`` for the given scholarship."""
        stmt = select(EmailTemplate).where(
            EmailTemplate.scholarship_type_id == scholarship_type_id,
            EmailTemplate.key == key,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_scholarship_template(
        db: AsyncSession, scholarship_type_id: int, data: Dict[str, Any]
    ) -> EmailTemplate:
        """Create a per-scholarship template override.

        Raises ``ValueError`` if an override for ``(scholarship_type_id, key)``
        already exists — callers should ``update_scholarship_template`` instead.
        """
        existing = await EmailTemplateService.get_scholarship_template(db, scholarship_type_id, data["key"])
        if existing is not None:
            raise ValueError(
                f"Per-scholarship template already exists for key={data['key']} "
                f"scholarship_type_id={scholarship_type_id}"
            )
        sending_type_value = data.get("sending_type", "single")
        template = EmailTemplate(
            key=data["key"],
            scholarship_type_id=scholarship_type_id,
            subject_template=data["subject_template"],
            body_template=data["body_template"],
            cc=data.get("cc"),
            bcc=data.get("bcc"),
            sending_type=(SendingType.bulk if sending_type_value == "bulk" else SendingType.single),
            recipient_options=data.get("recipient_options"),
            requires_approval=bool(data.get("requires_approval", False)),
            max_recipients=data.get("max_recipients"),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(template)
        await db.commit()
        await db.refresh(template)
        return template

    @staticmethod
    async def update_scholarship_template(
        db: AsyncSession,
        scholarship_type_id: int,
        key: str,
        data: Dict[str, Any],
    ) -> Optional[EmailTemplate]:
        """Update an existing per-scholarship template override.

        Returns ``None`` if no row matches ``(scholarship_type_id, key)``.
        Only fields present in ``data`` are written.
        """
        template = await EmailTemplateService.get_scholarship_template(db, scholarship_type_id, key)
        if template is None:
            return None
        if "subject_template" in data:
            template.subject_template = data["subject_template"]
        if "body_template" in data:
            template.body_template = data["body_template"]
        if "cc" in data:
            template.cc = data["cc"]
        if "bcc" in data:
            template.bcc = data["bcc"]
        if "sending_type" in data:
            template.sending_type = SendingType.bulk if data["sending_type"] == "bulk" else SendingType.single
        if "recipient_options" in data:
            template.recipient_options = data["recipient_options"]
        if "requires_approval" in data:
            template.requires_approval = bool(data["requires_approval"])
        if "max_recipients" in data:
            template.max_recipients = data["max_recipients"]
        template.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(template)
        return template

    @staticmethod
    async def delete_scholarship_template(db: AsyncSession, scholarship_type_id: int, key: str) -> bool:
        """Delete the per-scholarship override.

        Returns ``True`` if a row was deleted, ``False`` if no match.
        """
        template = await EmailTemplateService.get_scholarship_template(db, scholarship_type_id, key)
        if template is None:
            return False
        await db.delete(template)
        await db.commit()
        return True

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
            template.updated_at = datetime.now(timezone.utc)
        else:
            template = EmailTemplate(
                key=key,
                subject_template=subject,
                body_template=body,
                cc=cc,
                bcc=bcc,
                updated_at=datetime.now(timezone.utc),
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
        return await EmailTemplateService.set_template(db, key, default_subject, default_body)
