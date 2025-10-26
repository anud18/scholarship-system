"""
Scholarship Configuration Management API endpoints
Clean, database-driven approach for dynamic scholarship configuration management
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import and_
from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.core.security import require_admin, require_staff
from app.db.deps import get_db

# Student model removed - student data now fetched from external API
from app.models.application import Application, ApplicationStatus
from app.models.enums import Semester
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import AdminScholarship, User
from app.schemas.response import ApiResponse
from app.schemas.scholarship_configuration import (
    WhitelistBatchAddRequest,
    WhitelistBatchRemoveRequest,
    WhitelistImportResult,
    WhitelistResponse,
    WhitelistStudentInfo,
)
from app.services.whitelist_excel_service import whitelist_excel_service

router = APIRouter()


# Utility functions
def taiwan_to_western_year(taiwan_year: int) -> int:
    """Convert Taiwan calendar year (民國年) to Western calendar year"""
    return taiwan_year + 1911


def western_to_taiwan_year(western_year: int) -> int:
    """Convert Western calendar year to Taiwan calendar year (民國年)"""
    return western_year - 1911


async def get_user_accessible_scholarship_ids(user: User, db: AsyncSession) -> List[int]:
    """Get scholarship IDs that the user can access based on their role and permissions"""
    if user.is_super_admin():
        # Super admins can access all scholarships
        stmt = select(ScholarshipType.id)
        result = await db.execute(stmt)
        return result.scalars().all()

    elif user.is_admin():
        # Regular admins can only access scholarships they have permissions for
        stmt = select(AdminScholarship.scholarship_id).where(AdminScholarship.admin_id == user.id)
        result = await db.execute(stmt)
        return result.scalars().all()

    else:
        # Other roles have no access
        return []


# Core API endpoints


@router.get("/available-semesters")
async def get_available_semesters(
    scholarship_code: Optional[str] = Query(None, description="Filter periods by specific scholarship code"),
    quota_management_mode: Optional[str] = Query(
        None, description="Filter periods by quota management mode (e.g., 'matrix')"
    ),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get list of available academic periods from scholarship configurations"""

    try:
        # Get scholarship IDs user can access
        accessible_scholarship_ids = await get_user_accessible_scholarship_ids(current_user, db)

        if not accessible_scholarship_ids:
            return ApiResponse(success=True, message="No accessible scholarship configurations found", data=[])

        # Build query conditions
        conditions = [
            ScholarshipConfiguration.is_active.is_(True),
            ScholarshipConfiguration.scholarship_type_id.in_(accessible_scholarship_ids),
        ]

        # If scholarship_code filter is provided, add it to conditions
        if scholarship_code:
            scholarship_stmt = select(ScholarshipType.id).where(
                and_(ScholarshipType.code == scholarship_code, ScholarshipType.id.in_(accessible_scholarship_ids))
            )
            scholarship_result = await db.execute(scholarship_stmt)
            scholarship_id = scholarship_result.scalar_one_or_none()

            if not scholarship_id:
                return ApiResponse(
                    success=True, message=f"No accessible scholarship found with code: {scholarship_code}", data=[]
                )

            conditions.append(ScholarshipConfiguration.scholarship_type_id == scholarship_id)

        # If quota_management_mode filter is provided, add it to conditions
        if quota_management_mode:
            from app.models.enums import QuotaManagementMode

            try:
                # Find the enum by its value, not by its name
                mode_enum = None
                for mode in QuotaManagementMode:
                    if mode.value == quota_management_mode:
                        mode_enum = mode
                        break

                if mode_enum is None:
                    return ApiResponse(
                        success=False, message=f"Invalid quota management mode: {quota_management_mode}", data=[]
                    )

                conditions.append(ScholarshipConfiguration.quota_management_mode == mode_enum)
            except Exception:
                return ApiResponse(
                    success=False, message=f"Invalid quota management mode: {quota_management_mode}", data=[]
                )

        # Query for unique academic years and semesters from configurations
        stmt = (
            select(ScholarshipConfiguration.academic_year, ScholarshipConfiguration.semester)
            .where(and_(*conditions))
            .distinct()
        )

        result = await db.execute(stmt)
        config_periods = result.fetchall()

        # Build period list
        all_periods = []

        for academic_year, semester in config_periods:
            if semester:
                # Semester-based scholarship
                semester_num = "1" if semester.value == "first" else "2"
                all_periods.append(f"{academic_year}-{semester_num}")
            else:
                # Academic year-based scholarship
                all_periods.append(str(academic_year))

        # Sort by year descending, then by semester descending
        def sort_key(period):
            if "-" in period:
                year, sem = period.split("-")
                return (int(year), int(sem))
            else:
                return (int(period), 9)  # Academic year gets higher priority

        all_periods.sort(key=sort_key, reverse=True)

        # Remove duplicates while preserving order
        unique_periods = []
        seen = set()
        for period in all_periods:
            if period not in seen:
                unique_periods.append(period)
                seen.add(period)

        return ApiResponse(
            success=True, message=f"Retrieved {len(unique_periods)} available periods", data=unique_periods
        )

    except Exception as e:
        import logging
        import traceback

        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_available_semesters: {type(e).__name__}: {str(e)}", exc_info=True)
        logger.error(f"Full traceback: {traceback.format_exc()}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve available semesters: {str(e)}",
        )


