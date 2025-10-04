"""
Email management API endpoints for viewing email history and scheduled emails
"""

import json
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin
from app.db.deps import get_db
from app.models.email_management import EmailCategory, EmailStatus, EmailTestModeAudit, ScheduleStatus
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.email_management import (
    EmailHistoryListResponse,
    EmailHistoryRead,
    EmailProcessingStats,
    ScheduledEmailListResponse,
    ScheduledEmailRead,
    ScheduledEmailUpdate,
)
from app.services.config_management_service import ConfigurationService
from app.services.email_management_service import EmailManagementService

router = APIRouter()
email_service = EmailManagementService()


@router.get("/history", response_model=ApiResponse[EmailHistoryListResponse])
async def get_email_history(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    email_category: Optional[EmailCategory] = None,
    status: Optional[EmailStatus] = None,
    scholarship_type_id: Optional[int] = None,
    recipient_email: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
):
    """
    Get email history with permission-based filtering.
    Admins only see emails for their assigned scholarships.
    Superadmins see all emails.
    """
    emails, total = await email_service.get_email_history(
        db=db,
        user=current_user,
        skip=skip,
        limit=limit,
        email_category=email_category,
        status=status,
        scholarship_type_id=scholarship_type_id,
        recipient_email=recipient_email,
        date_from=date_from,
        date_to=date_to,
    )

    # Convert ORM objects to Pydantic models
    email_items = [EmailHistoryRead.from_orm_with_relations(email) for email in emails]

    response_data = EmailHistoryListResponse(items=email_items, total=total, skip=skip, limit=limit)

    return ApiResponse(success=True, message="Email history retrieved successfully", data=response_data)


@router.get("/scheduled", response_model=ApiResponse[ScheduledEmailListResponse])
async def get_scheduled_emails(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[ScheduleStatus] = None,
    scholarship_type_id: Optional[int] = None,
    requires_approval: Optional[bool] = None,
    email_category: Optional[EmailCategory] = None,
    scheduled_from: Optional[datetime] = None,
    scheduled_to: Optional[datetime] = None,
):
    """
    Get scheduled emails with permission-based filtering.
    Admins only see emails for their assigned scholarships or emails they created.
    Superadmins see all emails.
    """
    emails, total = await email_service.get_scheduled_emails(
        db=db,
        user=current_user,
        skip=skip,
        limit=limit,
        status=status,
        scholarship_type_id=scholarship_type_id,
        requires_approval=requires_approval,
        email_category=email_category,
        scheduled_from=scheduled_from,
        scheduled_to=scheduled_to,
    )

    # Convert ORM objects to Pydantic models
    email_items = [ScheduledEmailRead.from_orm_with_relations(email) for email in emails]

    response_data = ScheduledEmailListResponse(items=email_items, total=total, skip=skip, limit=limit)

    return ApiResponse(
        success=True,
        message="Scheduled emails retrieved successfully",
        data=response_data,
    )


@router.get("/scheduled/due", response_model=List[ScheduledEmailRead])
async def get_due_scheduled_emails(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    limit: int = Query(50, ge=1, le=200),
):
    """
    Get scheduled emails that are due to be sent.
    Only superadmins can access this endpoint for system processing.
    """
    if not current_user.is_super_admin():
        raise HTTPException(status_code=403, detail="Only superadmins can access due emails")

    emails = await email_service.get_due_scheduled_emails(db=db, limit=limit)
    return emails


@router.patch("/scheduled/{email_id}/approve", response_model=ScheduledEmailRead)
async def approve_scheduled_email(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    email_id: int,
    approval_data: ScheduledEmailUpdate,
):
    """
    Approve a scheduled email.
    Only users with permission to the associated scholarship can approve.
    """
    try:
        # Check if user has permission to approve this email
        # This is handled within the service method for permission checking
        scheduled_email = await email_service.approve_scheduled_email(
            db=db,
            email_id=email_id,
            approved_by_user_id=current_user.id,
            notes=approval_data.approval_notes,
        )
        return scheduled_email
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to approve email")


@router.patch("/scheduled/{email_id}/cancel", response_model=ScheduledEmailRead)
async def cancel_scheduled_email(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    email_id: int,
):
    """
    Cancel a scheduled email.
    Only users with permission to the associated scholarship can cancel.
    """
    try:
        # Check if user has permission to cancel this email
        # This is handled within the service method for permission checking
        scheduled_email = await email_service.cancel_scheduled_email(db=db, email_id=email_id)
        return scheduled_email
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to cancel email")


