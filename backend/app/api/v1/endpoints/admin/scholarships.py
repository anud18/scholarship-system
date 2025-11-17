"""
Admin Scholarships Management API Endpoints

Handles scholarship-related operations including:
- Scholarship applications listing
- Audit trail
- Sub-types management
- Sub-type configurations
- Permissions data
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.selectable import Select

from app.core.security import require_admin, require_scholarship_manager
from app.db.deps import get_db
from app.models.application import Application, ApplicationStatus
from app.models.scholarship import ScholarshipStatus, ScholarshipSubTypeConfig, ScholarshipType
from app.models.user import AdminScholarship, User
from app.schemas.application import ApplicationListResponse
from app.schemas.scholarship import (
    ScholarshipSubTypeConfigCreate,
    ScholarshipSubTypeConfigResponse,
    ScholarshipSubTypeConfigUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/scholarships/{scholarship_identifier}/applications")
async def get_applications_by_scholarship(
    scholarship_identifier: str = Path(..., regex=r"^(\d+|[a-z_]{1,50})$"),
    sub_type: Optional[str] = Query(None, description="Filter by sub-type"),
    status: Optional[str] = Query(None, description="Filter by status"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get applications for a specific scholarship type"""

    # Verify scholarship exists
    scholarship_stmt: Select[tuple[ScholarshipType]]

    try:
        scholarship_id = int(scholarship_identifier)
    except ValueError:
        scholarship_id = None

    if scholarship_id is not None:
        scholarship_stmt = select(ScholarshipType).where(ScholarshipType.id == scholarship_id)
    else:
        scholarship_stmt = select(ScholarshipType).where(ScholarshipType.code == scholarship_identifier)

    result = await db.execute(scholarship_stmt)
    scholarship = result.scalar_one_or_none()

    if not scholarship:
        raise HTTPException(status_code=404, detail="Scholarship not found")

    # Build query with joins and load files, configurations, and professor
    stmt = (
        select(Application, User)
        .options(
            selectinload(Application.files),
            selectinload(Application.scholarship_configuration),
            selectinload(Application.professor),
        )
        .join(User, Application.user_id == User.id)
        .where(Application.scholarship_type_id == scholarship.id)
    )

    # Default: exclude draft and deleted applications for admin view
    if status:
        stmt = stmt.where(Application.status == status)
    else:
        stmt = stmt.where(Application.status.notin_([ApplicationStatus.draft.value, ApplicationStatus.deleted.value]))

    if sub_type:
        # Filter by sub-type in scholarship_subtype_list
        stmt = stmt.where(Application.scholarship_subtype_list.contains([sub_type]))

    stmt = stmt.order_by(desc(Application.submitted_at))
    result = await db.execute(stmt)
    application_tuples = result.fetchall()

    # Convert to response format
    response_list = []
    for app_tuple in application_tuples:
        app, user = app_tuple

        # Process submitted_form_data to include file URLs
        processed_form_data = app.submitted_form_data or {}
        if processed_form_data and app.files:
            # Generate file access token
            from app.core.config import settings
            from app.core.security import create_access_token

            token_data = {"sub": str(current_user.id)}
            access_token = create_access_token(token_data)

            # Update documents in submitted_form_data with file URLs
            if "documents" in processed_form_data:
                existing_docs = processed_form_data["documents"]
                for existing_doc in existing_docs:
                    # Find matching file record
                    matching_file = next((f for f in app.files if f.file_type == existing_doc.get("document_id")), None)
                    if matching_file:
                        # Update existing file information with URLs
                        base_url = f"{settings.base_url}{settings.api_v1_str}"
                        existing_doc.update(
                            {
                                "file_id": matching_file.id,
                                "filename": matching_file.filename,
                                "original_filename": matching_file.original_filename,
                                "file_size": matching_file.file_size,
                                "mime_type": matching_file.mime_type or matching_file.content_type,
                                "file_path": f"{base_url}/files/applications/{app.id}/files/{matching_file.id}?token={access_token}",
                                "download_url": f"{base_url}/files/applications/{app.id}/files/{matching_file.id}/download?token={access_token}",
                                "is_verified": matching_file.is_verified,
                                "object_name": matching_file.object_name,
                            }
                        )

        # Create response data with proper field mapping
        app_data = {
            "id": app.id,
            "app_id": app.app_id,
            "user_id": app.user_id,
            # "student_id": app.student_id,  # Removed - student data now from external API
            "scholarship_type": scholarship.code,
            "scholarship_type_id": app.scholarship_type_id or scholarship.id,
            "scholarship_type_zh": scholarship.name,
            "scholarship_name": app.scholarship_configuration.config_name if app.scholarship_configuration else None,
            "amount": app.scholarship_configuration.amount if app.scholarship_configuration else None,
            "currency": app.scholarship_configuration.currency if app.scholarship_configuration else "TWD",
            "scholarship_subtype_list": app.scholarship_subtype_list or [],
            "status": app.status,
            "status_name": app.status_name,
            "academic_year": app.academic_year or str(datetime.now().year - 1911),  # Convert to ROC year
            "semester": app.semester.value if app.semester else "1",
            "student_data": app.student_data or {},
            "submitted_form_data": processed_form_data,
            "agree_terms": app.agree_terms or False,
            "professor_id": app.professor_id,
            "professor": (
                {
                    "id": app.professor.id,
                    "name": app.professor.name,
                    "nycu_id": app.professor.nycu_id,
                    "email": app.professor.email,
                }
                if app.professor
                else (
                    {
                        "id": app.professor_id,
                        "name": f"[教授不存在] ID: {app.professor_id}",
                        "nycu_id": None,
                        "email": None,
                        "error": True,
                    }
                    if app.professor_id
                    else None
                )
            ),
            "reviewer_id": app.reviewer_id,
            "final_approver_id": app.final_approver_id,
            "submitted_at": app.submitted_at,
            "reviewed_at": app.reviewed_at,
            "approved_at": app.approved_at,
            "created_at": app.created_at,
            "updated_at": app.updated_at,
            "meta_data": app.meta_data,
            # Additional fields for display - get from student_data first, fallback to user
            "student_name": (app.student_data.get("std_cname") if app.student_data else None)
            or (user.name if user else None),
            "student_no": (app.student_data.get("std_stdcode") if app.student_data else None)
            or getattr(user, "nycu_id", None),
            "student_email": (app.student_data.get("com_email") if app.student_data else None)
            or (user.email if user else None),
            "days_waiting": None,
            # Include scholarship configuration for professor review settings
            "scholarship_configuration": (
                {
                    "requires_professor_recommendation": (
                        app.scholarship_configuration.requires_professor_recommendation
                        if app.scholarship_configuration
                        else False
                    ),
                    "requires_college_review": (
                        app.scholarship_configuration.requires_college_review
                        if app.scholarship_configuration
                        else False
                    ),
                    "config_name": app.scholarship_configuration.config_name if app.scholarship_configuration else None,
                }
                if app.scholarship_configuration
                else None
            ),
        }

        # Calculate days waiting
        if app.submitted_at:
            now = datetime.now(timezone.utc)
            submitted_time = app.submitted_at

            if submitted_time.tzinfo is None:
                submitted_time = submitted_time.replace(tzinfo=timezone.utc)

            days_diff = (now - submitted_time).days
            app_data["days_waiting"] = max(0, days_diff)

        response_list.append(ApplicationListResponse.model_validate(app_data))

    return {
        "success": True,
        "message": f"Applications for scholarship {scholarship.code} retrieved successfully",
        "data": response_list,
    }


