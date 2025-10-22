from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.config import settings
from app.core.deps import get_db
from app.core.security import get_current_user, require_admin
from app.models.enums import Semester
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User
from app.schemas.response import ApiResponse
from app.schemas.scholarship import EligibleScholarshipResponse, ScholarshipTypeResponse, WhitelistToggleRequest

router = APIRouter()


@router.get("")
async def get_all_scholarships(
    academic_year: Optional[int] = Query(None, description="Filter by academic year"),
    semester: Optional[str] = Query(None, description="Filter by semester"),
    db: AsyncSession = Depends(get_db),
):
    """Get all scholarships for timeline display, optionally filtered by academic year and semester"""
    stmt = select(ScholarshipType)
    result = await db.execute(stmt)
    scholarships = result.scalars().all()

    # 使用篩選參數或預設值
    display_academic_year = academic_year if academic_year is not None else 113  # 預設 113 學年
    display_semester = semester if semester is not None else "first"  # 預設第一學期

    # Convert semester string to enum for configuration lookup
    semester_enum = None
    if display_semester == "first":
        semester_enum = Semester.first
    elif display_semester == "second":
        semester_enum = Semester.second

    # Batch load all configurations to avoid N+1 query
    # Get scholarship IDs for batch query
    scholarship_ids = [s.id for s in scholarships]

    # Build configuration query with all conditions
    config_conditions = [
        ScholarshipConfiguration.scholarship_type_id.in_(scholarship_ids),
        ScholarshipConfiguration.academic_year == display_academic_year,
        ScholarshipConfiguration.is_active.is_(True),
    ]

    # Load configurations for both yearly (semester=None) and semester-specific
    config_stmt = select(ScholarshipConfiguration).where(*config_conditions)
    config_result = await db.execute(config_stmt)
    all_configs = config_result.scalars().all()

    # Create mapping of (scholarship_id, is_yearly) -> configuration
    config_map = {}
    for config in all_configs:
        # Store config by (scholarship_type_id, semester) key
        key = (config.scholarship_type_id, config.semester)
        config_map[key] = config

    # Convert to dictionary format for timeline component
    scholarship_list = []
    for scholarship in scholarships:
        # Determine which config to use based on application cycle
        if scholarship.application_cycle and scholarship.application_cycle.value == "yearly":
            # For yearly scholarships, use config with semester = None
            config = config_map.get((scholarship.id, None))
        else:
            # For semester scholarships, use config with specific semester
            config = config_map.get((scholarship.id, semester_enum))

        # Build scholarship dictionary with data from configuration or defaults
        scholarship_dict = {
            "id": scholarship.id,
            "code": scholarship.code,
            "name": scholarship.name,
            "name_en": scholarship.name_en,
            "description": scholarship.description,
            "description_en": scholarship.description_en,
            "sub_type_list": scholarship.sub_type_list or [],
            "sub_type_selection_mode": scholarship.sub_type_selection_mode.value
            if scholarship.sub_type_selection_mode
            else "single",
            # 使用篩選的學年學期或預設值
            "academic_year": display_academic_year,
            "semester": display_semester,
            "application_cycle": scholarship.application_cycle.value if scholarship.application_cycle else "semester",
            "whitelist_enabled": scholarship.whitelist_enabled,
            "status": scholarship.status,
            "created_at": scholarship.created_at.isoformat() if scholarship.created_at else None,
            "updated_at": scholarship.updated_at.isoformat() if scholarship.updated_at else None,
            "created_by": scholarship.created_by,
            "updated_by": scholarship.updated_by,
        }

        # Add configuration-specific data if configuration exists
        if config:
            scholarship_dict.update(
                {
                    "configuration_id": config.id,
                    "amount": config.amount,
                    "currency": config.currency,
                    "whitelist_student_ids": config.whitelist_student_ids or {},
                    "renewal_application_start_date": config.renewal_application_start_date.isoformat()
                    if config.renewal_application_start_date
                    else None,
                    "renewal_application_end_date": config.renewal_application_end_date.isoformat()
                    if config.renewal_application_end_date
                    else None,
                    "application_start_date": config.application_start_date.isoformat()
                    if config.application_start_date
                    else None,
                    "application_end_date": config.application_end_date.isoformat()
                    if config.application_end_date
                    else None,
                    "renewal_professor_review_start": config.renewal_professor_review_start.isoformat()
                    if config.renewal_professor_review_start
                    else None,
                    "renewal_professor_review_end": config.renewal_professor_review_end.isoformat()
                    if config.renewal_professor_review_end
                    else None,
                    "renewal_college_review_start": config.renewal_college_review_start.isoformat()
                    if config.renewal_college_review_start
                    else None,
                    "renewal_college_review_end": config.renewal_college_review_end.isoformat()
                    if config.renewal_college_review_end
                    else None,
                    "requires_professor_recommendation": config.requires_professor_recommendation,
                    "professor_review_start": config.professor_review_start.isoformat()
                    if config.professor_review_start
                    else None,
                    "professor_review_end": config.professor_review_end.isoformat()
                    if config.professor_review_end
                    else None,
                    "requires_college_review": config.requires_college_review,
                    "college_review_start": config.college_review_start.isoformat()
                    if config.college_review_start
                    else None,
                    "college_review_end": config.college_review_end.isoformat() if config.college_review_end else None,
                    "review_deadline": config.review_deadline.isoformat() if config.review_deadline else None,
                }
            )
        else:
            # No configuration found - use default values
            scholarship_dict.update(
                {
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
                }
            )

        scholarship_list.append(scholarship_dict)

    return ApiResponse(
        success=True,
        message=f"Retrieved {len(scholarship_list)} scholarships",
        data=scholarship_list,
    )


