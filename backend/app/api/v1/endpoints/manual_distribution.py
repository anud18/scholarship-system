"""
Manual Distribution API Endpoints

Provides endpoints for admin to manually allocate scholarships to students.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_admin_user, get_db
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.services.manual_distribution_service import ManualDistributionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/manual-distribution", tags=["Manual Distribution"])


class AllocationItem(BaseModel):
    ranking_item_id: int
    sub_type_code: Optional[str] = None
    allocation_year: Optional[int] = None  # Which year's quota to use (None = current year)


class AllocateRequest(BaseModel):
    scholarship_type_id: int
    academic_year: int
    semester: str
    allocations: list[AllocationItem]


class FinalizeRequest(BaseModel):
    scholarship_type_id: int
    academic_year: int
    semester: str


@router.get("/available-combinations")
async def get_admin_available_combinations(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Get all active scholarship types and configurations for admin distribution."""
    try:
        scholarship_result = await db.execute(
            select(ScholarshipType).where(ScholarshipType.status == "active")
        )
        scholarship_types_objs = scholarship_result.scalars().all()

        scholarship_types = [
            {
                "id": st.id,
                "code": st.code,
                "name": st.name,
                "name_en": st.name_en if st.name_en else st.name,
            }
            for st in scholarship_types_objs
        ]

        config_result = await db.execute(
            select(ScholarshipConfiguration).where(ScholarshipConfiguration.is_active)
        )
        configs = config_result.scalars().all()

        academic_years_set = set()
        semesters_set = set()
        has_yearly_scholarships = False

        for config in configs:
            if config.academic_year:
                academic_years_set.add(config.academic_year)
            if config.semester:
                raw_value = config.semester.value if hasattr(config.semester, "value") else str(config.semester)
                value_lower = raw_value.lower()
                if value_lower in {"yearly"}:
                    has_yearly_scholarships = True
                else:
                    semesters_set.add(value_lower)
            else:
                has_yearly_scholarships = True

        semester_strings = sorted(list(semesters_set))
        if has_yearly_scholarships:
            semester_strings.append("yearly")

        return {
            "success": True,
            "message": "Available combinations retrieved successfully",
            "data": {
                "scholarship_types": scholarship_types,
                "academic_years": sorted(list(academic_years_set)),
                "semesters": sorted(list(set(semester_strings))),
            },
        }
    except Exception as e:
        logger.error(f"Error retrieving admin available combinations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve available combinations",
        )


@router.get("/students")
async def get_students_for_distribution(
    scholarship_type_id: int = Query(...),
    academic_year: int = Query(...),
    semester: str = Query(...),
    college_code: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Get ranked students with allocation status for manual distribution."""
    service = ManualDistributionService(db)
    students = await service.get_students_for_distribution(
        scholarship_type_id, academic_year, semester, college_code
    )
    return {
        "success": True,
        "message": "Students retrieved successfully",
        "data": students,
    }


@router.get("/quota-status")
async def get_quota_status(
    scholarship_type_id: int = Query(...),
    academic_year: int = Query(...),
    semester: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Get real-time quota status per sub-type per college."""
    service = ManualDistributionService(db)
    quota_status = await service.get_quota_status(
        scholarship_type_id, academic_year, semester
    )
    return {
        "success": True,
        "message": "Quota status retrieved successfully",
        "data": quota_status,
    }


@router.post("/allocate")
async def allocate(
    request: AllocateRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Save manual allocation selections."""
    service = ManualDistributionService(db)
    try:
        result = await service.allocate(
            request.scholarship_type_id,
            request.academic_year,
            request.semester,
            [a.model_dump() for a in request.allocations],
        )
        await db.commit()
        return {
            "success": True,
            "message": f"Updated {result['updated_count']} allocations",
            "data": result,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/finalize")
async def finalize(
    request: FinalizeRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Finalize distribution - lock and update application statuses."""
    service = ManualDistributionService(db)
    try:
        result = await service.finalize(
            request.scholarship_type_id,
            request.academic_year,
            request.semester,
        )
        await db.commit()
        return {
            "success": True,
            "message": f"Distribution finalized: {result['approved_count']} approved, {result['rejected_count']} rejected",
            "data": result,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
