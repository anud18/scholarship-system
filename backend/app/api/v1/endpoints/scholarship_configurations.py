"""
Scholarship Configuration Management API endpoints
Clean, database-driven approach for dynamic scholarship configuration management
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Body, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, select, func, distinct
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.db.deps import get_db
from app.core.security import require_admin, get_current_user
from app.models.user import User, AdminScholarship, UserRole
from app.models.scholarship import ScholarshipType, ScholarshipConfiguration
from app.models.application import Application, ApplicationStatus
from app.models.student import Student
from app.models.enums import ApplicationCycle, QuotaManagementMode, Semester
from app.schemas.response import ApiResponse

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
    if user.role == UserRole.SUPER_ADMIN:
        # Super admins can access all scholarships
        stmt = select(ScholarshipType.id)
        result = await db.execute(stmt)
        return result.scalars().all()
    
    elif user.role == UserRole.ADMIN:
        # Regular admins can only access scholarships they have permissions for
        stmt = select(AdminScholarship.scholarship_id).where(
            AdminScholarship.admin_id == user.id
        )
        result = await db.execute(stmt)
        return result.scalars().all()
    
    else:
        # Other roles have no access
        return []


# Core API endpoints

@router.get("/available-semesters", response_model=ApiResponse)
async def get_available_semesters(
    quota_management_mode: Optional[str] = Query(None, description="Filter periods by quota management mode (e.g., 'matrix')"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get list of available academic periods from scholarship configurations"""
    
    try:
        # Get scholarship IDs user can access
        accessible_scholarship_ids = await get_user_accessible_scholarship_ids(current_user, db)
        
        if not accessible_scholarship_ids:
            return ApiResponse(
                success=True,
                message="No accessible scholarship configurations found",
                data=[]
            )
        
        # Build query conditions
        conditions = [
            ScholarshipConfiguration.is_active == True,
            ScholarshipConfiguration.scholarship_type_id.in_(accessible_scholarship_ids)
        ]
        
        # If quota_management_mode filter is provided, add it to conditions
        if quota_management_mode:
            from app.models.enums import QuotaManagementMode
            try:
                mode_enum = QuotaManagementMode(quota_management_mode)
                conditions.append(ScholarshipConfiguration.quota_management_mode == mode_enum)
            except ValueError:
                return ApiResponse(
                    success=False,
                    message=f"Invalid quota management mode: {quota_management_mode}",
                    data=[]
                )
        
        # Query for unique academic years and semesters from configurations
        stmt = select(
            ScholarshipConfiguration.academic_year,
            ScholarshipConfiguration.semester
        ).where(and_(*conditions)).distinct()
        
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
            if '-' in period:
                year, sem = period.split('-')
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
            success=True,
            message=f"Retrieved {len(unique_periods)} available periods",
            data=unique_periods
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve available semesters: {str(e)}"
        )