@router.get("/matrix-quota-status/{period}")
async def get_matrix_quota_status(
    period: str,  # Academic year (e.g., "114") or semester (e.g., "114-1")
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get matrix quota status for PhD scholarships"""

    try:
        # Parse period
        if "-" in period:
            academic_year_str, semester_str = period.split("-")
            academic_year = int(academic_year_str)
            semester = Semester.first if semester_str == "1" else Semester.second
        else:
            academic_year = int(period)
            semester = None

        # Get accessible scholarship IDs
        accessible_scholarship_ids = await get_user_accessible_scholarship_ids(current_user, db)

        # Find PhD scholarship type
        if not accessible_scholarship_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="未找到可存取的獎學金")

        phd_stmt = select(ScholarshipType).where(
            and_(ScholarshipType.code == "phd", ScholarshipType.id.in_(accessible_scholarship_ids))
        )
        phd_result = await db.execute(phd_stmt)
        phd_scholarship = phd_result.scalar_one_or_none()

        if not phd_scholarship:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="PhD scholarship not found or not accessible"
            )

        # Get configuration for this period
        config_stmt = (
            select(ScholarshipConfiguration)
            .where(
                and_(
                    ScholarshipConfiguration.scholarship_type_id == phd_scholarship.id,
                    ScholarshipConfiguration.academic_year == academic_year,
                    ScholarshipConfiguration.semester == semester
                    if semester
                    else ScholarshipConfiguration.semester.is_(None),
                    ScholarshipConfiguration.is_active.is_(True),
                )
            )
            .options(selectinload(ScholarshipConfiguration.scholarship_type))
        )

        config_result = await db.execute(config_stmt)
        config = config_result.scalar_one_or_none()

        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No active configuration found for PhD scholarship in period {period}",
            )

        # Get matrix quotas from configuration
        matrix_quotas = config.quotas or {}

        if not matrix_quotas:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No matrix quota configuration found")

        # Get application usage data with single aggregated query (fixes N+1 problem)
        phd_quotas = {}
        grand_total_quota = 0
        grand_total_used = 0

        # Get sub-types from the scholarship type configuration
        sub_types = phd_scholarship.sub_type_list or ["nstc", "moe_1w", "moe_2w"]

        # Get college codes from the quota configuration
        college_codes = set()
        for sub_type_quotas in matrix_quotas.values():
            if isinstance(sub_type_quotas, dict):
                college_codes.update(sub_type_quotas.keys())
        college_codes = sorted(list(college_codes))

        # Get usage data efficiently from applications with student_data JSON field
        usage_data = {}

        # Query applications for this scholarship type and period
        app_stmt = select(Application).where(
            and_(
                Application.scholarship_type_id == phd_scholarship.id,
                Application.academic_year == academic_year,
                Application.semester == semester if semester else Application.semester.is_(None),
                Application.status.in_(["allocated", "submitted", "professor_reviewed", "college_reviewed"]),
            )
        )

        app_result = await db.execute(app_stmt)
        applications = app_result.scalars().all()

        # Calculate usage per college
        for app in applications:
            if not app.student_data or not isinstance(app.student_data, dict):
                continue

            # Get college code from student data
            # std_academyno is the correct field from API, prioritize it
            college_code = (
                app.student_data.get("std_academyno")
                or app.student_data.get("academy_code")
                or app.student_data.get("college_code")
                or app.student_data.get("std_college")
            )

            if not college_code:
                continue

            # Normalize college code to uppercase
            college_code = college_code.upper()

            # Initialize college usage if not exists
            if college_code not in usage_data:
                usage_data[college_code] = {"used": 0, "applications": 0}

            # Count allocated applications as "used"
            if app.status == "allocated":
                usage_data[college_code]["used"] += 1

            # Count all applications
            usage_data[college_code]["applications"] += 1

        # Build quota matrix using pre-fetched usage data
        for sub_type in sub_types:
            phd_quotas[sub_type] = {}
            sub_type_quotas = matrix_quotas.get(sub_type, {})

            for college in college_codes:
                total_quota = sub_type_quotas.get(college, 0)

                # Get usage from pre-fetched data
                college_usage = usage_data.get(college, {"used": 0, "applications": 0})
                used = college_usage["used"]
                applications = college_usage["applications"]

                phd_quotas[sub_type][college] = {
                    "total_quota": total_quota,
                    "used": used,
                    "available": max(0, total_quota - used),
                    "applications": applications,
                }

                grand_total_quota += total_quota
                grand_total_used += used

        # Build response
        response_data = {
            "academic_year": str(academic_year),
            "period_type": "semester" if semester else "academic_year",
            "phd_quotas": phd_quotas,
            "grand_total": {
                "total_quota": grand_total_quota,
                "total_used": grand_total_used,
                "total_available": grand_total_quota - grand_total_used,
            },
        }

        return ApiResponse(success=True, message="Matrix quota status retrieved successfully", data=response_data)

    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid period format: {period}")
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_matrix_quota_status: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve matrix quota status: {str(e)}",
        )


@router.put("/matrix-quota")
async def update_matrix_quota(
    sub_type: str = Body(...),
    college: str = Body(...),
    new_quota: int = Body(...),
    academic_year: Optional[int] = Body(None),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update matrix quota for specific sub-type and college"""

    if new_quota < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="配額不能為負數")

    if new_quota > 1000:  # Reasonable upper bound for scholarship quotas
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="配額數值過大（最大值：1000）")

    try:
        # Get accessible scholarship IDs
        accessible_scholarship_ids = await get_user_accessible_scholarship_ids(current_user, db)

        # Find PhD scholarship
        if not accessible_scholarship_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="未找到可存取的獎學金")

        phd_stmt = select(ScholarshipType).where(
            and_(ScholarshipType.code == "phd", ScholarshipType.id.in_(accessible_scholarship_ids))
        )
        phd_result = await db.execute(phd_stmt)
        phd_scholarship = phd_result.scalar_one_or_none()

        if not phd_scholarship:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="您沒有管理博士獎學金配額的權限")

        # Get the configuration for the specified academic year, or the most recent if not specified
        config_conditions = [
            ScholarshipConfiguration.scholarship_type_id == phd_scholarship.id,
            ScholarshipConfiguration.is_active.is_(True),
        ]

        if academic_year:
            config_conditions.append(ScholarshipConfiguration.academic_year == academic_year)

        config_stmt = (
            select(ScholarshipConfiguration)
            .where(and_(*config_conditions))
            .order_by(ScholarshipConfiguration.academic_year.desc())
            .limit(1)
        )

        config_result = await db.execute(config_stmt)
        config = config_result.scalar_one_or_none()

        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="No active configuration found for PhD scholarship"
            )

        # Validate sub_type and college
        valid_sub_types = phd_scholarship.sub_type_list or ["nstc", "moe_1w", "moe_2w"]
        if sub_type not in valid_sub_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid sub_type '{sub_type}'. Valid values: {valid_sub_types}",
            )

        # Initialize quota structure if needed
        if not config.quotas:
            config.quotas = {}

        if sub_type not in config.quotas:
            config.quotas[sub_type] = {}

        # Get old quota
        old_quota = config.quotas[sub_type].get(college, 0)

        # Update quota
        config.quotas[sub_type][college] = new_quota

        # Calculate totals
        sub_type_total = sum(config.quotas[sub_type].values())
        grand_total = sum(sum(colleges.values()) for colleges in config.quotas.values() if isinstance(colleges, dict))

        # Update total quota
        config.total_quota = grand_total
        config.updated_by = current_user.id

        # Mark as modified for SQLAlchemy
        flag_modified(config, "quotas")

        await db.commit()
        await db.refresh(config)

        return ApiResponse(
            success=True,
            message=f"Matrix quota updated: {sub_type} - {college}: {old_quota} → {new_quota}",
            data={
                "sub_type": sub_type,
                "college": college,
                "old_quota": old_quota,
                "new_quota": new_quota,
                "sub_type_total": sub_type_total,
                "grand_total": grand_total,
                "updated_by": current_user.id,
                "id": config.id,
            },
        )

    except Exception as e:
        await db.rollback()
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error in update_matrix_quota: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update matrix quota: {str(e)}"
        )