# 學生查看自己可以申請的獎學金
@router.get("/eligible")
async def get_scholarship_eligibility(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """Get scholarships that the current student is eligible for"""
    from app.services.application_service import get_student_data_from_user
    from app.services.scholarship_service import ScholarshipService

    student = await get_student_data_from_user(current_user)
    if not student:
        raise HTTPException(
            status_code=404,
            detail={
                "message": "無法取得學生資料，請稍後再試或聯繫系統管理員",
                "error_code": "STUDENT_DATA_NOT_FOUND",
                "nycu_id": current_user.nycu_id,
            },
        )

    scholarship_service = ScholarshipService(db)
    eligible_scholarships = await scholarship_service.get_eligible_scholarships(student, current_user.id)

    # Convert scholarship dictionaries to EligibleScholarshipResponse with rule details
    response_data = []
    for scholarship in eligible_scholarships:
        # Handle sub_type_list - ensure it's a list of dicts, not strings
        sub_type_list = scholarship.get("sub_type_list", [])
        if not sub_type_list:
            # If empty, provide a default "general" subtype as a dict
            sub_type_list = [{"value": "general", "label": "通用", "label_en": "General", "is_default": True}]

        response_item = EligibleScholarshipResponse(
            id=scholarship["id"],
            configuration_id=scholarship["configuration_id"],  # Pass through configuration ID
            code=scholarship["code"],
            name=scholarship["name"],
            name_en=scholarship.get("name_en") or scholarship["name"],
            eligible_sub_types=sub_type_list,
            academic_year=scholarship.get("academic_year"),
            semester=scholarship.get("semester"),
            application_cycle=scholarship.get("application_cycle", "semester"),
            description=scholarship.get("description"),
            description_en=scholarship.get("description_en"),
            amount=scholarship.get("amount", 0),
            currency=scholarship.get("currency", "TWD"),
            application_start_date=scholarship.get("application_start_date"),
            application_end_date=scholarship.get("application_end_date"),
            professor_review_start=scholarship.get("professor_review_start"),
            professor_review_end=scholarship.get("professor_review_end"),
            college_review_start=scholarship.get("college_review_start"),
            college_review_end=scholarship.get("college_review_end"),
            sub_type_selection_mode=scholarship.get("sub_type_selection_mode", "single"),
            terms_document_url=scholarship.get("terms_document_url"),
            passed=scholarship.get("passed", []),  # Rules passed from eligibility check
            warnings=[],  # Hide warnings from student view - they don't need to see these
            errors=scholarship.get("errors", []),  # Error messages from eligibility check
            created_at=scholarship.get("created_at"),
        )
        response_data.append(response_item)

    return ApiResponse(
        success=True,
        message="Eligible scholarships retrieved successfully",
        data=response_data,
    )


@router.get("/{id}")
async def get_scholarship_detail(id: int, db: AsyncSession = Depends(get_db)):
    """Get scholarship details"""
    stmt = select(ScholarshipType).options(joinedload(ScholarshipType.rules)).where(ScholarshipType.id == id)
    result = await db.execute(stmt)
    scholarship = result.unique().scalar_one_or_none()
    if not scholarship:
        raise HTTPException(status_code=404, detail="Scholarship not found")

    # Get active configuration for this scholarship to retrieve amount and other details
    config_stmt = (
        select(ScholarshipConfiguration)
        .where(
            ScholarshipConfiguration.scholarship_type_id == id,
            ScholarshipConfiguration.is_active.is_(True),
        )
        .order_by(
            ScholarshipConfiguration.academic_year.desc(),
            ScholarshipConfiguration.semester.desc(),
        )
        .limit(1)
    )

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
        "application_cycle": scholarship.application_cycle.value if scholarship.application_cycle else "semester",
        "sub_type_list": scholarship.sub_type_list or [],
        "amount": active_config.amount if active_config else 0,  # Get amount from active configuration
        "currency": active_config.currency if active_config else "TWD",  # Get currency from active configuration
        "whitelist_enabled": scholarship.whitelist_enabled if hasattr(scholarship, "whitelist_enabled") else False,
        "whitelist_student_ids": [
            student_id
            for subtype_list in (
                active_config.whitelist_student_ids.values()
                if active_config and active_config.whitelist_student_ids
                else []
            )
            for student_id in subtype_list
        ],
        "application_start_date": active_config.application_start_date if active_config else None,
        "application_end_date": active_config.application_end_date if active_config else None,
        "review_deadline": active_config.review_deadline if active_config else None,
        "professor_review_start": active_config.professor_review_start if active_config else None,
        "professor_review_end": active_config.professor_review_end if active_config else None,
        "college_review_start": active_config.college_review_start if active_config else None,
        "college_review_end": active_config.college_review_end if active_config else None,
        "sub_type_selection_mode": scholarship.sub_type_selection_mode.value
        if scholarship.sub_type_selection_mode
        else "single",
        "status": scholarship.status if hasattr(scholarship, "status") else "active",
        "requires_professor_recommendation": active_config.requires_professor_recommendation
        if active_config
        else False,
        "requires_college_review": active_config.requires_college_review if active_config else False,
        "review_workflow": scholarship.review_workflow if hasattr(scholarship, "review_workflow") else None,
        "auto_approval_rules": scholarship.auto_approval_rules if hasattr(scholarship, "auto_approval_rules") else None,
        "created_at": scholarship.created_at,
        "updated_at": scholarship.updated_at,
        "created_by": scholarship.created_by,
        "updated_by": scholarship.updated_by,
    }

    return ApiResponse(
        success=True,
        message="Scholarship details retrieved successfully",
        data=ScholarshipTypeResponse(**response_data),
    )