@router.get("/matrix-quota-status/{period}", response_model=ApiResponse)
async def get_matrix_quota_status(
    period: str,  # Academic year (e.g., "114") or semester (e.g., "114-1")
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get matrix quota status for PhD scholarships"""
    
    try:
        # Parse period
        if '-' in period:
            academic_year_str, semester_str = period.split('-')
            academic_year = int(academic_year_str)
            semester = Semester.FIRST if semester_str == "1" else Semester.SECOND
        else:
            academic_year = int(period)
            semester = None
        
        # Get accessible scholarship IDs
        accessible_scholarship_ids = await get_user_accessible_scholarship_ids(current_user, db)
        
        # Find PhD scholarship type
        if not accessible_scholarship_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="未找到可存取的獎學金"
            )
            
        phd_stmt = select(ScholarshipType).where(
            and_(
                ScholarshipType.code == "phd",
                ScholarshipType.id.in_(accessible_scholarship_ids)
            )
        )
        phd_result = await db.execute(phd_stmt)
        phd_scholarship = phd_result.scalar_one_or_none()
        
        if not phd_scholarship:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="PhD scholarship not found or not accessible"
            )
        
        # Get configuration for this period
        config_stmt = select(ScholarshipConfiguration).where(
            and_(
                ScholarshipConfiguration.scholarship_type_id == phd_scholarship.id,
                ScholarshipConfiguration.academic_year == academic_year,
                ScholarshipConfiguration.semester == semester if semester else ScholarshipConfiguration.semester.is_(None),
                ScholarshipConfiguration.is_active == True
            )
        ).options(selectinload(ScholarshipConfiguration.scholarship_type))
        
        config_result = await db.execute(config_stmt)
        config = config_result.scalar_one_or_none()
        
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No active configuration found for PhD scholarship in period {period}"
            )
        
        # Get matrix quotas from configuration
        matrix_quotas = config.college_quota_config or {}
        
        if not matrix_quotas:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No matrix quota configuration found"
            )
        
        # Get application usage data
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
        
        for sub_type in sub_types:
            phd_quotas[sub_type] = {}
            sub_type_quotas = matrix_quotas.get(sub_type, {})
            
            for college in college_codes:
                total_quota = sub_type_quotas.get(college, 0)
                
                # Get actual usage from applications using JOIN instead of subquery
                from sqlalchemy import join
                
                # Count approved applications with join to student table
                usage_stmt = select(func.count(Application.id)).select_from(
                    join(Application, Student, Application.student_id == Student.id)
                ).where(
                    and_(
                        Application.scholarship_type_id == phd_scholarship.id,
                        Application.academic_year == academic_year,
                        Application.status == ApplicationStatus.APPROVED,
                        Student.std_aca_no == college
                    )
                )
                
                # If semester-based, also filter by semester
                if semester:
                    usage_stmt = usage_stmt.where(Application.semester == semester)
                
                try:
                    usage_result = await db.execute(usage_stmt)
                    used = usage_result.scalar() or 0
                except Exception as usage_error:
                    print(f"DEBUG: Error in usage query: {usage_error}")
                    used = 0
                
                # Get total applications count using JOIN
                apps_stmt = select(func.count(Application.id)).select_from(
                    join(Application, Student, Application.student_id == Student.id)
                ).where(
                    and_(
                        Application.scholarship_type_id == phd_scholarship.id,
                        Application.academic_year == academic_year,
                        Student.std_aca_no == college
                    )
                )
                if semester:
                    apps_stmt = apps_stmt.where(Application.semester == semester)
                
                try:
                    apps_result = await db.execute(apps_stmt)
                    applications = apps_result.scalar() or 0
                except Exception as apps_error:
                    print(f"DEBUG: Error in applications query: {apps_error}")
                    applications = 0
                
                phd_quotas[sub_type][college] = {
                    "total_quota": total_quota,
                    "used": used,
                    "available": max(0, total_quota - used),
                    "applications": applications
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
                "total_available": grand_total_quota - grand_total_used
            }
        }
        
        return ApiResponse(
            success=True,
            message="Matrix quota status retrieved successfully",
            data=response_data
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid period format: {period}"
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_matrix_quota_status: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve matrix quota status: {str(e)}"
        )


@router.put("/matrix-quota", response_model=ApiResponse)
async def update_matrix_quota(
    sub_type: str = Body(...),
    college: str = Body(...),
    new_quota: int = Body(...),
    academic_year: Optional[int] = Body(None),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Update matrix quota for specific sub-type and college"""
    
    
    if new_quota < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="配額不能為負數"
        )
    
    if new_quota > 1000:  # Reasonable upper bound for scholarship quotas
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="配額數值過大（最大值：1000）"
        )
    
    try:
        # Get accessible scholarship IDs
        accessible_scholarship_ids = await get_user_accessible_scholarship_ids(current_user, db)
        
        # Find PhD scholarship
        if not accessible_scholarship_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="未找到可存取的獎學金"
            )
            
        phd_stmt = select(ScholarshipType).where(
            and_(
                ScholarshipType.code == "phd",
                ScholarshipType.id.in_(accessible_scholarship_ids)
            )
        )
        phd_result = await db.execute(phd_stmt)
        phd_scholarship = phd_result.scalar_one_or_none()
        
        if not phd_scholarship:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="您沒有管理博士獎學金配額的權限"
            )
        
        # Get the configuration for the specified academic year, or the most recent if not specified
        config_conditions = [
            ScholarshipConfiguration.scholarship_type_id == phd_scholarship.id,
            ScholarshipConfiguration.is_active == True
        ]
        
        if academic_year:
            config_conditions.append(ScholarshipConfiguration.academic_year == academic_year)
        
        config_stmt = select(ScholarshipConfiguration).where(
            and_(*config_conditions)
        ).order_by(ScholarshipConfiguration.academic_year.desc()).limit(1)
        
        config_result = await db.execute(config_stmt)
        config = config_result.scalar_one_or_none()
        
        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active configuration found for PhD scholarship"
            )
        
        # Validate sub_type and college
        valid_sub_types = phd_scholarship.sub_type_list or ["nstc", "moe_1w", "moe_2w"]
        if sub_type not in valid_sub_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid sub_type '{sub_type}'. Valid values: {valid_sub_types}"
            )
        
        # Initialize quota structure if needed
        if not config.college_quota_config:
            config.college_quota_config = {}
        
        if sub_type not in config.college_quota_config:
            config.college_quota_config[sub_type] = {}
        
        # Get old quota
        old_quota = config.college_quota_config[sub_type].get(college, 0)
        
        # Update quota
        config.college_quota_config[sub_type][college] = new_quota
        
        # Calculate totals
        sub_type_total = sum(config.college_quota_config[sub_type].values())
        grand_total = sum(
            sum(colleges.values()) 
            for colleges in config.college_quota_config.values()
            if isinstance(colleges, dict)
        )
        
        # Update total quota
        config.total_quota = grand_total
        config.updated_by = current_user.id
        
        # Mark as modified for SQLAlchemy
        flag_modified(config, 'college_quota_config')
        
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
                "config_id": config.id
            }
        )
        
    except Exception as e:
        await db.rollback()
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in update_matrix_quota: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update matrix quota: {str(e)}"
        )


