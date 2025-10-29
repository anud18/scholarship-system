"""
Admin Email Templates Management API Endpoints

Handles email template operations including:
- Generic email templates
- Scholarship-specific email templates
- Bulk template operations
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin
from app.db.deps import get_db
from app.models.system_setting import EmailTemplate
from app.models.user import User
from app.schemas.common import EmailTemplateSchema, EmailTemplateUpdateSchema
from app.services.system_setting_service import EmailTemplateService

from ._helpers import require_super_admin

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/email-template")
async def get_email_template(
    key: str = Query(..., description="Template key"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get email template by key (admin only)"""
    template = await EmailTemplateService.get_template(db, key)
    if not template:
        template_data = EmailTemplateSchema(
            key=key, subject_template="", body_template="", cc=None, bcc=None, updated_at=None
        )
    else:
        template_data = EmailTemplateSchema.model_validate(template)

    return {"success": True, "message": "Email template retrieved successfully", "data": template_data}


@router.put("/email-template")
async def update_email_template(
    template: EmailTemplateUpdateSchema,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update email template (super admin only)"""
    from app.models.system_setting import SendingType

    # Validate sending_type
    if template.sending_type not in ["single", "bulk"]:
        raise HTTPException(status_code=400, detail="Invalid sending_type. Must be 'single' or 'bulk'")

    # Get existing template
    existing_template = await EmailTemplateService.get_template(db, template.key)
    if not existing_template:
        raise HTTPException(status_code=404, detail="Email template not found")

    # Update the template using raw SQLAlchemy update
    from sqlalchemy import update as sql_update

    stmt = (
        sql_update(EmailTemplate)
        .where(EmailTemplate.key == template.key)
        .values(
            subject_template=template.subject_template,
            body_template=template.body_template,
            cc=template.cc,
            bcc=template.bcc,
            sending_type=SendingType.single if template.sending_type == "single" else SendingType.bulk,
            recipient_options=template.recipient_options,
            requires_approval=template.requires_approval,
            max_recipients=template.max_recipients,
            updated_at=func.now(),
        )
    )

    await db.execute(stmt)
    await db.commit()

    # Fetch updated template
    updated_template = await EmailTemplateService.get_template(db, template.key)

    return {
        "success": True,
        "message": "Email template updated successfully",
        "data": EmailTemplateSchema.model_validate(updated_template),
    }


@router.get("/email-templates")
async def get_email_templates(
    sending_type: Optional[str] = Query(None, description="Filter by sending type (single/bulk)"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get all email templates with optional sending type filtering"""
    from app.models.system_setting import SendingType

    stmt = select(EmailTemplate)

    if sending_type:
        if sending_type.lower() == "single":
            stmt = stmt.where(EmailTemplate.sending_type == SendingType.single)
        elif sending_type.lower() == "bulk":
            stmt = stmt.where(EmailTemplate.sending_type == SendingType.bulk)

    stmt = stmt.order_by(EmailTemplate.sending_type, EmailTemplate.key)
    result = await db.execute(stmt)
    templates = result.scalars().all()

    return [EmailTemplateSchema.model_validate(template) for template in templates]


@router.get("/scholarship-email-templates/{scholarship_type_id}")
async def get_scholarship_email_templates(
    scholarship_type_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get all email templates for a scholarship type"""
    service = EmailTemplateService(db)
    templates = await service.get_scholarship_templates(scholarship_type_id)
    return {
        "success": True,
        "message": "Email templates retrieved successfully",
        "data": templates,
    }


@router.get("/scholarship-email-templates/{scholarship_type_id}/{template_key}")
async def get_scholarship_email_template(
    scholarship_type_id: int,
    template_key: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific email template"""
    service = EmailTemplateService(db)
    template = await service.get_template(scholarship_type_id, template_key)
    return {
        "success": True,
        "message": "Email template retrieved successfully",
        "data": template,
    }


@router.post("/scholarship-email-templates")
async def create_scholarship_email_template(
    template_data: EmailTemplateSchema,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new email template"""
    service = EmailTemplateService(db)
    template = await service.create_template(template_data)
    return {
        "success": True,
        "message": "Email template created successfully",
        "data": template,
    }


@router.put("/scholarship-email-templates/{scholarship_type_id}/{template_key}")
async def update_scholarship_email_template(
    scholarship_type_id: int,
    template_key: str,
    template_data: EmailTemplateUpdateSchema,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update an email template"""
    service = EmailTemplateService(db)
    template = await service.update_template(scholarship_type_id, template_key, template_data)
    return {
        "success": True,
        "message": "Email template updated successfully",
        "data": template,
    }


@router.delete("/scholarship-email-templates/{scholarship_type_id}/{template_key}")
async def delete_scholarship_email_template(
    scholarship_type_id: int,
    template_key: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete an email template"""
    service = EmailTemplateService(db)
    await service.delete_template(scholarship_type_id, template_key)
    return {
        "success": True,
        "message": "Email template deleted successfully",
    }


@router.post("/scholarship-email-templates/{scholarship_type_id}/bulk-create")
async def bulk_create_scholarship_email_templates(
    scholarship_type_id: int,
    templates: List[EmailTemplateSchema],
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Bulk create email templates"""
    service = EmailTemplateService(db)
    created_templates = []
    for template_data in templates:
        template = await service.create_template(template_data)
        created_templates.append(template)
    return {
        "success": True,
        "message": f"{len(created_templates)} email templates created successfully",
        "data": created_templates,
    }


@router.get("/scholarship-email-templates/{scholarship_type_id}/available")
async def get_available_scholarship_email_templates(
    scholarship_type_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get available email template keys for a scholarship type"""
    # Return available template keys
    available_keys = [
        "application_approved",
        "application_rejected",
        "application_pending",
        "reminder_incomplete",
        "notification_new_application",
    ]
    return {
        "success": True,
        "message": "Available template keys retrieved successfully",
        "data": available_keys,
    }