@router.post("/dev/reset-application-periods")
async def reset_application_periods(current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
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
            "scholarships_updated": len(scholarships),
        },
    )


@router.post("/dev/toggle-whitelist/{id}")
async def dev_toggle_scholarship_whitelist(
    id: int,
    enable: bool = True,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Toggle scholarship whitelist for testing (dev only)"""
    if not settings.debug:
        raise HTTPException(status_code=403, detail="Only available in development mode")
    stmt = select(ScholarshipType).where(ScholarshipType.id == id)
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
            "scholarship_id": id,
            "scholarship_name": scholarship.name,
            "whitelist_enabled": scholarship.whitelist_enabled,
        },
    )


@router.post("/dev/add-to-whitelist/{id}")
async def add_student_to_whitelist(
    id: int,
    student_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Add student to scholarship whitelist (dev only)"""
    if not settings.debug:
        raise HTTPException(status_code=403, detail="Only available in development mode")
    stmt = select(ScholarshipType).where(ScholarshipType.id == id)
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
            "scholarship_id": id,
            "student_id": student_id,
            "whitelist_size": len(scholarship.whitelist_student_ids),
        },
    )


@router.post("/{scholarship_type}/upload-terms")
async def upload_terms_document(
    scholarship_type: str,
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload terms and conditions document for a scholarship type

    Args:
        scholarship_type: Scholarship type code (e.g., 'undergraduate_freshman', 'direct_phd', 'phd')
        file: PDF, DOC, or DOCX file containing terms and conditions
        current_user: Current authenticated admin user
        db: Database session

    Returns:
        ApiResponse with uploaded file URL
    """
    # Validate filename security
    if not file.filename:
        raise HTTPException(status_code=400, detail="檔案名稱不得為空")

    # Check for path traversal attempts
    if ".." in file.filename or "/" in file.filename or "\\" in file.filename:
        raise HTTPException(status_code=400, detail="無效的檔案名稱：包含路徑字元")

    # Validate filename characters - block dangerous characters while allowing Unicode (including Chinese)
    dangerous_chars = ["|", "<", ">", ":", '"', "?", "*"]
    if any(char in file.filename for char in dangerous_chars):
        raise HTTPException(status_code=400, detail="檔案名稱包含無效字元")

    # Limit filename length
    if len(file.filename) > 255:
        raise HTTPException(status_code=400, detail="檔案名稱過長")

    # Validate file type
    allowed_extensions = [".pdf", ".doc", ".docx"]
    file_extension = None
    for ext in allowed_extensions:
        if file.filename and file.filename.lower().endswith(ext):
            file_extension = ext
            break

    if not file_extension:
        raise HTTPException(
            status_code=400, detail=f"Invalid file type. Allowed types: {', '.join(allowed_extensions)}"
        )

    # Find scholarship type
    stmt = select(ScholarshipType).where(ScholarshipType.code == scholarship_type)
    result = await db.execute(stmt)
    scholarship = result.scalar_one_or_none()

    if not scholarship:
        raise HTTPException(status_code=404, detail=f"Scholarship type '{scholarship_type}' not found")

    # Import MinIO service
    import io

    from app.services.minio_service import minio_service

    # Generate unique filename
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    object_name = f"terms/{scholarship_type}_terms_{timestamp}{file_extension}"

    try:
        # Read file content
        file_content = await file.read()
        file_size = len(file_content)

        # Validate file size
        from app.core.config import settings

        if file_size > settings.max_file_size:
            raise HTTPException(
                status_code=400,
                detail=f"檔案大小超過限制 ({settings.max_file_size / 1024 / 1024:.1f}MB)",
            )

        # Check for empty files
        if file_size == 0:
            raise HTTPException(status_code=400, detail="檔案不得為空")

        # Validate file content type with magic bytes
        import magic

        mime = magic.Magic(mime=True)
        actual_mime_type = mime.from_buffer(file_content[:2048])

        allowed_mime_types = {
            ".pdf": "application/pdf",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }

        expected_mime = allowed_mime_types.get(file_extension)
        if expected_mime and actual_mime_type != expected_mime:
            # Don't expose actual_mime_type in error message to prevent potential XSS
            raise HTTPException(
                status_code=400,
                detail=f"檔案內容與副檔名不符：預期 {expected_mime}",
            )

        # Upload file to MinIO using the client directly
        file_stream = io.BytesIO(file_content)

        minio_service.client.put_object(
            bucket_name=minio_service.default_bucket,
            object_name=object_name,
            data=file_stream,
            length=file_size,
            content_type=file.content_type or "application/octet-stream",
        )

        # Store only object_name (not full URL) - will be proxied through Next.js
        scholarship.terms_document_url = object_name
        scholarship.updated_by = current_user.id

        await db.commit()
        await db.refresh(scholarship)

        return ApiResponse(
            success=True,
            message="Terms document uploaded successfully",
            data={
                "scholarship_type": scholarship_type,
                "terms_document_url": object_name,  # Return object_name for frontend
                "filename": file.filename,
            },
        )

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to upload terms document: {str(e)}")


@router.get("/{scholarship_type}/terms")
async def get_terms_document(
    scholarship_type: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get terms document for a scholarship type and proxy download from MinIO

    Args:
        scholarship_type: Scholarship type code
        current_user: Current authenticated user
        db: Database session

    Returns:
        Streaming response with file content
    """
    import io

    from fastapi.responses import StreamingResponse

    # Find scholarship type
    stmt = select(ScholarshipType).where(ScholarshipType.code == scholarship_type)
    result = await db.execute(stmt)
    scholarship = result.scalar_one_or_none()

    if not scholarship or not scholarship.terms_document_url:
        raise HTTPException(status_code=404, detail="Terms document not found")

    # Import MinIO service
    from app.services.minio_service import minio_service

    try:
        # Download from MinIO
        response = minio_service.client.get_object(
            bucket_name=minio_service.default_bucket, object_name=scholarship.terms_document_url
        )

        # Read file content
        file_content = response.read()

        # Determine content type based on file extension
        content_type = "application/pdf"
        if scholarship.terms_document_url.endswith(".doc"):
            content_type = "application/msword"
        elif scholarship.terms_document_url.endswith(".docx"):
            content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

        # Return file as streaming response
        return StreamingResponse(
            io.BytesIO(file_content),
            media_type=content_type,
            headers={"Content-Disposition": f"inline; filename*=UTF-8''{scholarship_type}_terms.pdf"},
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve terms document: {str(e)}")


@router.patch("/{id}/whitelist")
async def toggle_scholarship_whitelist(
    id: int,
    request: WhitelistToggleRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Toggle scholarship whitelist enable/disable

    Args:
        id: Scholarship type ID
        request: Whitelist toggle request with enabled flag
        current_user: Current authenticated admin user
        db: Database session

    Returns:
        Updated scholarship type with whitelist status
    """
    # Get scholarship type
    stmt = select(ScholarshipType).where(ScholarshipType.id == id)
    result = await db.execute(stmt)
    scholarship = result.scalar_one_or_none()

    if not scholarship:
        raise HTTPException(status_code=404, detail=f"找不到ID為 {id} 的獎學金類型")

    # Update whitelist_enabled
    scholarship.whitelist_enabled = request.enabled
    scholarship.updated_by = current_user.id

    await db.commit()
    await db.refresh(scholarship)

    # Get active configuration for amount and other details
    config_stmt = (
        select(ScholarshipConfiguration)
        .where(
            ScholarshipConfiguration.scholarship_type_id == id,
            ScholarshipConfiguration.is_active.is_(True),
        )
        .order_by(
            ScholarshipConfiguration.academic_year.desc(),
            ScholarshipConfiguration.semester.desc(),
        )
        .limit(1)
    )

    config_result = await db.execute(config_stmt)
    active_config = config_result.scalar_one_or_none()

    # Convert to response format with proper enum serialization
    response_data = {
        "id": scholarship.id,
        "code": scholarship.code,
        "name": scholarship.name,
        "name_en": scholarship.name_en,
        "description": scholarship.description,
        "description_en": scholarship.description_en,
        "application_cycle": scholarship.application_cycle.value if scholarship.application_cycle else "semester",
        "sub_type_list": scholarship.sub_type_list or [],
        "amount": active_config.amount if active_config else 0,
        "currency": active_config.currency if active_config else "TWD",
        "whitelist_enabled": scholarship.whitelist_enabled,
        "whitelist_student_ids": [
            student_id
            for subtype_list in (
                active_config.whitelist_student_ids.values()
                if active_config and active_config.whitelist_student_ids
                else []
            )
            for student_id in subtype_list
        ],
        "application_start_date": active_config.application_start_date if active_config else None,
        "application_end_date": active_config.application_end_date if active_config else None,
        "review_deadline": active_config.review_deadline if active_config else None,
        "professor_review_start": active_config.professor_review_start if active_config else None,
        "professor_review_end": active_config.professor_review_end if active_config else None,
        "college_review_start": active_config.college_review_start if active_config else None,
        "college_review_end": active_config.college_review_end if active_config else None,
        "sub_type_selection_mode": scholarship.sub_type_selection_mode.value
        if scholarship.sub_type_selection_mode
        else "single",
        "status": scholarship.status if hasattr(scholarship, "status") else "active",
        "requires_professor_recommendation": active_config.requires_professor_recommendation
        if active_config
        else False,
        "requires_college_review": active_config.requires_college_review if active_config else False,
        "review_workflow": scholarship.review_workflow if hasattr(scholarship, "review_workflow") else None,
        "auto_approval_rules": scholarship.auto_approval_rules if hasattr(scholarship, "auto_approval_rules") else None,
        "created_at": scholarship.created_at,
        "updated_at": scholarship.updated_at,
        "created_by": scholarship.created_by,
        "updated_by": scholarship.updated_by,
    }

    return ApiResponse(
        success=True,
        message=f"白名單已{'啟用' if request.enabled else '停用'}",
        data=ScholarshipTypeResponse(**response_data),
    )
