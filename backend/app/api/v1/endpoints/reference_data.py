"""
Reference data API endpoints for lookup tables
"""

from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_
from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_db
from app.models.application import Application
from app.models.enums import ApplicationCycle, Semester
from app.models.scholarship import ScholarshipType
from app.models.student import Academy, Degree, Department, EnrollType, Identity, SchoolIdentity, StudyingStatus
from app.schemas.common import ApiResponse

func: Any = sa_func

router = APIRouter()


@router.get("/degrees")
async def get_degrees(
    session: AsyncSession = Depends(get_db),
) -> List[dict]:
    """Get all degree types"""
    result = await session.execute(select(Degree))
    degrees = result.scalars().all()

    return [{"id": degree.id, "name": degree.name} for degree in degrees]


@router.get("/identities")
async def get_identities(
    session: AsyncSession = Depends(get_db),
) -> List[dict]:
    """Get all student identity types"""
    result = await session.execute(select(Identity))
    identities = result.scalars().all()

    return [{"id": identity.id, "name": identity.name} for identity in identities]


@router.get("/studying-statuses")
async def get_studying_statuses(
    session: AsyncSession = Depends(get_db),
) -> List[dict]:
    """Get all studying status types"""
    result = await session.execute(select(StudyingStatus))
    statuses = result.scalars().all()

    return [{"id": status.id, "name": status.name} for status in statuses]


@router.get("/school-identities")
async def get_school_identities(
    session: AsyncSession = Depends(get_db),
) -> List[dict]:
    """Get all school identity types"""
    result = await session.execute(select(SchoolIdentity))
    school_identities = result.scalars().all()

    return [{"id": school_identity.id, "name": school_identity.name} for school_identity in school_identities]


