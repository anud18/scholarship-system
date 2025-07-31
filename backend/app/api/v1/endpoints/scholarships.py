from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from app.core.deps import get_db
from app.core.config import settings
from app.core.security import require_admin, get_current_user
from app.models.user import User, UserRole
from app.models.scholarship import ScholarshipType
from app.schemas.scholarship import ScholarshipTypeResponse, EligibleScholarshipResponse
from app.schemas.response import ApiResponse
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import joinedload

router = APIRouter()

@router.get("/", response_model=ApiResponse[List[dict]])
async def get_all_scholarships(
    db: AsyncSession = Depends(get_db)
):
    """Get all scholarships for timeline display"""
    stmt = select(ScholarshipType)
    result = await db.execute(stmt)
    scholarships = result.scalars().all()
    
    # Convert to dictionary format for timeline component
    scholarship_list = []
    for scholarship in scholarships:
        scholarship_dict = {
            "id": scholarship.id,
            "code": scholarship.code,
            "name": scholarship.name,
            "name_en": scholarship.name_en,
            "description": scholarship.description,
            "description_en": scholarship.description_en,
            "category": scholarship.category,
            "sub_type_list": scholarship.sub_type_list or [],
            "sub_type_selection_mode": scholarship.sub_type_selection_mode.value if scholarship.sub_type_selection_mode else "single",
            "academic_year": scholarship.academic_year,
            "semester": scholarship.semester.value if scholarship.semester else "first",
            "application_cycle": scholarship.application_cycle.value if scholarship.application_cycle else "semester",
            "amount": float(scholarship.amount) if scholarship.amount else 0,
            "currency": scholarship.currency,
            "whitelist_enabled": scholarship.whitelist_enabled,
            "whitelist_student_ids": scholarship.whitelist_student_ids or [],
            "renewal_application_start_date": scholarship.renewal_application_start_date.isoformat() if scholarship.renewal_application_start_date else None,
            "renewal_application_end_date": scholarship.renewal_application_end_date.isoformat() if scholarship.renewal_application_end_date else None,
            "application_start_date": scholarship.application_start_date.isoformat() if scholarship.application_start_date else None,
            "application_end_date": scholarship.application_end_date.isoformat() if scholarship.application_end_date else None,
            "renewal_professor_review_start": scholarship.renewal_professor_review_start.isoformat() if scholarship.renewal_professor_review_start else None,
            "renewal_professor_review_end": scholarship.renewal_professor_review_end.isoformat() if scholarship.renewal_professor_review_end else None,
            "renewal_college_review_start": scholarship.renewal_college_review_start.isoformat() if scholarship.renewal_college_review_start else None,
            "renewal_college_review_end": scholarship.renewal_college_review_end.isoformat() if scholarship.renewal_college_review_end else None,
            "requires_professor_recommendation": scholarship.requires_professor_recommendation,
            "professor_review_start": scholarship.professor_review_start.isoformat() if scholarship.professor_review_start else None,
            "professor_review_end": scholarship.professor_review_end.isoformat() if scholarship.professor_review_end else None,
            "requires_college_review": scholarship.requires_college_review,
            "college_review_start": scholarship.college_review_start.isoformat() if scholarship.college_review_start else None,
            "college_review_end": scholarship.college_review_end.isoformat() if scholarship.college_review_end else None,
            "review_deadline": scholarship.review_deadline.isoformat() if scholarship.review_deadline else None,
            "status": scholarship.status,
            "created_at": scholarship.created_at.isoformat() if scholarship.created_at else None,
            "updated_at": scholarship.updated_at.isoformat() if scholarship.updated_at else None,
            "created_by": scholarship.created_by,
            "updated_by": scholarship.updated_by
        }
        scholarship_list.append(scholarship_dict)
    
    return ApiResponse(
        success=True,
        message=f"Retrieved {len(scholarship_list)} scholarships",
        data=scholarship_list
    )

