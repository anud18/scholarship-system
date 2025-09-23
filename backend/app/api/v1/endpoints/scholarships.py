from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from app.core.deps import get_db
from app.core.config import settings
from app.core.security import require_admin, get_current_user
from app.models.user import User
from app.models.scholarship import ScholarshipType, ScholarshipConfiguration
from app.models.enums import Semester
from app.schemas.scholarship import ScholarshipTypeResponse, EligibleScholarshipResponse
from app.schemas.response import ApiResponse
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import joinedload

router = APIRouter()

@router.get("/", response_model=ApiResponse[List[dict]])
async def get_all_scholarships(
    academic_year: Optional[int] = Query(None, description="Filter by academic year"),
    semester: Optional[str] = Query(None, description="Filter by semester"),
    db: AsyncSession = Depends(get_db)
):
    """Get all scholarships for timeline display, optionally filtered by academic year and semester"""
    stmt = select(ScholarshipType)
    result = await db.execute(stmt)
    scholarships = result.scalars().all()
    
    # Convert to dictionary format for timeline component
    scholarship_list = []
    for scholarship in scholarships:
        # 使用篩選參數或預設值
        display_academic_year = academic_year if academic_year is not None else 113  # 預設 113 學年
        display_semester = semester if semester is not None else "first"  # 預設第一學期
        
        # Convert semester string to enum for configuration lookup
        semester_enum = None
        if display_semester == "first":
            semester_enum = Semester.FIRST
        elif display_semester == "second":
            semester_enum = Semester.SECOND
        
        # Get active configuration for this scholarship and academic year
        # For yearly scholarships, look for configurations with semester = None
        # For semester scholarships, look for configurations with the specific semester
        config_conditions = [
            ScholarshipConfiguration.scholarship_type_id == scholarship.id,
            ScholarshipConfiguration.academic_year == display_academic_year,
            ScholarshipConfiguration.is_active == True
        ]
        
        # Add semester condition based on scholarship's application cycle
        if scholarship.application_cycle and scholarship.application_cycle.value == "yearly":
            # For yearly scholarships, look for configurations with semester = None
            config_conditions.append(ScholarshipConfiguration.semester.is_(None))
        else:
            # For semester scholarships, look for configurations with the specific semester
            config_conditions.append(ScholarshipConfiguration.semester == semester_enum)
        
        config_stmt = select(ScholarshipConfiguration).where(*config_conditions)
        config_result = await db.execute(config_stmt)
        config = config_result.scalar_one_or_none()
        
        # Build scholarship dictionary with data from configuration or defaults
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
            # 使用篩選的學年學期或預設值
            "academic_year": display_academic_year,
            "semester": display_semester,
            "application_cycle": scholarship.application_cycle.value if scholarship.application_cycle else "semester",
            "whitelist_enabled": scholarship.whitelist_enabled,
            "status": scholarship.status,
            "created_at": scholarship.created_at.isoformat() if scholarship.created_at else None,
            "updated_at": scholarship.updated_at.isoformat() if scholarship.updated_at else None,
            "created_by": scholarship.created_by,
            "updated_by": scholarship.updated_by
        }
        
        # Add configuration-specific data if configuration exists
        if config:
            scholarship_dict.update({
                "amount": config.amount,
                "currency": config.currency,
                "whitelist_student_ids": config.whitelist_student_ids or {},
                "renewal_application_start_date": config.renewal_application_start_date.isoformat() if config.renewal_application_start_date else None,
                "renewal_application_end_date": config.renewal_application_end_date.isoformat() if config.renewal_application_end_date else None,
                "application_start_date": config.application_start_date.isoformat() if config.application_start_date else None,
                "application_end_date": config.application_end_date.isoformat() if config.application_end_date else None,
                "renewal_professor_review_start": config.renewal_professor_review_start.isoformat() if config.renewal_professor_review_start else None,
                "renewal_professor_review_end": config.renewal_professor_review_end.isoformat() if config.renewal_professor_review_end else None,
                "renewal_college_review_start": config.renewal_college_review_start.isoformat() if config.renewal_college_review_start else None,
                "renewal_college_review_end": config.renewal_college_review_end.isoformat() if config.renewal_college_review_end else None,
                "requires_professor_recommendation": config.requires_professor_recommendation,
                "professor_review_start": config.professor_review_start.isoformat() if config.professor_review_start else None,
                "professor_review_end": config.professor_review_end.isoformat() if config.professor_review_end else None,
                "requires_college_review": config.requires_college_review,
                "college_review_start": config.college_review_start.isoformat() if config.college_review_start else None,
                "college_review_end": config.college_review_end.isoformat() if config.college_review_end else None,
                "review_deadline": config.review_deadline.isoformat() if config.review_deadline else None,
            })
        else:
            # No configuration found - use default values
            scholarship_dict.update({
                "amount": 0,
                "currency": "TWD",
                "whitelist_student_ids": {},
                "renewal_application_start_date": None,
                "renewal_application_end_date": None,
                "application_start_date": None,
                "application_end_date": None,
                "renewal_professor_review_start": None,
                "renewal_professor_review_end": None,
                "renewal_college_review_start": None,
                "renewal_college_review_end": None,
                "requires_professor_recommendation": False,
                "professor_review_start": None,
                "professor_review_end": None,
                "requires_college_review": False,
                "college_review_start": None,
                "college_review_end": None,
                "review_deadline": None,
            })
        
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
    from app.services.application_service import get_student_data_from_user
    from app.services.scholarship_service import ScholarshipService
    
    student = await get_student_data_from_user(current_user)
    if not student:
        raise HTTPException(
            status_code=404, 
            detail=f"Student profile not found for user {current_user.nycu_id}"
        )

    scholarship_service = ScholarshipService(db)
    eligible_scholarships = await scholarship_service.get_eligible_scholarships(student, current_user.id)
    
    # Convert scholarship dictionaries to EligibleScholarshipResponse with rule details
    response_data = []
    for scholarship in eligible_scholarships:
        response_item = EligibleScholarshipResponse(
            id=scholarship['id'],
            configuration_id=scholarship['configuration_id'],  # Pass through configuration ID
            code=scholarship['code'],
            name=scholarship['name'],
            name_en=scholarship.get('name_en') or scholarship['name'],
            eligible_sub_types=scholarship.get('sub_type_list', []) or ["general"],
            category=scholarship['category'],
            academic_year=scholarship.get('academic_year'),
            semester=scholarship.get('semester'),
            application_cycle=scholarship.get('application_cycle', 'semester'),
            description=scholarship.get('description'),
            description_en=scholarship.get('description_en'),
            amount=scholarship.get('amount', 0),
            currency=scholarship.get('currency', 'TWD'),
            application_start_date=scholarship.get('application_start_date'),
            application_end_date=scholarship.get('application_end_date'),
            professor_review_start=scholarship.get('professor_review_start'),
            professor_review_end=scholarship.get('professor_review_end'),
            college_review_start=scholarship.get('college_review_start'),
            college_review_end=scholarship.get('college_review_end'),
            sub_type_selection_mode=scholarship.get('sub_type_selection_mode', 'single'),
            passed=scholarship.get('passed', []),  # Rules passed from eligibility check
            warnings=[],  # Hide warnings from student view - they don't need to see these
            errors=scholarship.get('errors', []),  # Error messages from eligibility check
            created_at=scholarship.get('created_at')
        )
        response_data.append(response_item)
    
    return response_data
    
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
    
    # Get active configuration for this scholarship to retrieve amount and other details
    config_stmt = select(ScholarshipConfiguration).where(
        ScholarshipConfiguration.scholarship_type_id == scholarship_id,
        ScholarshipConfiguration.is_active == True
    ).order_by(
        ScholarshipConfiguration.academic_year.desc(),
        ScholarshipConfiguration.semester.desc()
    ).limit(1)
    
    config_result = await db.execute(config_stmt)
    active_config = config_result.scalar_one_or_none()
    
    # Convert the model to response format with proper enum serialization
    response_data = {
        "id": scholarship.id,
        "code": scholarship.code,
        "name": scholarship.name,
        "name_en": scholarship.name_en,
        "description": scholarship.description,
        "description_en": scholarship.description_en,
        "category": scholarship.category if hasattr(scholarship, 'category') else None,
        "application_cycle": scholarship.application_cycle.value if scholarship.application_cycle else "semester",
        "sub_type_list": scholarship.sub_type_list or [],
        "amount": active_config.amount if active_config else 0,  # Get amount from active configuration
        "currency": active_config.currency if active_config else "TWD",  # Get currency from active configuration
        "whitelist_enabled": scholarship.whitelist_enabled if hasattr(scholarship, 'whitelist_enabled') else False,
        "whitelist_student_ids": [student_id for subtype_list in (active_config.whitelist_student_ids.values() if active_config and active_config.whitelist_student_ids else []) for student_id in subtype_list],
        "application_start_date": active_config.application_start_date if active_config else None,
        "application_end_date": active_config.application_end_date if active_config else None,
        "review_deadline": active_config.review_deadline if active_config else None,
        "professor_review_start": active_config.professor_review_start if active_config else None,
        "professor_review_end": active_config.professor_review_end if active_config else None,
        "college_review_start": active_config.college_review_start if active_config else None,
        "college_review_end": active_config.college_review_end if active_config else None,
        "sub_type_selection_mode": scholarship.sub_type_selection_mode.value if scholarship.sub_type_selection_mode else "single",
        "status": scholarship.status if hasattr(scholarship, 'status') else "active",
        "requires_professor_recommendation": active_config.requires_professor_recommendation if active_config else False,
        "requires_college_review": active_config.requires_college_review if active_config else False,
        "review_workflow": scholarship.review_workflow if hasattr(scholarship, 'review_workflow') else None,
        "auto_approval_rules": scholarship.auto_approval_rules if hasattr(scholarship, 'auto_approval_rules') else None,
        "created_at": scholarship.created_at,
        "updated_at": scholarship.updated_at,
        "created_by": scholarship.created_by,
        "updated_by": scholarship.updated_by
    }
    
    return ScholarshipTypeResponse(**response_data)

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