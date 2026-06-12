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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin
from app.db.deps import get_db
from app.models.system_setting import EmailTemplate
from app.models.audit_log import AuditAction, AuditLog
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

    # G31 (#993): EmailHistory stores每封信的完整內容, but TEMPLATE changes had
    # no before/after snapshot — comparing「當時範本 vs 現狀」was impossible.
    db.add(
        AuditLog.create_log(
            user_id=current_user.id,
            action=AuditAction.update.value,
            resource_type="email_template",
            resource_id=str(template.key),
            description=f"email template '{template.key}' updated",
            old_values={
                "subject_template": existing_template.subject_template,
                "body_template": existing_template.body_template,
                "cc": existing_template.cc,
                "bcc": existing_template.bcc,
            },
            new_values={
                "subject_template": template.subject_template,
                "body_template": template.body_template,
                "cc": template.cc,
                "bcc": template.bcc,
            },
        )
    )
    await db.execute(stmt)
    await db.commit()

    # Fetch updated template
    updated_template = await EmailTemplateService.get_template(db, template.key)

    logger.info(
        "email-template updated: key=%s by user_id=%s sending_type=%s",
        template.key,
        current_user.id,
        template.sending_type,
        extra={
            "actor_user_id": current_user.id,
            "actor_role": current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
            "template_key": template.key,
            "sending_type": template.sending_type,
            "subject_template_len": len(template.subject_template) if template.subject_template else 0,
            "body_template_len": len(template.body_template) if template.body_template else 0,
            "cc_count": len(template.cc) if template.cc else 0,
            "bcc_count": len(template.bcc) if template.bcc else 0,
            "requires_approval": template.requires_approval,
            "max_recipients": template.max_recipients,
        },
    )

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

    return {
        "success": True,
        "message": "Email templates retrieved successfully",
        "data": [EmailTemplateSchema.model_validate(template).model_dump() for template in templates],
    }


# Per-scholarship email templates (closes issue #647)
#
# Persistence layer added in the same PR:
#   - EmailTemplate.scholarship_type_id (NULL = generic; non-NULL = override)
#   - Compound UNIQUE (key, scholarship_type_id) so generic + per-scholarship
#     rows coexist for the same key
#   - EmailTemplateService.{list,get,create,update,delete}_scholarship_template


@router.get("/scholarship-email-templates/{scholarship_type_id}")
async def get_scholarship_email_templates(
    scholarship_type_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get all per-scholarship email-template overrides for a scholarship type.

    Returns only rows where ``scholarship_type_id`` matches — generic
    NULL-scoped templates are excluded because clients asking for
    "this scholarship's templates" shouldn't see the fallback set.
    """
    templates = await EmailTemplateService.list_scholarship_templates(db, scholarship_type_id)
    items = [EmailTemplateSchema.model_validate(t).model_dump() for t in templates]
    return {
        "success": True,
        "message": "Scholarship email templates retrieved successfully",
        "data": {"items": items, "scholarship_type_id": scholarship_type_id},
    }


@router.get("/scholarship-email-templates/{scholarship_type_id}/{template_key}")
async def get_scholarship_email_template(
    scholarship_type_id: int,
    template_key: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific per-scholarship email template (404 if not configured)."""
    template = await EmailTemplateService.get_scholarship_template(db, scholarship_type_id, template_key)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No per-scholarship template found for key='{template_key}' "
                f"scholarship_type_id={scholarship_type_id}"
            ),
        )
    return {
        "success": True,
        "message": "Scholarship email template retrieved successfully",
        "data": EmailTemplateSchema.model_validate(template),
    }