@router.get("/colleges")
async def get_colleges(current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Get college configurations from database"""

    try:
        # Use centralized college mappings instead of querying non-existent Student model
        from app.core.college_mappings import get_all_colleges

        colleges = get_all_colleges()

        return ApiResponse(success=True, message=f"Retrieved {len(colleges)} colleges", data=colleges)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve colleges: {str(e)}"
        )


@router.get("/scholarship-types")
async def get_scholarship_types(current_user: User = Depends(require_staff), db: AsyncSession = Depends(get_db)):
    """Get scholarship types that the user has access to"""

    try:
        # Get accessible scholarship IDs
        accessible_scholarship_ids = await get_user_accessible_scholarship_ids(current_user, db)

        if not accessible_scholarship_ids:
            return ApiResponse(success=True, message="No accessible scholarship types found", data=[])

        # Get scholarship types with their configurations
        stmt = (
            select(ScholarshipType)
            .where(and_(ScholarshipType.id.in_(accessible_scholarship_ids), ScholarshipType.status == "active"))
            .options(selectinload(ScholarshipType.sub_type_configs))
        )

        result = await db.execute(stmt)
        scholarship_types = result.scalars().all()

        type_configs = []
        for stype in scholarship_types:
            # Get latest active configuration
            config_stmt = (
                select(ScholarshipConfiguration)
                .where(
                    and_(
                        ScholarshipConfiguration.scholarship_type_id == stype.id,
                        ScholarshipConfiguration.is_active.is_(True),
                    )
                )
                .order_by(ScholarshipConfiguration.academic_year.desc())
                .limit(1)
            )

            config_result = await db.execute(config_stmt)
            latest_config = config_result.scalar_one_or_none()

            type_config = {
                "code": stype.code,
                "name": stype.name,
                "name_en": stype.name_en or stype.name,
                "sub_types": stype.sub_type_list or [],
                "has_quota_limit": latest_config.has_quota_limit if latest_config else False,
                "has_college_quota": latest_config.has_college_quota if latest_config else False,
                "quota_management_mode": latest_config.quota_management_mode.value
                if latest_config and latest_config.quota_management_mode
                else "none",
                "application_period": stype.application_cycle.value if stype.application_cycle else "semester",
                "description": latest_config.description if latest_config else stype.description or "",
            }
            type_configs.append(type_config)

        return ApiResponse(success=True, message=f"Retrieved {len(type_configs)} scholarship types", data=type_configs)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve scholarship types: {str(e)}"
        )


@router.get("/overview/{period}")
async def get_quota_overview(
    period: str,  # Academic year or semester (e.g., "114" or "114-1")
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get comprehensive quota overview for accessible scholarship types"""

    try:
        # Parse period
        if "-" in period:
            academic_year_str, semester_str = period.split("-")
            academic_year = int(academic_year_str)
            semester = Semester.first if semester_str == "1" else Semester.second
        else:
            academic_year = int(period)
            semester = None

        # Get accessible scholarship IDs
        accessible_scholarship_ids = await get_user_accessible_scholarship_ids(current_user, db)

        if not accessible_scholarship_ids:
            return ApiResponse(success=True, message="No accessible scholarships found", data=[])

        # Get configurations for this period
        stmt = (
            select(ScholarshipConfiguration)
            .where(
                and_(
                    ScholarshipConfiguration.scholarship_type_id.in_(accessible_scholarship_ids),
                    ScholarshipConfiguration.academic_year == academic_year,
                    ScholarshipConfiguration.semester == semester
                    if semester
                    else ScholarshipConfiguration.semester.is_(None),
                    ScholarshipConfiguration.is_active.is_(True),
                )
            )
            .options(selectinload(ScholarshipConfiguration.scholarship_type))
        )

        result = await db.execute(stmt)
        configurations = result.scalars().all()

        overview_data = []

        for config in configurations:
            stype = config.scholarship_type

            # Build sub-type data
            sub_types = []
            for sub_type_code in stype.sub_type_list or ["general"]:
                # Calculate allocated quota for this sub-type
                allocated_quota = 0

                if config.has_college_quota and config.quotas:
                    if sub_type_code in config.quotas:
                        sub_type_quotas = config.quotas[sub_type_code]
                        if isinstance(sub_type_quotas, dict):
                            allocated_quota = sum(sub_type_quotas.values())
                        else:
                            allocated_quota = sub_type_quotas
                elif config.total_quota:
                    # Split total quota among sub-types
                    num_sub_types = len(stype.sub_type_list or ["general"])
                    allocated_quota = config.total_quota // num_sub_types if num_sub_types > 0 else config.total_quota

                # Get actual usage from applications
                quota_query = select(sa_func.count(Application.id)).where(
                    and_(
                        Application.scholarship_type_id == stype.id,
                        Application.config_code == config.config_code,
                        Application.sub_type == sub_type_code,
                        Application.status.in_([ApplicationStatus.approved, ApplicationStatus.FUNDED]),
                    )
                )
                used_quota_result = await db.execute(quota_query)
                used_quota = used_quota_result.scalar() or 0

                # Get total applications count (all statuses except rejected/withdrawn)
                total_apps_query = select(sa_func.count(Application.id)).where(
                    and_(
                        Application.scholarship_type_id == stype.id,
                        Application.config_code == config.config_code,
                        Application.sub_type == sub_type_code,
                        Application.status.not_in([ApplicationStatus.rejected, ApplicationStatus.withdrawn]),
                    )
                )
                total_apps_result = await db.execute(total_apps_query)
                applications_count = total_apps_result.scalar() or 0

                sub_types.append(
                    {
                        "main_type": stype.code,
                        "sub_type": sub_type_code,
                        "scholarship_name": sub_type_code.replace("_", " ").title(),
                        "allocated_quota": allocated_quota,
                        "used_quota": used_quota,
                        "remaining_quota": max(0, allocated_quota - used_quota),
                        "applications_count": applications_count,
                        "application_period": stype.application_cycle.value if stype.application_cycle else "semester",
                        "current_period": period,
                    }
                )

            overview_data.append(
                {
                    "code": stype.code,
                    "name": stype.name,
                    "name_en": stype.name_en or stype.name,
                    "has_quota_limit": config.has_quota_limit,
                    "has_college_quota": config.has_college_quota,
                    "quota_management_mode": config.quota_management_mode.value
                    if config.quota_management_mode
                    else "none",
                    "application_period": stype.application_cycle.value if stype.application_cycle else "semester",
                    "description": config.description or stype.description or "",
                    "sub_types": sub_types,
                }
            )

        return ApiResponse(success=True, message="Quota overview retrieved successfully", data=overview_data)

    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid period format: {period}")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve quota overview: {str(e)}"
        )


