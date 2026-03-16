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
from app.db.deps import get_sync_db
from app.models.college_review import ManualDistributionHistory
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


class DistributionHistoryItem(BaseModel):
    id: int
    operation_type: str
    change_summary: Optional[str]
    total_allocated: Optional[int]
    created_at: str
    created_by: Optional[int]


class RestoreRequest(BaseModel):
    history_id: int


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


@router.get("/auto-allocate-preview")
async def auto_allocate_preview(
    scholarship_type_id: int = Query(...),
    academic_year: int = Query(...),
    semester: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Generate auto-allocation suggestions without persisting."""
    try:
        service = ManualDistributionService(db)
        suggestions = await service.auto_allocate_preview(
            scholarship_type_id=scholarship_type_id,
            academic_year=academic_year,
            semester=semester,
        )
        return {
            "success": True,
            "message": "Auto-allocation preview generated",
            "data": {"suggestions": suggestions},
        }
    except Exception as e:
        logger.error("Error generating auto-allocation preview: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate auto-allocation preview")


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


@router.get("/{scholarship_type_id}/history")
async def get_distribution_history(
    scholarship_type_id: int,
    academic_year: int = Query(...),
    semester: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Get allocation history for a scholarship/year/semester combination."""
    try:
        result = await db.execute(
            select(ManualDistributionHistory)
            .where(
                ManualDistributionHistory.scholarship_type_id == scholarship_type_id,
                ManualDistributionHistory.academic_year == academic_year,
                ManualDistributionHistory.semester == semester,
            )
            .order_by(ManualDistributionHistory.created_at.desc())
        )
        histories = result.scalars().all()

        history_data = [
            {
                "id": h.id,
                "operation_type": h.operation_type,
                "change_summary": h.change_summary,
                "total_allocated": h.total_allocated,
                "created_at": h.created_at.isoformat() if h.created_at else None,
                "created_by": h.created_by,
            }
            for h in histories
        ]

        return {
            "success": True,
            "message": "Distribution history retrieved successfully",
            "data": history_data,
        }
    except Exception as e:
        logger.error(f"Error retrieving distribution history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve distribution history",
        )


@router.post("/{scholarship_type_id}/restore")
async def restore_from_history(
    scholarship_type_id: int,
    request: RestoreRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Restore allocations from a specific history record."""
    service = ManualDistributionService(db)
    try:
        # Fetch the history record
        result = await db.execute(
            select(ManualDistributionHistory).where(
                ManualDistributionHistory.id == request.history_id,
                ManualDistributionHistory.scholarship_type_id == scholarship_type_id,
            )
        )
        history = result.scalar_one_or_none()

        if not history:
            raise ValueError("History record not found")

        # Restore allocations from snapshot
        restore_result = await service.restore_from_history(
            scholarship_type_id,
            history.academic_year,
            history.semester,
            history.allocations_snapshot,
        )

        await db.commit()
        return {
            "success": True,
            "message": f"Restored {restore_result['restored_count']} allocations from history",
            "data": restore_result,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error restoring from history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to restore from history",
        )


@router.get("/distribution-summary")
async def get_distribution_summary(
    scholarship_type_id: int = Query(...),
    academic_year: int = Query(...),
    semester: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """
    取得分發結果摘要：所有被分發的學生及其分配到的獎學金子類型。
    回傳所有已分配學生，按 sub_type × allocation_year 分組。
    """
    from sqlalchemy import and_, or_
    from sqlalchemy.orm import selectinload
    from app.models.college_review import CollegeRanking, CollegeRankingItem
    from app.models.application import Application

    try:
        # 取得已完成分發的排名
        if semester in ("annual", "yearly", ""):
            sem_filter = or_(
                CollegeRanking.semester.is_(None),
                CollegeRanking.semester == "annual",
                CollegeRanking.semester == "yearly",
            )
        else:
            sem_filter = CollegeRanking.semester == semester

        ranking_stmt = select(CollegeRanking).where(
            and_(
                CollegeRanking.scholarship_type_id == scholarship_type_id,
                CollegeRanking.academic_year == academic_year,
                sem_filter,
                CollegeRanking.is_finalized == True,
                CollegeRanking.distribution_executed == True,
            )
        )
        ranking_result = await db.execute(ranking_stmt)
        rankings = ranking_result.scalars().all()

        if not rankings:
            return {
                "success": True,
                "message": "尚未完成分發",
                "data": {"groups": [], "total_allocated": 0},
            }

        ranking_ids = [r.id for r in rankings]

        # 取得所有已分配的 ranking items
        items_stmt = (
            select(CollegeRankingItem)
            .where(
                and_(
                    CollegeRankingItem.ranking_id.in_(ranking_ids),
                    CollegeRankingItem.is_allocated == True,
                )
            )
            .options(selectinload(CollegeRankingItem.application))
        )
        items_result = await db.execute(items_stmt)
        allocated_items = items_result.scalars().all()

        # 按 (sub_type, allocation_year) 分組
        groups: dict[tuple, list] = {}
        for item in allocated_items:
            sub_type = item.allocated_sub_type or "general"
            alloc_year = item.allocation_year or academic_year
            key = (sub_type, alloc_year)
            groups.setdefault(key, []).append(item)

        group_data = []
        total_allocated = 0
        for (sub_type, alloc_year), items in sorted(groups.items()):
            students = []
            for item in items:
                app = item.application
                sd = (app.student_data or {}) if app else {}
                students.append({
                    "ranking_item_id": item.id,
                    "application_id": item.application_id,
                    "student_name": sd.get("std_cname", ""),
                    "student_id": sd.get("std_stdcode", ""),
                    "college_code": sd.get("std_academyno") or sd.get("trm_academyno", ""),
                    "college_name": sd.get("trm_academyname", ""),
                    "department_name": sd.get("trm_depname", ""),
                    "rank_position": item.rank_position,
                })
            total_allocated += len(students)
            group_data.append({
                "sub_type": sub_type,
                "allocation_year": alloc_year,
                "count": len(students),
                "students": students,
            })

        return {
            "success": True,
            "message": f"共 {total_allocated} 位學生已分發",
            "data": {
                "groups": group_data,
                "total_allocated": total_allocated,
            },
        }
    except Exception as e:
        logger.error(f"Error getting distribution summary: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="取得分發摘要失敗",
        )


class GenerateRostersRequest(BaseModel):
    scholarship_type_id: int
    academic_year: int
    semester: str
    student_verification_enabled: bool = False  # 預設不驗證，加快速度
    force_regenerate: bool = False


@router.post("/generate-rosters-from-distribution")
async def generate_rosters_from_distribution(
    request: GenerateRostersRequest,
    sync_db=Depends(get_sync_db),
    current_user=Depends(get_current_admin_user),
):
    """
    從矩陣分發結果批次產生造冊。

    針對每個唯一的 (allocation_year, sub_type) 組合建立獨立的造冊。
    例如：115 年度分發後，可能產生 nstc-115、nstc-114、moe_1w-115 等多個造冊。
    """
    from app.services.roster_service import RosterService

    service = RosterService(sync_db)
    try:
        rosters = service.generate_rosters_from_distribution(
            scholarship_type_id=request.scholarship_type_id,
            academic_year=request.academic_year,
            semester=request.semester,
            created_by_user_id=current_user.id,
            student_verification_enabled=request.student_verification_enabled,
            force_regenerate=request.force_regenerate,
        )

        roster_summaries = [
            {
                "id": r.id,
                "roster_code": r.roster_code,
                "sub_type": r.sub_type,
                "allocation_year": r.allocation_year,
                "project_number": r.project_number,
                "period_label": r.period_label,
                "status": r.status.value,
                "qualified_count": r.qualified_count,
                "disqualified_count": r.disqualified_count,
                "total_amount": str(r.total_amount),
            }
            for r in rosters
        ]

        return {
            "success": True,
            "message": f"成功產生 {len(rosters)} 個造冊",
            "data": {
                "rosters_created": len(rosters),
                "rosters": roster_summaries,
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error generating rosters from distribution: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"造冊產生失敗: {str(e)}",
        )