@router.patch("/scheduled/{email_id}", response_model=ScheduledEmailRead)
async def update_scheduled_email(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    email_id: int,
    update_data: ScheduledEmailUpdate,
):
    """
    Update a scheduled email's subject and body.
    Only super_admin can update scheduled emails.
    """
    if not current_user.is_super_admin():
        raise HTTPException(status_code=403, detail="Super admin access required")

    try:
        scheduled_email = await email_service.update_scheduled_email(
            db=db, email_id=email_id, subject=update_data.subject, body=update_data.body
        )
        return scheduled_email
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to update scheduled email")


@router.post("/scheduled/process", response_model=EmailProcessingStats)
async def process_due_emails(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    batch_size: int = Query(10, ge=1, le=50),
):
    """
    Process due scheduled emails by sending them.
    Only superadmins can trigger email processing.
    """
    if not current_user.is_super_admin():
        raise HTTPException(status_code=403, detail="Only superadmins can process emails")

    try:
        stats = await email_service.process_due_emails(db=db, batch_size=batch_size)
        return EmailProcessingStats(**stats)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process emails: {str(e)}")


@router.get("/categories", response_model=List[str])
async def get_email_categories(
    current_user: User = Depends(require_admin),
):
    """
    Get list of available email categories.
    """
    return [category.value for category in EmailCategory]


@router.get("/statuses", response_model=dict)
async def get_email_statuses(
    current_user: User = Depends(require_admin),
):
    """
    Get list of available email and schedule statuses.
    """
    return {
        "email_statuses": [status.value for status in EmailStatus],
        "schedule_statuses": [status.value for status in ScheduleStatus],
    }


# ========== Email Test Mode Endpoints ==========