# CRUD Endpoints for ScholarshipConfiguration Management


@router.post("/configurations")
async def create_scholarship_configuration(
    config_data: Dict[str, Any] = Body(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new scholarship configuration"""

    try:
        # Get accessible scholarship IDs
        accessible_scholarship_ids = await get_user_accessible_scholarship_ids(current_user, db)

        scholarship_type_id = config_data.get("scholarship_type_id")
        if not scholarship_type_id or scholarship_type_id not in accessible_scholarship_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="您沒有管理此獎學金的權限")

        # Check if configuration already exists for this period
        existing_stmt = select(ScholarshipConfiguration).where(
            and_(
                ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
                ScholarshipConfiguration.academic_year == config_data.get("academic_year"),
                ScholarshipConfiguration.semester == config_data.get("semester"),
                ScholarshipConfiguration.is_active.is_(True),
            )
        )
        existing_result = await db.execute(existing_stmt)
        existing_config = existing_result.scalar_one_or_none()

        if existing_config:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="此學年度/學期已存在配置")

        # Create new configuration
        new_config = ScholarshipConfiguration(
            scholarship_type_id=scholarship_type_id,
            academic_year=config_data["academic_year"],
            semester=config_data.get("semester"),
            config_name=config_data["config_name"],
            config_code=config_data["config_code"],
            description=config_data.get("description"),
            description_en=config_data.get("description_en"),
            amount=config_data["amount"],
            currency=config_data.get("currency", "TWD"),
            whitelist_student_ids=config_data.get("whitelist_student_ids", {}),
            renewal_application_start_date=config_data.get("renewal_application_start_date"),
            renewal_application_end_date=config_data.get("renewal_application_end_date"),
            application_start_date=config_data.get("application_start_date"),
            application_end_date=config_data.get("application_end_date"),
            renewal_professor_review_start=config_data.get("renewal_professor_review_start"),
            renewal_professor_review_end=config_data.get("renewal_professor_review_end"),
            renewal_college_review_start=config_data.get("renewal_college_review_start"),
            renewal_college_review_end=config_data.get("renewal_college_review_end"),
            requires_professor_recommendation=config_data.get("requires_professor_recommendation", False),
            professor_review_start=config_data.get("professor_review_start"),
            professor_review_end=config_data.get("professor_review_end"),
            requires_college_review=config_data.get("requires_college_review", False),
            college_review_start=config_data.get("college_review_start"),
            college_review_end=config_data.get("college_review_end"),
            review_deadline=config_data.get("review_deadline"),
            is_active=config_data.get("is_active", True),
            effective_start_date=config_data.get("effective_start_date"),
            effective_end_date=config_data.get("effective_end_date"),
            version=config_data.get("version", "1.0"),
            created_by=current_user.id,
        )

        db.add(new_config)
        await db.commit()
        await db.refresh(new_config)

        return ApiResponse(
            success=True, message="獎學金配置建立成功", data={"id": new_config.id, "config_code": new_config.config_code}
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create configuration: {str(e)}"
        )


@router.get("/configurations/{id}")
async def get_scholarship_configuration(
    id: int, current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """Get a specific scholarship configuration by ID"""

    try:
        # Get accessible scholarship IDs
        accessible_scholarship_ids = await get_user_accessible_scholarship_ids(current_user, db)

        # Get configuration with scholarship type
        stmt = (
            select(ScholarshipConfiguration)
            .where(
                and_(
                    ScholarshipConfiguration.id == id,
                    ScholarshipConfiguration.scholarship_type_id.in_(accessible_scholarship_ids),
                )
            )
            .options(selectinload(ScholarshipConfiguration.scholarship_type))
        )

        result = await db.execute(stmt)
        config = result.scalar_one_or_none()

        if not config:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="配置不存在或您沒有存取權限")

        # Build response data
        config_data = {
            "id": config.id,
            "scholarship_type_id": config.scholarship_type_id,
            "scholarship_type_name": config.scholarship_type.name if config.scholarship_type else None,
            "academic_year": config.academic_year,
            "semester": config.semester.value if config.semester else None,
            "config_name": config.config_name,
            "config_code": config.config_code,
            "description": config.description,
            "description_en": config.description_en,
            "amount": config.amount,
            "currency": config.currency,
            "whitelist_student_ids": config.whitelist_student_ids,
            "has_quota_limit": config.has_quota_limit,
            "has_college_quota": config.has_college_quota,
            "quota_management_mode": config.quota_management_mode.value if config.quota_management_mode else "none",
            "total_quota": config.total_quota,
            "quotas": config.quotas,
            "renewal_application_start_date": config.renewal_application_start_date.isoformat()
            if config.renewal_application_start_date
            else None,
            "renewal_application_end_date": config.renewal_application_end_date.isoformat()
            if config.renewal_application_end_date
            else None,
            "application_start_date": config.application_start_date.isoformat()
            if config.application_start_date
            else None,
            "application_end_date": config.application_end_date.isoformat() if config.application_end_date else None,
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
            "professor_review_end": config.professor_review_end.isoformat() if config.professor_review_end else None,
            "requires_college_review": config.requires_college_review,
            "college_review_start": config.college_review_start.isoformat() if config.college_review_start else None,
            "college_review_end": config.college_review_end.isoformat() if config.college_review_end else None,
            "review_deadline": config.review_deadline.isoformat() if config.review_deadline else None,
            "is_active": config.is_active,
            "effective_start_date": config.effective_start_date.isoformat() if config.effective_start_date else None,
            "effective_end_date": config.effective_end_date.isoformat() if config.effective_end_date else None,
            "version": config.version,
            "created_at": config.created_at.isoformat() if config.created_at else None,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        }

        return ApiResponse(success=True, message="配置資料取得成功", data=config_data)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve configuration: {str(e)}"
        )


@router.put("/configurations/{id}")
async def update_scholarship_configuration(
    id: int,
    config_data: Dict[str, Any] = Body(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update a scholarship configuration (excluding quota fields)"""

    try:
        # Get accessible scholarship IDs
        accessible_scholarship_ids = await get_user_accessible_scholarship_ids(current_user, db)

        # Get existing configuration
        stmt = select(ScholarshipConfiguration).where(
            and_(
                ScholarshipConfiguration.id == id,
                ScholarshipConfiguration.scholarship_type_id.in_(accessible_scholarship_ids),
            )
        )

        result = await db.execute(stmt)
        config = result.scalar_one_or_none()

        if not config:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="配置不存在或您沒有存取權限")

        # Update fields (excluding quota-related fields)
        if "config_name" in config_data:
            config.config_name = config_data["config_name"]
        if "description" in config_data:
            config.description = config_data["description"]
        if "description_en" in config_data:
            config.description_en = config_data["description_en"]
        if "amount" in config_data:
            config.amount = config_data["amount"]
        if "currency" in config_data:
            config.currency = config_data["currency"]
        if "whitelist_student_ids" in config_data:
            config.whitelist_student_ids = config_data["whitelist_student_ids"]
            flag_modified(config, "whitelist_student_ids")

        # Update application periods with proper date parsing
        from app.utils.date_utils import parse_date_field

        if "renewal_application_start_date" in config_data:
            config.renewal_application_start_date = parse_date_field(config_data["renewal_application_start_date"])
        if "renewal_application_end_date" in config_data:
            config.renewal_application_end_date = parse_date_field(config_data["renewal_application_end_date"])
        if "application_start_date" in config_data:
            config.application_start_date = parse_date_field(config_data["application_start_date"])
        if "application_end_date" in config_data:
            config.application_end_date = parse_date_field(config_data["application_end_date"])

        # Update review periods
        if "renewal_professor_review_start" in config_data:
            config.renewal_professor_review_start = parse_date_field(config_data["renewal_professor_review_start"])
        if "renewal_professor_review_end" in config_data:
            config.renewal_professor_review_end = parse_date_field(config_data["renewal_professor_review_end"])
        if "renewal_college_review_start" in config_data:
            config.renewal_college_review_start = parse_date_field(config_data["renewal_college_review_start"])
        if "renewal_college_review_end" in config_data:
            config.renewal_college_review_end = parse_date_field(config_data["renewal_college_review_end"])
        if "requires_professor_recommendation" in config_data:
            config.requires_professor_recommendation = config_data["requires_professor_recommendation"]
        if "professor_review_start" in config_data:
            config.professor_review_start = parse_date_field(config_data["professor_review_start"])
        if "professor_review_end" in config_data:
            config.professor_review_end = parse_date_field(config_data["professor_review_end"])
        if "requires_college_review" in config_data:
            config.requires_college_review = config_data["requires_college_review"]
        if "college_review_start" in config_data:
            config.college_review_start = parse_date_field(config_data["college_review_start"])
        if "college_review_end" in config_data:
            config.college_review_end = parse_date_field(config_data["college_review_end"])
        if "review_deadline" in config_data:
            config.review_deadline = parse_date_field(config_data["review_deadline"])

        # Update status and effective dates
        if "is_active" in config_data:
            config.is_active = config_data["is_active"]
        if "effective_start_date" in config_data:
            config.effective_start_date = parse_date_field(config_data["effective_start_date"])
        if "effective_end_date" in config_data:
            config.effective_end_date = parse_date_field(config_data["effective_end_date"])
        if "version" in config_data:
            config.version = config_data["version"]

        # Update quota management settings
        if "quota_management_mode" in config_data:
            from app.models.enums import QuotaManagementMode

            mode_value = config_data["quota_management_mode"]
            if mode_value:
                # Find the enum by its value
                mode_enum = None
                for mode in QuotaManagementMode:
                    if mode.value == mode_value:
                        mode_enum = mode
                        break
                if mode_enum:
                    config.quota_management_mode = mode_enum
            else:
                config.quota_management_mode = QuotaManagementMode.none

        if "has_quota_limit" in config_data:
            config.has_quota_limit = config_data["has_quota_limit"]
        if "has_college_quota" in config_data:
            config.has_college_quota = config_data["has_college_quota"]
        if "total_quota" in config_data:
            config.total_quota = config_data["total_quota"]
        if "quotas" in config_data:
            config.quotas = config_data["quotas"]
            flag_modified(config, "quotas")

        config.updated_by = current_user.id

        await db.commit()
        await db.refresh(config)

        return ApiResponse(success=True, message="配置更新成功", data={"id": config.id, "config_code": config.config_code})

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error in update_scholarship_configuration: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update configuration: {str(e)}"
        )


