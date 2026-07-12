"""
Student management API endpoints for administrators
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin
from app.db.deps import get_db
from app.models.application import Application
from app.models.enums import ApplicationStatus
from app.models.scholarship import ScholarshipType
from app.models.user import EmployeeStatus, User, UserRole
from app.services.student_service import StudentService

logger = logging.getLogger(__name__)

router = APIRouter()


def applied_application_filters() -> list:
    """Filter clauses for applications that count as "the student applied".

    An application counts once the student has submitted it (draft = not yet
    applied); soft-deleted rows and rows without a scholarship type link are
    excluded. Shared by the list annotation and the scholarship filters so the
    badges shown always match what the filters return.
    """
    return [
        Application.deleted_at.is_(None),
        Application.status.notin_([ApplicationStatus.draft, ApplicationStatus.deleted]),
        Application.scholarship_type_id.isnot(None),
    ]


async def get_applied_scholarships_map(db: AsyncSession, user_ids: list[int]) -> dict[int, list[dict]]:
    """Aggregate which scholarship types each user has applied for.

    Returns {user_id: [{scholarship_type_id, code, name, application_count}]},
    one entry per distinct scholarship type with the number of qualifying
    applications (see applied_application_filters for what qualifies).
    """
    applied_map: dict[int, list[dict]] = {user_id: [] for user_id in user_ids}
    if not user_ids:
        return applied_map

    stmt = (
        select(
            Application.user_id,
            ScholarshipType.id,
            ScholarshipType.code,
            ScholarshipType.name,
            func.count(Application.id),
        )
        .join(ScholarshipType, Application.scholarship_type_id == ScholarshipType.id)
        .where(Application.user_id.in_(user_ids), *applied_application_filters())
        .group_by(Application.user_id, ScholarshipType.id, ScholarshipType.code, ScholarshipType.name)
        .order_by(ScholarshipType.id)
    )
    result = await db.execute(stmt)
    for user_id, type_id, type_code, type_name, application_count in result.all():
        applied_map[user_id].append(
            {
                "scholarship_type_id": type_id,
                "code": type_code,
                "name": type_name,
                "application_count": application_count,
            }
        )
    return applied_map


def convert_student_to_dict(user: User, applied_scholarships: Optional[list[dict]] = None) -> dict:
    """Convert User model (student role) to dictionary"""
    return {
        "id": user.id,
        "nycu_id": user.nycu_id,
        "name": user.name,
        "email": user.email,
        "user_type": user.user_type.value if user.user_type else None,
        "status": user.status.value if user.status else None,
        "dept_code": user.dept_code,
        "dept_name": user.dept_name,
        "college_code": user.college_code,
        "role": user.role.value if hasattr(user.role, "value") else str(user.role),
        "comment": user.comment,
        "applied_scholarships": applied_scholarships or [],
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


@router.get("")
async def get_all_students(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search by name, email, or NYCU ID"),
    dept_code: Optional[str] = Query(None, description="Filter by department code"),
    status: Optional[str] = Query(None, description="Filter by status (在學/畢業)"),
    scholarship_type_id: Optional[int] = Query(
        None, description="Filter by scholarship type the student has applied for"
    ),
    has_application: Optional[bool] = Query(
        None, description="Filter by whether the student has applied for any scholarship"
    ),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all students with pagination, search, and filters

    Each student item includes applied_scholarships: the scholarship types the
    student has submitted applications for (drafts and deleted applications
    excluded), with per-type application counts.

    Requires admin or super_admin role.
    """
    # Base query: students only
    stmt = select(User).where(User.role == UserRole.student)

    # Apply search filter
    if search:
        search_pattern = f"%{search}%"
        stmt = stmt.where(
            or_(
                User.name.ilike(search_pattern),
                User.email.ilike(search_pattern),
                User.nycu_id.ilike(search_pattern),
            )
        )

    # Apply department filter
    if dept_code:
        stmt = stmt.where(User.dept_code == dept_code)

    # Apply status filter
    if status:
        # Validate status is a valid EmployeeStatus value
        valid_statuses = [s.value for s in EmployeeStatus]
        if status in valid_statuses:
            stmt = stmt.where(User.status == status)

    # Apply scholarship application filters (EXISTS correlated on User.id)
    if scholarship_type_id is not None:
        stmt = stmt.where(
            select(Application.id)
            .where(
                Application.user_id == User.id,
                Application.scholarship_type_id == scholarship_type_id,
                *applied_application_filters(),
            )
            .exists()
        )

    if has_application is not None:
        any_application = (
            select(Application.id).where(Application.user_id == User.id, *applied_application_filters()).exists()
        )
        stmt = stmt.where(any_application if has_application else ~any_application)

    # Get total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    result = await db.execute(count_stmt)
    total = result.scalar() or 0

    # Apply pagination and ordering
    stmt = stmt.order_by(desc(User.created_at)).offset((page - 1) * size).limit(size)

    # Execute query
    result = await db.execute(stmt)
    students = result.scalars().all()

    # Annotate each student with the scholarships they have applied for
    applied_map = await get_applied_scholarships_map(db, [student.id for student in students])

    # Convert to dict
    student_list = [convert_student_to_dict(student, applied_map.get(student.id, [])) for student in students]

    # Calculate total pages
    pages = (total + size - 1) // size if total > 0 else 0

    return {
        "success": True,
        "message": "Students retrieved successfully",
        "data": {
            "items": student_list,
            "total": total,
            "page": page,
            "size": size,
            "pages": pages,
        },
    }