@router.post("/scholarship-email-templates", status_code=status.HTTP_201_CREATED)
async def create_scholarship_email_template(
    template_data: EmailTemplateSchema,
    scholarship_type_id: int = Query(..., description="Scholarship type to attach the template to"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new per-scholarship email template (409 if already exists)."""
    payload = template_data.model_dump()
    try:
        template = await EmailTemplateService.create_scholarship_template(db, scholarship_type_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    logger.info(
        "scholarship-email-template created: scholarship_type_id=%s key=%s by user_id=%s",
        scholarship_type_id,
        template.key,
        current_user.id,
        extra={
            "actor_user_id": current_user.id,
            "scholarship_type_id": scholarship_type_id,
            "template_key": template.key,
        },
    )
    return {
        "success": True,
        "message": "Scholarship email template created successfully",
        "data": EmailTemplateSchema.model_validate(template),
    }


@router.put("/scholarship-email-templates/{scholarship_type_id}/{template_key}")
async def update_scholarship_email_template(
    scholarship_type_id: int,
    template_key: str,
    template_data: EmailTemplateUpdateSchema,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing per-scholarship email template (404 if not configured)."""
    payload = template_data.model_dump(exclude_unset=True)
    # G31 (#993): snapshot the prior version before the in-place update.
    prior = await EmailTemplateService.get_scholarship_template(db, scholarship_type_id, template_key)
    prior_values = (
        {
            "subject_template": prior.subject_template,
            "body_template": prior.body_template,
        }
        if prior
        else None
    )
    template = await EmailTemplateService.update_scholarship_template(db, scholarship_type_id, template_key, payload)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No per-scholarship template found for key='{template_key}' "
                f"scholarship_type_id={scholarship_type_id}"
            ),
        )

    db.add(
        AuditLog.create_log(
            user_id=current_user.id,
            action=AuditAction.update.value,
            resource_type="email_template",
            resource_id=f"{scholarship_type_id}:{template_key}",
            description=f"scholarship email template '{template_key}' (type {scholarship_type_id}) updated",
            old_values=prior_values,
            new_values={k: v for k, v in payload.items() if k in ("subject_template", "body_template", "cc", "bcc")},
        )
    )
    await db.commit()

    logger.info(
        "scholarship-email-template updated: scholarship_type_id=%s key=%s by user_id=%s fields=%s",
        scholarship_type_id,
        template_key,
        current_user.id,
        sorted(payload.keys()),
        extra={
            "actor_user_id": current_user.id,
            "scholarship_type_id": scholarship_type_id,
            "template_key": template_key,
            "updated_fields": sorted(payload.keys()),
        },
    )
    return {
        "success": True,
        "message": "Scholarship email template updated successfully",
        "data": EmailTemplateSchema.model_validate(template),
    }


@router.delete("/scholarship-email-templates/{scholarship_type_id}/{template_key}")
async def delete_scholarship_email_template(
    scholarship_type_id: int,
    template_key: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a per-scholarship email template (404 if not configured)."""
    deleted = await EmailTemplateService.delete_scholarship_template(db, scholarship_type_id, template_key)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No per-scholarship template found for key='{template_key}' "
                f"scholarship_type_id={scholarship_type_id}"
            ),
        )

    logger.info(
        "scholarship-email-template deleted: scholarship_type_id=%s key=%s by user_id=%s",
        scholarship_type_id,
        template_key,
        current_user.id,
        extra={
            "actor_user_id": current_user.id,
            "scholarship_type_id": scholarship_type_id,
            "template_key": template_key,
        },
    )
    return {
        "success": True,
        "message": "Scholarship email template deleted successfully",
        "data": None,
    }


@router.post(
    "/scholarship-email-templates/{scholarship_type_id}/bulk-create",
    status_code=status.HTTP_201_CREATED,
)
async def bulk_create_scholarship_email_templates(
    scholarship_type_id: int,
    templates: List[EmailTemplateSchema],
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create multiple per-scholarship templates in one call (idempotent on conflict)."""
    created: list = []
    skipped: list = []
    for tpl in templates:
        payload = tpl.model_dump()
        try:
            row = await EmailTemplateService.create_scholarship_template(db, scholarship_type_id, payload)
            created.append(EmailTemplateSchema.model_validate(row))
        except ValueError:
            skipped.append(payload["key"])

    logger.info(
        "scholarship-email-template bulk-create: scholarship_type_id=%s created=%d skipped=%d by user_id=%s",
        scholarship_type_id,
        len(created),
        len(skipped),
        current_user.id,
        extra={
            "actor_user_id": current_user.id,
            "scholarship_type_id": scholarship_type_id,
            "created_count": len(created),
            "skipped_keys": skipped,
        },
    )
    return {
        "success": True,
        "message": f"Bulk created {len(created)} scholarship email templates",
        "data": {
            "created": [c.model_dump() for c in created],
            "skipped_keys": skipped,
            "scholarship_type_id": scholarship_type_id,
        },
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
