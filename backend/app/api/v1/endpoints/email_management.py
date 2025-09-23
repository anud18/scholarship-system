"""
Email management API endpoints for viewing email history and scheduled emails
"""

from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.deps import get_db
from app.core.security import require_admin
from app.models.user import User
from app.models.email_management import EmailStatus, ScheduleStatus, EmailCategory
from app.services.email_management_service import EmailManagementService
from app.schemas.email_management import (
    EmailHistoryRead,
    EmailHistoryListResponse,
    ScheduledEmailRead,
    ScheduledEmailListResponse,
    ScheduledEmailUpdate,
    EmailProcessingStats
)
from app.schemas.common import ApiResponse

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
        date_to=date_to
    )
    
    # Convert ORM objects to Pydantic models
    email_items = [EmailHistoryRead.from_orm_with_relations(email) for email in emails]
    
    response_data = EmailHistoryListResponse(
        items=email_items,
        total=total,
        skip=skip,
        limit=limit
    )
    
    return ApiResponse(
        success=True,
        message="Email history retrieved successfully",
        data=response_data
    )


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
        scheduled_to=scheduled_to
    )
    
    # Convert ORM objects to Pydantic models
    email_items = [ScheduledEmailRead.from_orm_with_relations(email) for email in emails]
    
    response_data = ScheduledEmailListResponse(
        items=email_items,
        total=total,
        skip=skip,
        limit=limit
    )
    
    return ApiResponse(
        success=True,
        message="Scheduled emails retrieved successfully",
        data=response_data
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
    if current_user.role != "superadmin":
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
            notes=approval_data.approval_notes
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
        scheduled_email = await email_service.cancel_scheduled_email(
            db=db,
            email_id=email_id
        )
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
    # Check if user is super admin
    from app.models.user import UserRole
    if current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Super admin access required")
    
    try:
        scheduled_email = await email_service.update_scheduled_email(
            db=db,
            email_id=email_id,
            subject=update_data.subject,
            body=update_data.body
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
    if current_user.role != "superadmin":
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
        "schedule_statuses": [status.value for status in ScheduleStatus]
    }