@router.get("/stats")
async def get_student_statistics(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Get student statistics

    Returns:
    - total_students: Total number of students
    - status_distribution: Distribution by status (在學/畢業)
    - dept_distribution: Top 10 departments by student count
    """
    # Total students
    total_stmt = select(func.count()).select_from(User).where(User.role == UserRole.student)
    result = await db.execute(total_stmt)
    total_students = result.scalar() or 0

    # Status distribution
    status_stmt = select(User.status, func.count()).where(User.role == UserRole.student).group_by(User.status)
    result = await db.execute(status_stmt)
    status_rows = result.all()
    status_distribution = {row[0].value if row[0] else "未知": row[1] for row in status_rows}

    # Department distribution (top 10)
    dept_stmt = (
        select(User.dept_name, func.count())
        .where(and_(User.role == UserRole.student, User.dept_name.isnot(None)))
        .group_by(User.dept_name)
        .order_by(desc(func.count()))
        .limit(10)
    )
    result = await db.execute(dept_stmt)
    dept_rows = result.all()
    dept_distribution = {row[0]: row[1] for row in dept_rows}

    # Recent registrations (last 30 days)
    from datetime import timedelta

    thirty_days_ago = func.now() - timedelta(days=30)
    recent_stmt = (
        select(func.count())
        .select_from(User)
        .where(and_(User.role == UserRole.student, User.created_at >= thirty_days_ago))
    )
    result = await db.execute(recent_stmt)
    recent_registrations = result.scalar() or 0

    return {
        "success": True,
        "message": "Student statistics retrieved successfully",
        "data": {
            "total_students": total_students,
            "status_distribution": status_distribution,
            "dept_distribution": dept_distribution,
            "recent_registrations": recent_registrations,
        },
    }


@router.get("/{user_id}")
async def get_student_detail(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Get detailed information for a specific student

    Returns basic user info from database.

    SECURITY: Admin PII lookup. Audit-logged with actor_user_id +
    target user_id + target nycu_id so directed lookups of specific
    students are traceable to an admin actor.
    """
    stmt = select(User).where(and_(User.id == user_id, User.role == UserRole.student))
    result = await db.execute(stmt)
    student = result.scalar_one_or_none()

    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    logger.info(
        "admin student-detail lookup: target_user_id=%s nycu_id=%s by user_id=%s",
        student.id,
        student.nycu_id,
        current_user.id,
        extra={
            "actor_user_id": current_user.id,
            "actor_role": (current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)),
            "target_user_id": student.id,
            "target_nycu_id": student.nycu_id,
        },
    )

    applied_map = await get_applied_scholarships_map(db, [student.id])

    return {
        "success": True,
        "message": "Student detail retrieved successfully",
        "data": convert_student_to_dict(student, applied_map.get(student.id, [])),
    }


@router.get("/{user_id}/sis-data")
async def get_student_sis_data(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Get real-time student information from SIS API

    This endpoint fetches fresh data from the external Student Information System.
    Requires the student's NYCU ID.

    SECURITY: Live SIS PII fetch (basic info + multi-semester term data).
    Audit-logged with actor + target identifiers + SIS-fetch outcome.
    Per-semester fetch failures are also counted so the SIS API's
    availability is visible without spamming the log on legitimate
    gap-year terms.
    """
    # Get student from database
    stmt = select(User).where(and_(User.id == user_id, User.role == UserRole.student))
    result = await db.execute(stmt)
    student = result.scalar_one_or_none()

    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    if not student.nycu_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Student does not have a NYCU ID")

    log_extra = {
        "actor_user_id": current_user.id,
        "actor_role": (current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)),
        "target_user_id": student.id,
        "target_nycu_id": student.nycu_id,
    }

    # Fetch from SIS API
    student_service = StudentService()

    try:
        # Get basic info from API
        basic_info = await student_service.get_student_basic_info(student.nycu_id)

        if not basic_info:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student data not found in SIS")

        # Get term data for recent semesters
        from app.utils.academic_period import get_academic_year_range

        semesters = []
        term_fetch_failures = 0
        student_code = basic_info.get("std_stdcode", student.nycu_id)

        if student_code:
            # Get academic years to query (current + 3 years back)
            academic_years = get_academic_year_range(years_back=3, include_current=True)

            for year in academic_years:
                for term in ["1", "2"]:
                    try:
                        term_data = await student_service.get_student_term_info(student_code, str(year), term)
                        if term_data:
                            semesters.append({"academic_year": str(year), "term": term, **term_data})
                    except Exception as term_exc:
                        # Some semesters legitimately don't exist (gap years, before-enrollment
                        # terms). Log at debug + count failures so a real SIS outage is visible
                        # in the audit row without spamming on legitimate gaps.
                        term_fetch_failures += 1
                        logger.debug(
                            "SIS term fetch failed: student=%s year=%s term=%s: %s",
                            student_code,
                            year,
                            term,
                            term_exc,
                        )

        logger.info(
            "admin SIS-data lookup: target_user_id=%s nycu_id=%s semesters=%d term_failures=%d by user_id=%s",
            student.id,
            student.nycu_id,
            len(semesters),
            term_fetch_failures,
            current_user.id,
            extra={
                **log_extra,
                "semesters_count": len(semesters),
                "term_fetch_failures": term_fetch_failures,
            },
        )

        return {
            "success": True,
            "message": "Student SIS data retrieved successfully",
            "data": {
                "basic_info": basic_info,
                "semesters": semesters,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("admin SIS-data lookup failed", extra=log_extra)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Failed to fetch student data from SIS"
        ) from e