@router.get("/scholarships/{scholarship_identifier}/audit-trail")
async def get_scholarship_audit_trail(
    scholarship_identifier: str = Path(..., regex=r"^(\d+|[a-z_]{1,50})$"),
    action_filter: Optional[str] = Query(None, description="Filter by action type"),
    limit: int = Query(500, le=1000, description="Maximum number of audit logs to return"),
    offset: int = Query(0, ge=0, description="Number of audit logs to skip"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Get audit trail for all applications of a specific scholarship type (staff only)

    Returns all operations performed on applications of this scholarship type, including:
    - Operations on deleted applications (which don't appear in the applications list)
    - Who performed each action and when
    - Application context (app_id, student name, etc.)
    """
    # Verify scholarship exists
    scholarship_stmt: Select[tuple[ScholarshipType]]

    try:
        scholarship_id = int(scholarship_identifier)
    except ValueError:
        scholarship_id = None

    if scholarship_id is not None:
        scholarship_stmt = select(ScholarshipType).where(ScholarshipType.id == scholarship_id)
    else:
        scholarship_stmt = select(ScholarshipType).where(ScholarshipType.code == scholarship_identifier)

    result = await db.execute(scholarship_stmt)
    scholarship = result.scalar_one_or_none()

    if not scholarship:
        raise HTTPException(status_code=404, detail="Scholarship not found")

    # Get audit trail using the service
    from app.services.application_audit_service import ApplicationAuditService

    audit_service = ApplicationAuditService(db)
    audit_logs = await audit_service.get_scholarship_audit_trail(
        scholarship_type_id=scholarship.id, limit=limit, offset=offset, action_filter=action_filter
    )

    # Format timestamps for JSON response
    formatted_logs = []
    for log in audit_logs:
        log_copy = dict(log)
        if log_copy.get("created_at"):
            log_copy["created_at"] = log_copy["created_at"].isoformat()
        formatted_logs.append(log_copy)

    return {
        "success": True,
        "message": f"Retrieved {len(formatted_logs)} audit log entries for scholarship {scholarship.code}",
        "data": formatted_logs,
    }


@router.get("/scholarships/{scholarship_code}/sub-types")
async def get_scholarship_sub_types(
    scholarship_code: str = Path(..., regex=r"^[a-z_]{1,50}$"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get sub-types for a specific scholarship"""

    # Get scholarship
    stmt = select(ScholarshipType).where(ScholarshipType.code == scholarship_code)
    result = await db.execute(stmt)
    scholarship = result.scalar_one_or_none()

    if not scholarship:
        raise HTTPException(status_code=404, detail="Scholarship not found")

    sub_types = scholarship.sub_type_list or []

    # Return sub-types with statistics
    sub_type_stats = []
    for sub_type in sub_types:
        # Get applications for this sub-type
        stmt = select(Application).where(
            Application.scholarship_type_id == scholarship.id, Application.scholarship_subtype_list.contains([sub_type])
        )
        result = await db.execute(stmt)
        applications = result.scalars().all()

        total_applications = len(applications)
        pending_review = len(
            [
                app
                for app in applications
                if app.status
                in [
                    ApplicationStatus.submitted.value,
                    ApplicationStatus.under_review.value,
                ]
            ]
        )

        # Calculate average wait time
        completed_apps = [
            app
            for app in applications
            if app.status in [ApplicationStatus.approved.value, ApplicationStatus.rejected.value]
            and app.submitted_at
            and app.reviewed_at
        ]

        avg_wait_days = 0
        if completed_apps:
            total_days = sum([(app.reviewed_at - app.submitted_at).days for app in completed_apps])
            avg_wait_days = round(total_days / len(completed_apps), 1)

        sub_type_stats.append(
            {
                "sub_type": sub_type,
                "total_applications": total_applications,
                "pending_review": pending_review,
                "avg_wait_days": avg_wait_days,
            }
        )

    return {
        "success": True,
        "message": f"Sub-type statistics for scholarship {scholarship_code} retrieved successfully",
        "data": sub_type_stats,
    }


@router.get("/scholarships/sub-type-translations")
async def get_sub_type_translations(current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Get sub-type name translations for all supported languages from database"""

    # Get all active scholarship types with their sub-type configurations
    stmt = (
        select(ScholarshipType)
        .options(selectinload(ScholarshipType.sub_type_configs))
        .where(ScholarshipType.status == ScholarshipStatus.active.value)
    )
    result = await db.execute(stmt)
    scholarships = result.scalars().all()

    # Build translations from database
    translations = {"zh": {}, "en": {}}

    for scholarship in scholarships:
        # Get sub-type translations for this scholarship
        scholarship_translations = scholarship.get_sub_type_translations()

        # Merge into global translations
        for lang in ["zh", "en"]:
            translations[lang].update(scholarship_translations[lang])

    return {
        "success": True,
        "message": "Sub-type translations retrieved successfully from database",
        "data": translations,
    }


# === 子類型配置管理 API === #


@router.get("/scholarships/{scholarship_id}/sub-type-configs")
async def get_scholarship_sub_type_configs(
    scholarship_id: int, current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """Get sub-type configurations for a specific scholarship"""

    # Get scholarship with sub-type configurations
    stmt = (
        select(ScholarshipType)
        .options(selectinload(ScholarshipType.sub_type_configs))
        .where(ScholarshipType.id == scholarship_id)
    )
    result = await db.execute(stmt)
    scholarship = result.scalar_one_or_none()

    if not scholarship:
        raise HTTPException(status_code=404, detail="Scholarship not found")

    # Get sub-type configurations
    configs = []

    # 獲取已配置的子類型
    for config in scholarship.get_active_sub_type_configs():
        config_dict = {
            "id": config.id,
            "scholarship_type_id": config.scholarship_type_id,
            "sub_type_code": config.sub_type_code,
            "name": config.name,
            "name_en": config.name_en,
            "description": config.description,
            "description_en": config.description_en,
            "amount": config.amount,
            "currency": config.currency,
            "display_order": config.display_order,
            "is_active": config.is_active,
            "effective_amount": config.effective_amount,
            "created_at": config.created_at,
            "updated_at": config.updated_at,
        }
        configs.append(ScholarshipSubTypeConfigResponse.model_validate(config_dict))

    # 為 general 子類型添加預設配置（如果沒有配置且在子類型列表中）
    if "general" in scholarship.sub_type_list:
        general_config = scholarship.get_sub_type_config("general")
        if not general_config:
            # 創建預設的 general 配置
            now = datetime.now(timezone.utc)

            config_dict = {
                "id": 0,  # 虛擬 ID
                "scholarship_type_id": scholarship.id,
                "sub_type_code": "general",
                "name": "一般獎學金",
                "name_en": "General Scholarship",
                "description": "一般獎學金",
                "description_en": "General Scholarship",
                "amount": None,
                "currency": scholarship.currency,
                "display_order": 0,
                "is_active": True,
                "effective_amount": scholarship.amount,
                "created_at": now,
                "updated_at": now,
            }
            configs.append(ScholarshipSubTypeConfigResponse.model_validate(config_dict))

    return {"success": True, "message": "Sub-type configurations retrieved successfully", "data": configs}


@router.post("/scholarships/{scholarship_id}/sub-type-configs")
async def create_sub_type_config(
    scholarship_id: int,
    config_data: ScholarshipSubTypeConfigCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create new sub-type configuration for a scholarship"""

    # Get scholarship with sub-type configurations
    stmt = (
        select(ScholarshipType)
        .options(selectinload(ScholarshipType.sub_type_configs))
        .where(ScholarshipType.id == scholarship_id)
    )
    result = await db.execute(stmt)
    scholarship = result.scalar_one_or_none()

    if not scholarship:
        raise HTTPException(status_code=404, detail="Scholarship not found")

    # Validate sub_type_code
    if config_data.sub_type_code not in scholarship.sub_type_list:
        raise HTTPException(status_code=400, detail="Invalid sub_type_code for this scholarship")

    # Prevent creating general sub-type configurations
    if config_data.sub_type_code == "general":
        raise HTTPException(
            status_code=400, detail="Cannot create configuration for 'general' sub-type. It uses default values."
        )

    # Check if config already exists
    existing = await db.execute(
        select(ScholarshipSubTypeConfig).where(
            ScholarshipSubTypeConfig.scholarship_type_id == scholarship_id,
            ScholarshipSubTypeConfig.sub_type_code == config_data.sub_type_code,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Sub-type configuration already exists")

    # Create new config
    config = ScholarshipSubTypeConfig(
        scholarship_type_id=scholarship_id,
        created_by=current_user.id,
        updated_by=current_user.id,
        **config_data.model_dump(),
    )

    db.add(config)
    await db.commit()
    await db.refresh(config)

    config_dict = {
        "id": config.id,
        "scholarship_type_id": config.scholarship_type_id,
        "sub_type_code": config.sub_type_code,
        "name": config.name,
        "name_en": config.name_en,
        "description": config.description,
        "description_en": config.description_en,
        "amount": config.amount,
        "currency": config.currency,
        "display_order": config.display_order,
        "is_active": config.is_active,
        "effective_amount": config.effective_amount,
        "created_at": config.created_at,
        "updated_at": config.updated_at,
    }

    return {
        "success": True,
        "message": "Sub-type configuration created successfully",
        "data": ScholarshipSubTypeConfigResponse.model_validate(config_dict),
    }


@router.put("/scholarships/sub-type-configs/{id}")
async def update_sub_type_config(
    id: int,
    config_data: ScholarshipSubTypeConfigUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update sub-type configuration"""

    # Get config
    stmt = select(ScholarshipSubTypeConfig).where(ScholarshipSubTypeConfig.id == id)
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail="Sub-type configuration not found")

    # Update only fields defined in the Pydantic schema to prevent mass assignment
    # This automatically stays in sync with schema changes
    allowed_fields = set(config_data.model_fields.keys())

    update_data = config_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field in allowed_fields and hasattr(config, field):
            setattr(config, field, value)

    config.updated_by = current_user.id
    await db.commit()
    await db.refresh(config)

    config_dict = {
        "id": config.id,
        "scholarship_type_id": config.scholarship_type_id,
        "sub_type_code": config.sub_type_code,
        "name": config.name,
        "name_en": config.name_en,
        "description": config.description,
        "description_en": config.description_en,
        "amount": config.amount,
        "currency": config.currency,
        "display_order": config.display_order,
        "is_active": config.is_active,
        "effective_amount": config.effective_amount,
        "created_at": config.created_at,
        "updated_at": config.updated_at,
    }

    return {
        "success": True,
        "message": "Sub-type configuration updated successfully",
        "data": ScholarshipSubTypeConfigResponse.model_validate(config_dict),
    }


@router.delete("/scholarships/sub-type-configs/{id}")
async def delete_sub_type_config(
    id: int, current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """Delete sub-type configuration (soft delete by setting is_active=False)"""

    # Get config
    stmt = select(ScholarshipSubTypeConfig).where(ScholarshipSubTypeConfig.id == id)
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sub-type configuration not found")

    # Soft delete
    config.is_active = False
    config.updated_by = current_user.id
    await db.commit()

    return {"success": True, "message": "Sub-type configuration deleted successfully", "data": None}


# === 獎學金權限管理相關 API === #


@router.get("/scholarships/all-for-permissions")
async def get_all_scholarships_for_permissions(
    current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """Get all scholarships for permission management (admin only)"""

    # Get all active scholarships
    stmt = (
        select(ScholarshipType)
        .where(ScholarshipType.status == ScholarshipStatus.active.value)
        .order_by(ScholarshipType.name)
    )

    result = await db.execute(stmt)
    scholarships = result.scalars().all()

    # Convert to response format
    scholarship_list = []
    for scholarship in scholarships:
        scholarship_list.append(
            {"id": scholarship.id, "name": scholarship.name, "name_en": scholarship.name_en, "code": scholarship.code}
        )

    return {
        "success": True,
        "message": f"Retrieved {len(scholarship_list)} scholarships for permission management",
        "data": scholarship_list,
    }


@router.get("/scholarships/my-scholarships")
async def get_my_scholarships(
    current_user: User = Depends(require_scholarship_manager), db: AsyncSession = Depends(get_db)
):
    """Get scholarships that the current user has permission to manage"""

    logger.info(f"get_my_scholarships called by user {current_user.id} role {current_user.role}")

    if current_user.is_super_admin():
        # Super admins can see all scholarships
        logger.info("User is super admin, getting all active scholarships")
        stmt = (
            select(ScholarshipType)
            .where(ScholarshipType.status == ScholarshipStatus.active.value)
            .order_by(ScholarshipType.name)
        )

        result = await db.execute(stmt)
        scholarships = result.scalars().all()
        logger.info(f"Found {len(scholarships)} active scholarships for super admin")
    else:
        # Regular admins and college users can only see assigned scholarships
        logger.info(f"User is {current_user.role}, getting assigned scholarships")
        stmt = (
            select(ScholarshipType)
            .join(AdminScholarship, ScholarshipType.id == AdminScholarship.scholarship_id)
            .where(
                AdminScholarship.admin_id == current_user.id, ScholarshipType.status == ScholarshipStatus.active.value
            )
            .order_by(ScholarshipType.name)
        )

        result = await db.execute(stmt)
        scholarships = result.scalars().all()
        logger.info(f"Found {len(scholarships)} assigned scholarships for user")

    # Convert to response format
    scholarship_list = []
    for scholarship in scholarships:
        scholarship_list.append(
            {
                "id": scholarship.id,
                "name": scholarship.name,
                "name_en": scholarship.name_en,
                "code": scholarship.code,
                "application_cycle": scholarship.application_cycle.value if scholarship.application_cycle else None,
                "status": scholarship.status,  # status is also a string, not an enum in this model
                "whitelist_enabled": scholarship.whitelist_enabled,  # 申請白名單開關狀態
                "sub_type_list": scholarship.sub_type_list or [],  # 子獎學金類型列表
            }
        )

    return {
        "success": True,
        "message": f"Retrieved {len(scholarship_list)} scholarships for current user",
        "data": scholarship_list,
    }


# ============================
# Scholarship Rules Management
# ============================