@router.get("/academies")
async def get_academies(
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[List[dict]]:
    """Get all academy/college information"""
    result = await session.execute(select(Academy).order_by(Academy.code))
    academies = result.scalars().all()

    data = [{"id": academy.id, "code": academy.code, "name": academy.name} for academy in academies]

    return ApiResponse(success=True, message="Academies retrieved successfully", data=data)


@router.get("/departments")
async def get_departments(
    session: AsyncSession = Depends(get_db),
) -> List[dict]:
    """Get all department information with academy mapping"""
    result = await session.execute(select(Department).order_by(Department.code))
    departments = result.scalars().all()

    return [
        {
            "id": department.id,
            "code": department.code,
            "name": department.name,
            "academy_code": department.academy_code,
        }
        for department in departments
    ]


@router.get("/enroll-types")
async def get_enroll_types(
    degree_id: Optional[int] = Query(None, description="Filter by degree ID"),
    session: AsyncSession = Depends(get_db),
) -> List[dict]:
    """Get enrollment types, optionally filtered by degree"""
    query = select(EnrollType).options(selectinload(EnrollType.degree))

    if degree_id:
        query = query.where(EnrollType.degreeId == degree_id)

    result = await session.execute(query.order_by(EnrollType.degreeId, EnrollType.code))
    enroll_types = result.scalars().all()

    return [
        {
            "degree_id": enroll_type.degreeId,
            "code": enroll_type.code,
            "name": enroll_type.name,
            "name_en": enroll_type.name_en,
            "degree_name": enroll_type.degree.name if enroll_type.degree else None,
        }
        for enroll_type in enroll_types
    ]


@router.get("/all")
async def get_all_reference_data(
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Get all reference data in a single request"""

    # Get all reference data in parallel
    degrees_result = await session.execute(select(Degree))
    identities_result = await session.execute(select(Identity))
    statuses_result = await session.execute(select(StudyingStatus))
    school_identities_result = await session.execute(select(SchoolIdentity))
    academies_result = await session.execute(select(Academy).order_by(Academy.code))
    departments_result = await session.execute(select(Department).order_by(Department.code))
    enroll_types_result = await session.execute(
        select(EnrollType).options(selectinload(EnrollType.degree)).order_by(EnrollType.degreeId, EnrollType.code)
    )

    degrees = degrees_result.scalars().all()
    identities = identities_result.scalars().all()
    statuses = statuses_result.scalars().all()
    school_identities = school_identities_result.scalars().all()
    academies = academies_result.scalars().all()
    departments = departments_result.scalars().all()
    enroll_types = enroll_types_result.scalars().all()

    return {
        "degrees": [{"id": degree.id, "name": degree.name} for degree in degrees],
        "identities": [{"id": identity.id, "name": identity.name} for identity in identities],
        "studying_statuses": [{"id": status.id, "name": status.name} for status in statuses],
        "school_identities": [
            {"id": school_identity.id, "name": school_identity.name} for school_identity in school_identities
        ],
        "academies": [{"id": academy.id, "code": academy.code, "name": academy.name} for academy in academies],
        "departments": [
            {"id": department.id, "code": department.code, "name": department.name} for department in departments
        ],
        "enroll_types": [
            {
                "degree_id": enroll_type.degreeId,
                "code": enroll_type.code,
                "name": enroll_type.name,
                "name_en": enroll_type.name_en,
                "degree_name": enroll_type.degree.name if enroll_type.degree else None,
            }
            for enroll_type in enroll_types
        ],
    }


@router.get("/semesters")
async def get_available_semesters() -> dict:
    """Get available semester and academic year options for dynamic generation"""
    from datetime import datetime

    from app.models.enums import Semester

    # Get current Taiwan academic year (民國年)
    current_year = datetime.now().year
    current_month = datetime.now().month
    taiwan_year = current_year - 1911

    # Determine current semester (8月以前為第二學期，8月以後為第一學期)
    current_semester = Semester.first.value if current_month >= 8 else Semester.second.value

    # Generate academic years: current - 2 to current + 2
    academic_years = []
    for year_offset in range(-2, 3):
        year = taiwan_year + year_offset
        academic_years.append(
            {
                "value": year,
                "label": f"{year}學年",
                "label_en": f"Academic Year {year + 1911}-{year + 1912}",
                "is_current": year_offset == 0,
            }
        )

    # Semester options using system enums
    semesters = [
        {
            "value": Semester.first.value,
            "label": "第一學期",
            "label_en": "First Semester",
            "is_current": current_semester == Semester.first.value,
        },
        {
            "value": Semester.second.value,
            "label": "第二學期",
            "label_en": "Second Semester",
            "is_current": current_semester == Semester.second.value,
        },
    ]

    return {
        "academic_years": academic_years,
        "semesters": semesters,
        "current_academic_year": taiwan_year,
        "current_semester": current_semester,
        "current_western_year": current_year,
    }


@router.get("/semester-academic-year-combinations")
async def get_semester_academic_year_combinations(
    include_statistics: bool = Query(False, description="Include application statistics"),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Get semester and academic year combinations with optional statistics"""
    from datetime import datetime

    # Get current info
    current_year = datetime.now().year
    current_month = datetime.now().month
    taiwan_year = current_year - 1911
    current_semester = Semester.first.value if current_month >= 8 else Semester.second.value

    combinations = []

    # Generate combinations for the last 3 years and next 2 years
    for year_offset in range(-2, 3):
        year = taiwan_year + year_offset

        for semester in [Semester.first.value, Semester.second.value]:
            semester_label = "第一學期" if semester == Semester.first.value else "第二學期"
            semester_label_en = "First Semester" if semester == Semester.first.value else "Second Semester"

            combination = {
                "value": f"{year}-{semester}",
                "academic_year": year,
                "semester": semester,
                "label": f"{year}學年{semester_label}",
                "label_en": f"Academic Year {year + 1911}-{year + 1912} {semester_label_en}",
                "is_current": year == taiwan_year and semester == current_semester,
                "sort_order": year * 10 + (1 if semester == Semester.first.value else 2),
            }

            # Add statistics if requested
            if include_statistics:
                count_result = await session.execute(
                    select(func.count(Application.id)).where(
                        and_(
                            Application.academic_year == year,
                            Application.semester == semester,
                        )
                    )
                )
                combination["application_count"] = count_result.scalar() or 0

            combinations.append(combination)

    # Sort by year and semester (newest first)
    combinations.sort(key=lambda x: x["sort_order"], reverse=True)

    return {
        "combinations": combinations,
        "current_combination": f"{taiwan_year}-{current_semester}",
        "total_combinations": len(combinations),
    }


@router.get("/active-academic-periods")
async def get_active_academic_periods(
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Get academic periods that have actual application data"""

    # Get distinct academic year/semester combinations that have applications
    stmt = (
        select(
            Application.academic_year,
            Application.semester,
            func.count(Application.id).label("application_count"),
            func.min(Application.created_at).label("first_application"),
            func.max(Application.created_at).label("last_application"),
        )
        .where(
            and_(
                Application.academic_year.is_not(None),
                Application.semester.is_not(None),
            )
        )
        .group_by(Application.academic_year, Application.semester)
        .order_by(Application.academic_year.desc(), Application.semester)
    )

    result = await session.execute(stmt)
    active_periods = []

    for row in result:
        semester_label = "第一學期" if row.semester == Semester.first.value else "第二學期"
        semester_label_en = "First Semester" if row.semester == Semester.first.value else "Second Semester"

        active_periods.append(
            {
                "value": f"{row.academic_year}-{row.semester}",
                "academic_year": row.academic_year,
                "semester": row.semester,
                "label": f"{row.academic_year}學年{semester_label}",
                "label_en": f"Academic Year {row.academic_year + 1911}-{row.academic_year + 1912} {semester_label_en}",
                "application_count": row.application_count,
                "first_application": row.first_application.isoformat() if row.first_application else None,
                "last_application": row.last_application.isoformat() if row.last_application else None,
            }
        )

    return {"active_periods": active_periods, "total_periods": len(active_periods)}


@router.get("/scholarship-periods")
async def get_scholarship_periods(
    scholarship_id: Optional[int] = Query(None, description="Scholarship type ID"),
    scholarship_code: Optional[str] = Query(None, description="Scholarship type code"),
    application_cycle: Optional[str] = Query(None, description="Application cycle filter (semester/yearly)"),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    """Get appropriate academic periods based on scholarship application cycle"""
    from datetime import datetime

    # Get current info
    current_year = datetime.now().year
    current_month = datetime.now().month
    taiwan_year = current_year - 1911
    current_semester = Semester.first.value if current_month >= 8 else Semester.second.value

    # Get scholarship info if specified
    scholarship_cycle = None
    scholarship_name = None

    if scholarship_id or scholarship_code:
        stmt = select(ScholarshipType)
        if scholarship_id:
            stmt = stmt.where(ScholarshipType.id == scholarship_id)
        elif scholarship_code:
            stmt = stmt.where(ScholarshipType.code == scholarship_code)

        result = await session.execute(stmt)
        scholarship = result.scalar_one_or_none()

        if scholarship:
            scholarship_cycle = scholarship.application_cycle
            scholarship_name = scholarship.name

    # Use provided cycle or detected cycle
    cycle = application_cycle or (scholarship_cycle.value if scholarship_cycle else ApplicationCycle.semester.value)

    periods = []

    if cycle == ApplicationCycle.yearly.value:
        # 學年制：只顯示學年選項
        for year_offset in range(-3, 3):
            year = taiwan_year + year_offset
            periods.append(
                {
                    "value": f"{year}",
                    "academic_year": year,
                    "semester": None,
                    "label": f"{year}學年",
                    "label_en": f"Academic Year {year + 1911}-{year + 1912}",
                    "is_current": year == taiwan_year,
                    "cycle": "yearly",
                    "sort_order": year,
                }
            )
    else:
        # 學期制：顯示學年學期組合
        for year_offset in range(-2, 3):
            year = taiwan_year + year_offset

            for semester in [Semester.first.value, Semester.second.value]:
                semester_label = "第一學期" if semester == Semester.first.value else "第二學期"
                semester_label_en = "First Semester" if semester == Semester.first.value else "Second Semester"

                periods.append(
                    {
                        "value": f"{year}-{semester}",
                        "academic_year": year,
                        "semester": semester,
                        "label": f"{year}學年{semester_label}",
                        "label_en": f"Academic Year {year + 1911}-{year + 1912} {semester_label_en}",
                        "is_current": year == taiwan_year and semester == current_semester,
                        "cycle": "semester",
                        "sort_order": year * 10 + (1 if semester == Semester.first.value else 2),
                    }
                )

    # Sort periods (newest first)
    periods.sort(key=lambda x: x["sort_order"], reverse=True)

    return ApiResponse(
        success=True,
        message="Scholarship periods retrieved successfully",
        data={
            "periods": periods,
            "cycle": cycle,
            "scholarship_name": scholarship_name,
            "current_period": f"{taiwan_year}-{current_semester}"
            if cycle == ApplicationCycle.semester.value
            else f"{taiwan_year}",
            "total_periods": len(periods),
        },
    )


@router.get("/scholarship-types-with-cycles")
async def get_scholarship_types_with_cycles(
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Get all scholarship types with their application cycles"""

    stmt = select(ScholarshipType).where(ScholarshipType.status == "active")
    result = await session.execute(stmt)
    scholarships = result.scalars().all()

    scholarship_info = []
    cycle_counts = {"semester": 0, "yearly": 0}

    for scholarship in scholarships:
        cycle = (
            scholarship.application_cycle.value if scholarship.application_cycle else ApplicationCycle.semester.value
        )
        cycle_counts[cycle] += 1

        scholarship_info.append(
            {
                "id": scholarship.id,
                "code": scholarship.code,
                "name": scholarship.name,
                "name_en": scholarship.name_en,
                "category": scholarship.category,
                "application_cycle": cycle,
                "cycle_label": "學年制" if cycle == ApplicationCycle.yearly.value else "學期制",
                "cycle_label_en": "Yearly" if cycle == ApplicationCycle.yearly.value else "Semester",
            }
        )

    return {
        "scholarships": scholarship_info,
        "cycle_counts": cycle_counts,
        "total_scholarships": len(scholarship_info),
    }
