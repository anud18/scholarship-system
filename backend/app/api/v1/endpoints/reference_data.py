"""
Reference data API endpoints for lookup tables
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.core.deps import get_db
from app.models.student import (
    Degree, Identity, StudyingStatus, SchoolIdentity, 
    Academy, Department, EnrollType
)

router = APIRouter()


@router.get("/degrees")
async def get_degrees(
    session: AsyncSession = Depends(get_db),
) -> List[dict]:
    """Get all degree types"""
    result = await session.execute(select(Degree))
    degrees = result.scalars().all()
    
    return [
        {
            "id": degree.id,
            "name": degree.name
        }
        for degree in degrees
    ]


@router.get("/identities")
async def get_identities(
    session: AsyncSession = Depends(get_db),
) -> List[dict]:
    """Get all student identity types"""
    result = await session.execute(select(Identity))
    identities = result.scalars().all()
    
    return [
        {
            "id": identity.id,
            "name": identity.name
        }
        for identity in identities
    ]


@router.get("/studying-statuses")
async def get_studying_statuses(
    session: AsyncSession = Depends(get_db),
) -> List[dict]:
    """Get all studying status types"""
    result = await session.execute(select(StudyingStatus))
    statuses = result.scalars().all()
    
    return [
        {
            "id": status.id,
            "name": status.name
        }
        for status in statuses
    ]


@router.get("/school-identities")
async def get_school_identities(
    session: AsyncSession = Depends(get_db),
) -> List[dict]:
    """Get all school identity types"""
    result = await session.execute(select(SchoolIdentity))
    school_identities = result.scalars().all()
    
    return [
        {
            "id": school_identity.id,
            "name": school_identity.name
        }
        for school_identity in school_identities
    ]


@router.get("/academies")
async def get_academies(
    session: AsyncSession = Depends(get_db),
) -> List[dict]:
    """Get all academy/college information"""
    result = await session.execute(select(Academy).order_by(Academy.code))
    academies = result.scalars().all()
    
    return [
        {
            "id": academy.id,
            "code": academy.code,
            "name": academy.name
        }
        for academy in academies
    ]


@router.get("/departments")
async def get_departments(
    session: AsyncSession = Depends(get_db),
) -> List[dict]:
    """Get all department information"""
    result = await session.execute(select(Department).order_by(Department.code))
    departments = result.scalars().all()
    
    return [
        {
            "id": department.id,
            "code": department.code,
            "name": department.name
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
            "degree_name": enroll_type.degree.name if enroll_type.degree else None
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
    enroll_types_result = await session.execute(select(EnrollType).options(selectinload(EnrollType.degree)).order_by(EnrollType.degreeId, EnrollType.code))
    
    degrees = degrees_result.scalars().all()
    identities = identities_result.scalars().all()
    statuses = statuses_result.scalars().all()
    school_identities = school_identities_result.scalars().all()
    academies = academies_result.scalars().all()
    departments = departments_result.scalars().all()
    enroll_types = enroll_types_result.scalars().all()
    
    return {
        "degrees": [
            {"id": degree.id, "name": degree.name}
            for degree in degrees
        ],
        "identities": [
            {"id": identity.id, "name": identity.name}
            for identity in identities
        ],
        "studying_statuses": [
            {"id": status.id, "name": status.name}
            for status in statuses
        ],
        "school_identities": [
            {"id": school_identity.id, "name": school_identity.name}
            for school_identity in school_identities
        ],
        "academies": [
            {
                "id": academy.id,
                "code": academy.code,
                "name": academy.name
            }
            for academy in academies
        ],
        "departments": [
            {
                "id": department.id,
                "code": department.code,
                "name": department.name
            }
            for department in departments
        ],
        "enroll_types": [
            {
                "degree_id": enroll_type.degreeId,
                "code": enroll_type.code,
                "name": enroll_type.name,
                "name_en": enroll_type.name_en,
                "degree_name": enroll_type.degree.name if enroll_type.degree else None
            }
            for enroll_type in enroll_types
        ]
    }


@router.get("/semesters")
async def get_available_semesters() -> dict:
    """Get available semester and academic year options for dynamic generation"""
    from datetime import datetime
    
    # Get current Taiwan academic year (民國年)
    current_year = datetime.now().year
    taiwan_year = current_year - 1911
    
    # Generate academic years: current - 2 to current + 2
    academic_years = []
    for year_offset in range(-2, 3):
        year = taiwan_year + year_offset
        academic_years.append({
            "value": year,
            "label": f"{year}學年度",
            "label_en": f"AY{year}",
            "is_current": year_offset == 0
        })
    
    # Semester options
    semesters = [
        {"value": 1, "label": "第一學期", "label_en": "First Semester"},
        {"value": 2, "label": "第二學期", "label_en": "Second Semester"},
        {"value": 3, "label": "暑期", "label_en": "Summer"}
    ]
    
    return {
        "academic_years": academic_years,
        "semesters": semesters,
        "current_academic_year": taiwan_year,
        "current_western_year": current_year
    }