@router.get("/colleges", response_model=ApiResponse)
async def get_colleges(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get college configurations from database"""
    
    try:
        # Get unique college codes from student data or configurations
        stmt = select(distinct(Student.std_aca_no)).where(
            Student.std_aca_no.isnot(None)
        )
        result = await db.execute(stmt)
        college_codes = result.scalars().all()
        
        # Build college list using centralized mappings
        from app.core.college_mappings import get_all_colleges, is_valid_college_code
        
        colleges = []
        for code in sorted(college_codes):
            if code and is_valid_college_code(code):
                college_info = get_all_colleges()
                college_data = next((c for c in college_info if c["code"] == code), None)
                if college_data:
                    colleges.append(college_data)
        
        return ApiResponse(
            success=True,
            message=f"Retrieved {len(colleges)} colleges",
            data=colleges
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve colleges: {str(e)}"
        )


@router.get("/scholarship-types", response_model=ApiResponse)
async def get_scholarship_types(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get scholarship types that the user has access to"""
    
    try:
        # Get accessible scholarship IDs
        accessible_scholarship_ids = await get_user_accessible_scholarship_ids(current_user, db)
        
        if not accessible_scholarship_ids:
            return ApiResponse(
                success=True,
                message="No accessible scholarship types found",
                data=[]
            )
        
        # Get scholarship types with their configurations
        stmt = select(ScholarshipType).where(
            and_(
                ScholarshipType.id.in_(accessible_scholarship_ids),
                ScholarshipType.status == "active"
            )
        ).options(
            selectinload(ScholarshipType.sub_type_configs)
        )
        
        result = await db.execute(stmt)
        scholarship_types = result.scalars().all()
        
        type_configs = []
        for stype in scholarship_types:
            # Get latest active configuration
            config_stmt = select(ScholarshipConfiguration).where(
                and_(
                    ScholarshipConfiguration.scholarship_type_id == stype.id,
                    ScholarshipConfiguration.is_active == True
                )
            ).order_by(ScholarshipConfiguration.academic_year.desc()).limit(1)
            
            config_result = await db.execute(config_stmt)
            latest_config = config_result.scalar_one_or_none()
            
            type_config = {
                "code": stype.code,
                "name": stype.name,
                "name_en": stype.name_en or stype.name,
                "category": stype.category,
                "sub_types": stype.sub_type_list or [],
                "has_quota_limit": latest_config.has_quota_limit if latest_config else False,
                "has_college_quota": latest_config.has_college_quota if latest_config else False,
                "quota_management_mode": latest_config.quota_management_mode.value if latest_config and latest_config.quota_management_mode else "none",
                "application_period": stype.application_cycle.value if stype.application_cycle else "semester",
                "description": latest_config.description if latest_config else stype.description or ""
            }
            type_configs.append(type_config)
        
        return ApiResponse(
            success=True,
            message=f"Retrieved {len(type_configs)} scholarship types",
            data=type_configs
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve scholarship types: {str(e)}"
        )


@router.get("/overview/{period}", response_model=ApiResponse)
async def get_quota_overview(
    period: str,  # Academic year or semester (e.g., "114" or "114-1")
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get comprehensive quota overview for accessible scholarship types"""
    
    try:
        # Parse period
        if '-' in period:
            academic_year_str, semester_str = period.split('-')
            academic_year = int(academic_year_str)
            semester = Semester.FIRST if semester_str == "1" else Semester.SECOND
        else:
            academic_year = int(period)
            semester = None
            
        # Get accessible scholarship IDs
        accessible_scholarship_ids = await get_user_accessible_scholarship_ids(current_user, db)
        
        if not accessible_scholarship_ids:
            return ApiResponse(
                success=True,
                message="No accessible scholarships found",
                data=[]
            )
        
        # Get configurations for this period
        stmt = select(ScholarshipConfiguration).where(
            and_(
                ScholarshipConfiguration.scholarship_type_id.in_(accessible_scholarship_ids),
                ScholarshipConfiguration.academic_year == academic_year,
                ScholarshipConfiguration.semester == semester if semester else ScholarshipConfiguration.semester.is_(None),
                ScholarshipConfiguration.is_active == True
            )
        ).options(
            selectinload(ScholarshipConfiguration.scholarship_type)
        )
        
        result = await db.execute(stmt)
        configurations = result.scalars().all()
        
        overview_data = []
        
        for config in configurations:
            stype = config.scholarship_type
            
            # Build sub-type data
            sub_types = []
            for sub_type_code in (stype.sub_type_list or ["general"]):
                # Calculate allocated quota for this sub-type
                allocated_quota = 0
                
                if config.has_college_quota and config.college_quota_config:
                    if sub_type_code in config.college_quota_config:
                        sub_type_quotas = config.college_quota_config[sub_type_code]
                        if isinstance(sub_type_quotas, dict):
                            allocated_quota = sum(sub_type_quotas.values())
                        else:
                            allocated_quota = sub_type_quotas
                elif config.total_quota:
                    # Split total quota among sub-types
                    num_sub_types = len(stype.sub_type_list or ["general"])
                    allocated_quota = config.total_quota // num_sub_types if num_sub_types > 0 else config.total_quota
                
                # TODO: Get actual usage from applications
                used_quota = 0
                applications_count = 0
                
                sub_types.append({
                    "main_type": stype.code,
                    "sub_type": sub_type_code,
                    "scholarship_name": sub_type_code.replace("_", " ").title(),
                    "allocated_quota": allocated_quota,
                    "used_quota": used_quota,
                    "remaining_quota": max(0, allocated_quota - used_quota),
                    "applications_count": applications_count,
                    "application_period": stype.application_cycle.value if stype.application_cycle else "semester",
                    "current_period": period
                })
            
            overview_data.append({
                "code": stype.code,
                "name": stype.name,
                "name_en": stype.name_en or stype.name,
                "category": stype.category,
                "has_quota_limit": config.has_quota_limit,
                "has_college_quota": config.has_college_quota,
                "quota_management_mode": config.quota_management_mode.value if config.quota_management_mode else "none",
                "application_period": stype.application_cycle.value if stype.application_cycle else "semester",
                "description": config.description or stype.description or "",
                "sub_types": sub_types
            })
        
        return ApiResponse(
            success=True,
            message="Quota overview retrieved successfully",
            data=overview_data
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid period format: {period}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve quota overview: {str(e)}"
        )