# 學生查看自己可以申請的獎學金
@router.get("/eligible", response_model=List[EligibleScholarshipResponse])
async def get_scholarship_eligibility(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get scholarships that the current student is eligible for"""
    from app.services.application_service import get_student_from_user
    from app.services.scholarship_service import get_eligible_scholarships
    
    student = await get_student_from_user(current_user, db)
    if not student:
        raise HTTPException(
            status_code=404, 
            detail=f"Student profile not found for user {current_user.nycu_id}"
        )

    eligible_scholarships = await get_eligible_scholarships(student, db, include_validation_details=False)
    return eligible_scholarships
    
@router.get("/{scholarship_id}", response_model=ScholarshipTypeResponse)
async def get_scholarship_detail(
    scholarship_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get scholarship details"""
    stmt = select(ScholarshipType).options(
        joinedload(ScholarshipType.rules)
    ).where(ScholarshipType.id == scholarship_id)
    result = await db.execute(stmt)
    scholarship = result.unique().scalar_one_or_none()
    if not scholarship:
        raise HTTPException(status_code=404, detail="Scholarship not found")
    return scholarship

@router.post("/dev/reset-application-periods")
async def reset_application_periods(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Reset all scholarship application periods for testing (dev only)"""
    if not settings.debug:
        raise HTTPException(status_code=403, detail="Only available in development mode")
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=30)
    end_date = now + timedelta(days=30)
    stmt = select(ScholarshipType)
    result = await db.execute(stmt)
    scholarships = result.scalars().all()
    for scholarship in scholarships:
        scholarship.application_start_date = start_date
        scholarship.application_end_date = end_date
    await db.commit()
    return ApiResponse(
        success=True,
        message=f"Reset {len(scholarships)} scholarship application periods",
        data={
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "scholarships_updated": len(scholarships)
        }
    )

@router.post("/dev/toggle-whitelist/{scholarship_id}")
async def toggle_scholarship_whitelist(
    scholarship_id: int,
    enable: bool = True,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Toggle scholarship whitelist for testing (dev only)"""
    if not settings.debug:
        raise HTTPException(status_code=403, detail="Only available in development mode")
    stmt = select(ScholarshipType).where(ScholarshipType.id == scholarship_id)
    result = await db.execute(stmt)
    scholarship = result.scalar_one_or_none()
    if not scholarship:
        raise HTTPException(status_code=404, detail="Scholarship not found")
    scholarship.whitelist_enabled = enable
    if not enable:
        scholarship.whitelist_student_ids = []
    await db.commit()
    return ApiResponse(
        success=True,
        message=f"Whitelist {'enabled' if enable else 'disabled'} for {scholarship.name}",
        data={
            "scholarship_id": scholarship_id,
            "scholarship_name": scholarship.name,
            "whitelist_enabled": scholarship.whitelist_enabled
        }
    )

@router.post("/dev/add-to-whitelist/{scholarship_id}")
async def add_student_to_whitelist(
    scholarship_id: int,
    student_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Add student to scholarship whitelist (dev only)"""
    if not settings.debug:
        raise HTTPException(status_code=403, detail="Only available in development mode")
    stmt = select(ScholarshipType).where(ScholarshipType.id == scholarship_id)
    result = await db.execute(stmt)
    scholarship = result.scalar_one_or_none()
    if not scholarship:
        raise HTTPException(status_code=404, detail="Scholarship not found")
    # Ensure whitelist_student_ids is a list
    if not scholarship.whitelist_student_ids:
        scholarship.whitelist_student_ids = []
    # Add student_id if not present
    if student_id not in scholarship.whitelist_student_ids:
        scholarship.whitelist_student_ids.append(student_id)
        scholarship.whitelist_enabled = True
    await db.commit()
    return ApiResponse(
        success=True,
        message=f"Student {student_id} added to {scholarship.name} whitelist",
        data={
            "scholarship_id": scholarship_id,
            "student_id": student_id,
            "whitelist_size": len(scholarship.whitelist_student_ids)
        }
    )