@router.get("/test-mode/status")
async def get_test_mode_status(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    獲取郵件測試模式狀態（向後相容舊格式）
    """
    try:
        config_service = ConfigurationService(db)
        config = await config_service.get_configuration("email_test_mode")

        if not config:
            return ApiResponse(
                success=True,
                message="Test mode configuration not found",
                data={"enabled": False, "redirect_emails": [], "expires_at": None},
            )

        # Parse JSON value
        test_config = json.loads(config.value) if isinstance(config.value, str) else config.value

        # Backward compatibility: convert old redirect_email to redirect_emails array
        if "redirect_email" in test_config and "redirect_emails" not in test_config:
            old_email = test_config.get("redirect_email")
            test_config["redirect_emails"] = [old_email] if old_email else []
            # Remove old key
            del test_config["redirect_email"]

        # Ensure redirect_emails is always an array
        if "redirect_emails" not in test_config:
            test_config["redirect_emails"] = []

        return ApiResponse(
            success=True,
            message="Test mode status retrieved successfully",
            data=test_config,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get test mode status: {str(e)}")


@router.post("/test-mode/enable")
async def enable_test_mode(
    redirect_emails: str,
    request: Request,
    duration_hours: int = 24,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    啟用郵件測試模式

    Args:
        redirect_emails: 測試郵件重定向地址（多個信箱用逗號或換行符分隔）
        duration_hours: 測試模式持續時間（小時），預設 24 小時
    """
    if not current_user.is_super_admin():
        raise HTTPException(status_code=403, detail="只有超級管理員可以啟用測試模式")

    try:
        config_service = ConfigurationService(db)

        # Parse and validate email addresses
        # Support both comma and newline separation
        email_list = []
        for email in redirect_emails.replace("\n", ",").split(","):
            email = email.strip()
            if email and "@" in email:
                email_list.append(email)

        if not email_list:
            raise HTTPException(status_code=400, detail="請至少提供一個有效的測試信箱地址")

        # Calculate expiration time
        expires_at = datetime.now(timezone.utc) + timedelta(hours=duration_hours)

        # Create test mode config (using new redirect_emails array format)
        test_config = {
            "enabled": True,
            "redirect_emails": email_list,
            "expires_at": expires_at.isoformat(),
            "enabled_by": current_user.id,
            "enabled_at": datetime.now(timezone.utc).isoformat(),
        }

        # Update configuration
        await config_service.set_configuration(
            key="email_test_mode",
            value=json.dumps(test_config),
            user_id=current_user.id,
        )

        # Log audit event
        client_ip = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

        audit_log = EmailTestModeAudit.log_enabled(
            user_id=current_user.id, config_after=test_config, ip_address=client_ip, user_agent=user_agent
        )
        db.add(audit_log)
        await db.commit()

        return ApiResponse(
            success=True,
            message=f"測試模式已啟用，將於 {duration_hours} 小時後自動關閉",
            data=test_config,
        )

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to enable test mode: {str(e)}")


@router.post("/test-mode/disable")
async def disable_test_mode(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    停用郵件測試模式
    """
    if not current_user.is_super_admin():
        raise HTTPException(status_code=403, detail="只有超級管理員可以停用測試模式")

    try:
        config_service = ConfigurationService(db)
        old_config = await config_service.get_configuration("email_test_mode")

        if not old_config:
            return ApiResponse(
                success=True,
                message="Test mode not configured",
                data={"enabled": False},
            )

        # Parse old config
        old_test_config = json.loads(old_config.value) if isinstance(old_config.value, str) else old_config.value

        # Create new disabled config
        new_test_config = {
            "enabled": False,
            "redirect_emails": [],
            "expires_at": None,
            "disabled_by": current_user.id,
            "disabled_at": datetime.now(timezone.utc).isoformat(),
        }

        # Update configuration
        await config_service.set_configuration(
            key="email_test_mode",
            value=json.dumps(new_test_config),
            user_id=current_user.id,
        )

        # Log audit event
        client_ip = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")

        audit_log = EmailTestModeAudit.log_disabled(
            user_id=current_user.id, config_before=old_test_config, ip_address=client_ip, user_agent=user_agent
        )
        db.add(audit_log)
        await db.commit()

        return ApiResponse(
            success=True,
            message="測試模式已停用",
            data=new_test_config,
        )

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to disable test mode: {str(e)}")


@router.get("/test-mode/audit")
async def get_test_mode_audit_logs(
    *,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    limit: int = Query(100, ge=1, le=1000),
    event_type: Optional[str] = None,
):
    """
    獲取郵件測試模式稽核記錄
    """
    try:
        # Build query
        stmt = select(EmailTestModeAudit).order_by(EmailTestModeAudit.timestamp.desc()).limit(limit)

        if event_type:
            stmt = stmt.where(EmailTestModeAudit.event_type == event_type)

        result = await db.execute(stmt)
        audit_logs = result.scalars().all()

        # Convert to dict format
        audit_data = []
        for log in audit_logs:
            audit_data.append(
                {
                    "id": log.id,
                    "event_type": log.event_type,
                    "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                    "user_id": log.user_id,
                    "config_before": log.config_before,
                    "config_after": log.config_after,
                    "original_recipient": log.original_recipient,
                    "actual_recipient": log.actual_recipient,
                    "email_subject": log.email_subject,
                    "session_id": log.session_id,
                    "ip_address": str(log.ip_address) if log.ip_address else None,
                }
            )

        return ApiResponse(
            success=True,
            message=f"Retrieved {len(audit_data)} audit log entries",
            data={"items": audit_data, "total": len(audit_data)},
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get audit logs: {str(e)}")


@router.delete("/test-mode/audit-logs/cleanup")
async def cleanup_old_audit_logs(
    retention_days: int = Query(90, description="保留最近 N 天的記錄，預設 90 天"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    清理舊的測試模式稽核記錄

    Args:
        retention_days: 保留天數，預設 90 天（會刪除超過此天數的記錄）
    """
    if not current_user.is_super_admin():
        raise HTTPException(status_code=403, detail="只有超級管理員可以清理稽核記錄")

    try:
        from datetime import timedelta

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

        # Count records to be deleted
        count_stmt = select(EmailTestModeAudit).where(EmailTestModeAudit.timestamp < cutoff_date)
        count_result = await db.execute(count_stmt)
        records_to_delete = len(count_result.scalars().all())

        # Delete old audit logs
        delete_stmt = select(EmailTestModeAudit).where(EmailTestModeAudit.timestamp < cutoff_date)
        delete_result = await db.execute(delete_stmt)
        old_logs = delete_result.scalars().all()

        for log in old_logs:
            await db.delete(log)

        await db.commit()

        return ApiResponse(
            success=True,
            message=f"Successfully deleted {records_to_delete} audit log entries older than {retention_days} days",
            data={
                "deleted_count": records_to_delete,
                "retention_days": retention_days,
                "cutoff_date": cutoff_date.isoformat(),
            },
        )

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to cleanup audit logs: {str(e)}")