@router.delete("/configurations/{id}")
async def deactivate_scholarship_configuration(
    id: int, current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """Deactivate (soft delete) a scholarship configuration"""

    try:
        # Get accessible scholarship IDs
        accessible_scholarship_ids = await get_user_accessible_scholarship_ids(current_user, db)

        # Get existing configuration
        stmt = select(ScholarshipConfiguration).where(
            and_(
                ScholarshipConfiguration.id == id,
                ScholarshipConfiguration.scholarship_type_id.in_(accessible_scholarship_ids),
            )
        )

        result = await db.execute(stmt)
        config = result.scalar_one_or_none()

        if not config:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="配置不存在或您沒有存取權限")

        # Check if there are active applications using this configuration
        # This would need to be implemented based on your application model structure
        # For now, we'll just perform the soft delete

        config.is_active = False
        config.updated_by = current_user.id

        await db.commit()

        return ApiResponse(success=True, message="配置已停用", data={"id": config.id, "config_code": config.config_code})

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to deactivate configuration: {str(e)}"
        )


@router.post("/configurations/{id}/duplicate")
async def duplicate_scholarship_configuration(
    id: int,
    target_data: Dict[str, Any] = Body(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Duplicate a scholarship configuration to a new academic period"""

    try:
        # Get accessible scholarship IDs
        accessible_scholarship_ids = await get_user_accessible_scholarship_ids(current_user, db)

        # Get source configuration
        stmt = select(ScholarshipConfiguration).where(
            and_(
                ScholarshipConfiguration.id == id,
                ScholarshipConfiguration.scholarship_type_id.in_(accessible_scholarship_ids),
            )
        )

        result = await db.execute(stmt)
        source_config = result.scalar_one_or_none()

        if not source_config:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="來源配置不存在或您沒有存取權限")

        target_academic_year = target_data["academic_year"]
        target_semester = target_data.get("semester")

        # Check if target configuration already exists
        existing_stmt = select(ScholarshipConfiguration).where(
            and_(
                ScholarshipConfiguration.scholarship_type_id == source_config.scholarship_type_id,
                ScholarshipConfiguration.academic_year == target_academic_year,
                ScholarshipConfiguration.semester == target_semester,
                ScholarshipConfiguration.is_active.is_(True),
            )
        )
        existing_result = await db.execute(existing_stmt)
        existing_config = existing_result.scalar_one_or_none()

        if existing_config:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="目標學年度/學期已存在配置")

        # Create duplicate configuration
        new_config = ScholarshipConfiguration(
            scholarship_type_id=source_config.scholarship_type_id,
            academic_year=target_academic_year,
            semester=target_semester,
            config_name=target_data.get("config_name", f"{source_config.config_name} (複製)"),
            config_code=target_data["config_code"],
            description=source_config.description,
            description_en=source_config.description_en,
            amount=source_config.amount,
            currency=source_config.currency,
            whitelist_student_ids=source_config.whitelist_student_ids.copy()
            if source_config.whitelist_student_ids
            else {},
            requires_professor_recommendation=source_config.requires_professor_recommendation,
            requires_college_review=source_config.requires_college_review,
            is_active=True,
            version="1.0",
            created_by=current_user.id,
        )

        db.add(new_config)
        await db.commit()
        await db.refresh(new_config)

        return ApiResponse(
            success=True, message="配置複製成功", data={"id": new_config.id, "config_code": new_config.config_code}
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to duplicate configuration: {str(e)}"
        )


@router.get("/configurations")
async def list_scholarship_configurations(
    scholarship_type_id: Optional[int] = Query(None, description="Filter by scholarship type ID"),
    academic_year: Optional[int] = Query(None, description="Filter by academic year"),
    semester: Optional[str] = Query(None, description="Filter by semester (first/second)"),
    is_active: bool = Query(True, description="Filter by active status"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List scholarship configurations with filtering"""

    try:
        # Get accessible scholarship IDs
        accessible_scholarship_ids = await get_user_accessible_scholarship_ids(current_user, db)

        if not accessible_scholarship_ids:
            return ApiResponse(success=True, message="No accessible configurations found", data=[])

        # Build query conditions
        conditions = [
            ScholarshipConfiguration.scholarship_type_id.in_(accessible_scholarship_ids),
            ScholarshipConfiguration.is_active == is_active,
        ]

        if scholarship_type_id:
            conditions.append(ScholarshipConfiguration.scholarship_type_id == scholarship_type_id)

        if academic_year:
            conditions.append(ScholarshipConfiguration.academic_year == academic_year)

        if semester:
            if semester == "first":
                conditions.append(ScholarshipConfiguration.semester == Semester.first)
            elif semester == "second":
                conditions.append(ScholarshipConfiguration.semester == Semester.second)

        # Execute query
        stmt = (
            select(ScholarshipConfiguration)
            .where(and_(*conditions))
            .options(selectinload(ScholarshipConfiguration.scholarship_type))
            .order_by(ScholarshipConfiguration.academic_year.desc(), ScholarshipConfiguration.semester.desc())
        )

        result = await db.execute(stmt)
        configurations = result.scalars().all()

        # Build response data
        config_list = []
        for config in configurations:
            config_data = {
                "id": config.id,
                "scholarship_type_id": config.scholarship_type_id,
                "scholarship_type_name": config.scholarship_type.name if config.scholarship_type else None,
                "scholarship_type_code": config.scholarship_type.code if config.scholarship_type else None,
                "academic_year": config.academic_year,
                "semester": config.semester.value if config.semester else None,
                "config_name": config.config_name,
                "config_code": config.config_code,
                "description": config.description,
                "description_en": config.description_en,
                "amount": config.amount,
                "currency": config.currency,
                "whitelist_student_ids": config.whitelist_student_ids,
                "has_quota_limit": config.has_quota_limit,
                "has_college_quota": config.has_college_quota,
                "quota_management_mode": config.quota_management_mode.value if config.quota_management_mode else "none",
                "total_quota": config.total_quota,
                "quotas": config.quotas,
                "is_active": config.is_active,
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
                # Add review-related fields
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
                "effective_start_date": config.effective_start_date.isoformat()
                if config.effective_start_date
                else None,
                "effective_end_date": config.effective_end_date.isoformat() if config.effective_end_date else None,
                "version": config.version,
                "created_at": config.created_at.isoformat() if config.created_at else None,
                "updated_at": config.updated_at.isoformat() if config.updated_at else None,
            }
            config_list.append(config_data)

        return ApiResponse(success=True, message=f"Retrieved {len(config_list)} configurations", data=config_list)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to list configurations: {str(e)}"
        )


# Whitelist Management Endpoints


@router.get("/{id}/whitelist")
async def get_configuration_whitelist(
    id: int, current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """
    Get whitelist for a specific scholarship configuration

    Returns whitelist organized by sub-scholarship type with student details
    """
    # Get configuration
    stmt = select(ScholarshipConfiguration).where(ScholarshipConfiguration.id == id)
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail=f"找不到ID為 {id} 的獎學金配置")

    # Get all whitelisted students organized by sub_type
    whitelist_data = config.get_all_whitelisted_students()  # Returns Dict[str, List[str]] - nycu_ids

    response_list = []
    for sub_type, nycu_ids in whitelist_data.items():
        if not nycu_ids:
            response_list.append(WhitelistResponse(sub_type=sub_type, students=[], total=0))
            continue

        # Fetch user details for these nycu_ids
        stmt = select(User).where(User.nycu_id.in_(nycu_ids))
        result = await db.execute(stmt)
        users = result.scalars().all()

        # Create user lookup dictionary
        user_dict = {user.nycu_id: user for user in users}

        # Build student info list - 包含所有申請白名單學號（包括未註冊的）
        students = []
        for nycu_id in nycu_ids:
            user = user_dict.get(nycu_id)
            students.append(
                WhitelistStudentInfo(
                    student_id=user.id if user else None,
                    nycu_id=nycu_id,
                    name=user.name if user else None,
                    sub_type=sub_type,
                    note=None,
                    is_registered=user is not None,
                )
            )

        response_list.append(WhitelistResponse(sub_type=sub_type, students=students, total=len(students)))

    return ApiResponse(success=True, message="成功取得白名單", data=response_list)


@router.post("/{id}/whitelist/batch")
async def batch_add_whitelist(
    id: int,
    request: WhitelistBatchAddRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Batch add students to whitelist

    Request format:
    {
        "students": [
            {"nycu_id": "0856001", "sub_type": "nstc"},
            {"nycu_id": "0856002", "sub_type": "moe_1w"}
        ]
    }
    """
    # Get configuration with scholarship_type eagerly loaded
    stmt = (
        select(ScholarshipConfiguration)
        .options(joinedload(ScholarshipConfiguration.scholarship_type))
        .where(ScholarshipConfiguration.id == id)
    )
    result = await db.execute(stmt)
    config = result.unique().scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail=f"找不到ID為 {id} 的獎學金配置")

    added_count = 0
    errors = []

    for student_data in request.students:
        nycu_id = student_data["nycu_id"]
        sub_type = student_data["sub_type"]

        # Validate sub_type exists in scholarship_type's sub_type_list
        if config.scholarship_type.sub_type_list and sub_type not in config.scholarship_type.sub_type_list:
            errors.append(f"學號 {nycu_id}: 子獎學金類型 {sub_type} 無效")
            continue

        # Add to whitelist using nycu_id (允許添加未註冊的學生)
        config.add_student_to_whitelist(nycu_id, sub_type)
        added_count += 1

    # Mark the field as modified for JSON update
    flag_modified(config, "whitelist_student_ids")
    config.updated_by = current_user.id

    await db.commit()

    return ApiResponse(
        success=True, message=f"成功新增 {added_count} 位學生到白名單", data={"added_count": added_count, "errors": errors}
    )


@router.delete("/{id}/whitelist/batch")
async def batch_remove_whitelist(
    id: int,
    request: WhitelistBatchRemoveRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Batch remove students from whitelist

    Request format:
    {
        "nycu_ids": ["0856001", "0856002"],
        "sub_type": "nstc"  // Optional, if null removes from all sub-types
    }
    """
    # Get configuration
    stmt = select(ScholarshipConfiguration).where(ScholarshipConfiguration.id == id)
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail=f"找不到ID為 {id} 的獎學金配置")

    removed_count = 0

    for nycu_id in request.nycu_ids:
        removed = config.remove_student_from_whitelist(nycu_id, request.sub_type)
        if removed:
            removed_count += 1

    # Mark the field as modified for JSON update
    flag_modified(config, "whitelist_student_ids")
    config.updated_by = current_user.id

    await db.commit()

    return ApiResponse(success=True, message=f"成功移除 {removed_count} 位學生", data={"removed_count": removed_count})


@router.post("/{id}/whitelist/import")
async def import_whitelist_excel(
    id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Import whitelist from Excel file

    Expected Excel format:
    | 學號 | 姓名 | 子獎學金類型 | 備註 |
    """
    # Validate file type
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="只支援 Excel 檔案格式 (.xlsx, .xls)")

    # Get configuration
    stmt = (
        select(ScholarshipConfiguration)
        .options(selectinload(ScholarshipConfiguration.scholarship_type))
        .where(ScholarshipConfiguration.id == id)
    )
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail=f"找不到ID為 {id} 的獎學金配置")

    # Get valid sub_types
    valid_sub_types = config.scholarship_type.sub_type_list or ["general"]

    # Read and parse Excel
    file_content = await file.read()
    success_data, parse_errors = whitelist_excel_service.parse_import_excel(file_content, valid_sub_types)

    # Process successful data
    added_count = 0
    import_errors = []

    for student_data in success_data:
        nycu_id = student_data["nycu_id"]
        sub_type = student_data["sub_type"]

        # Validate sub_type exists in scholarship_type's sub_type_list
        if config.scholarship_type.sub_type_list and sub_type not in config.scholarship_type.sub_type_list:
            import_errors.append({"row": "", "nycu_id": nycu_id, "error": f"子獎學金類型 {sub_type} 無效"})
            continue

        # Add to whitelist using nycu_id (允許添加未註冊的學生)
        config.add_student_to_whitelist(nycu_id, sub_type)
        added_count += 1

    # Combine all errors
    all_errors = parse_errors + import_errors

    # Mark the field as modified for JSON update
    if added_count > 0:
        flag_modified(config, "whitelist_student_ids")
        config.updated_by = current_user.id
        await db.commit()

    return ApiResponse(
        success=True,
        message=f"匯入完成：成功 {added_count} 筆，失敗 {len(all_errors)} 筆",
        data=WhitelistImportResult(
            success_count=added_count, error_count=len(all_errors), errors=all_errors, warnings=[]
        ),
    )


@router.get("/{id}/whitelist/export")
async def export_whitelist_excel(
    id: int, current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """
    Export whitelist to Excel file
    """
    # Get configuration
    stmt = (
        select(ScholarshipConfiguration)
        .options(selectinload(ScholarshipConfiguration.scholarship_type))
        .where(ScholarshipConfiguration.id == id)
    )
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail=f"找不到ID為 {id} 的獎學金配置")

    # Get all whitelisted students with details
    whitelist_data = config.get_all_whitelisted_students()  # Dict[str, List[str]]

    # Fetch user details and organize data
    export_data = {}
    for sub_type, nycu_ids in whitelist_data.items():
        if not nycu_ids:
            export_data[sub_type] = []
            continue

        # Fetch registered users
        stmt = select(User).where(User.nycu_id.in_(nycu_ids))
        result = await db.execute(stmt)
        users = result.scalars().all()
        user_dict = {user.nycu_id: user for user in users}

        # Include ALL nycu_ids (including unregistered students)
        export_data[sub_type] = [
            {
                "nycu_id": nycu_id,
                "name": user_dict[nycu_id].name if nycu_id in user_dict else "未註冊",
                "note": "",
            }
            for nycu_id in nycu_ids
        ]

    # Generate Excel
    scholarship_name = config.scholarship_type.name
    excel_file = whitelist_excel_service.export_whitelist(export_data, scholarship_name)

    # Return as downloadable file
    filename = (
        f"{scholarship_name}_申請白名單_{config.academic_year}_{config.semester.value if config.semester else 'yearly'}.xlsx"
    )

    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.get("/{id}/whitelist/template")
async def download_whitelist_template(
    id: int, current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """
    Download whitelist import template Excel file
    """
    # Get configuration
    stmt = (
        select(ScholarshipConfiguration)
        .options(selectinload(ScholarshipConfiguration.scholarship_type))
        .where(ScholarshipConfiguration.id == id)
    )
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail=f"找不到ID為 {id} 的獎學金配置")

    # Get valid sub_types
    valid_sub_types = config.scholarship_type.sub_type_list or ["general"]

    # Generate template
    template_file = whitelist_excel_service.generate_template(valid_sub_types)

    # Return as downloadable file
    filename = f"白名單匯入模板_{config.scholarship_type.name}.xlsx"

    return StreamingResponse(
        template_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
