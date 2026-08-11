"""
Manual Distribution API Endpoints

Provides endpoints for admin to manually allocate scholarships to students.
"""

import logging
from typing import Literal, NamedTuple, Optional
from urllib.parse import quote as _url_quote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import get_current_admin_user, get_db
from app.db.deps import get_sync_db
from app.db.session import AsyncSessionLocal
from app.models.application import Application
from app.models.audit_log import AuditAction, AuditLog
from app.models.college_review import CollegeRanking, CollegeRankingItem, ManualDistributionHistory
from app.models.email_management import EmailCategory
from app.models.scholarship import ScholarshipConfiguration, ScholarshipSubTypeConfig, ScholarshipType
from app.models.user import User
from app.schemas.application import RevokeRequest, SuspendRequest
from app.services.application_audit_service import ApplicationAuditService
from app.services.email_service import EmailService
from app.services.manual_distribution_export_service import (
    ManualDistributionExportService,
    RecipientExportGroup,
    build_recipient_row,
)
from app.services.manual_distribution_service import ManualDistributionService
from app.utils.date_utils import now_taipei_str
from app.utils.export_download import XLSX_MEDIA_TYPE, sanitise_filename_part

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/manual-distribution", tags=["Manual Distribution"])


class AllocationItem(BaseModel):
    ranking_item_id: int
    sub_type_code: Optional[str] = None
    allocation_config_id: Optional[int] = None  # Consumed config (None = own requesting config)


class AllocateRequest(BaseModel):
    scholarship_type_id: int
    academic_year: int
    semester: str
    allocations: list[AllocationItem]


class AutoAllocatePreviewRequest(BaseModel):
    scholarship_type_id: int
    academic_year: int
    semester: str
    college_code: Optional[str] = None  # Restrict suggestions to one college
    # The caller's on-screen allocations for every row it renders, all colleges
    # — same shape as AllocateRequest.allocations, a null sub_type_code meaning
    # 未決. None (the field omitted) falls back to the saved state.
    staged: Optional[list[AllocationItem]] = None


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
        scholarship_result = await db.execute(select(ScholarshipType).where(ScholarshipType.status == "active"))
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

        config_result = await db.execute(select(ScholarshipConfiguration).where(ScholarshipConfiguration.is_active))
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
        logger.exception("Error retrieving admin available combinations")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve available combinations",
        ) from e


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
    students = await service.get_students_for_distribution(scholarship_type_id, academic_year, semester, college_code)
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
    quota_status = await service.get_quota_status(scholarship_type_id, academic_year, semester)
    return {
        "success": True,
        "message": "Quota status retrieved successfully",
        "data": quota_status,
    }


@router.get("/state")
async def get_distribution_state(
    scholarship_type_id: int = Query(...),
    academic_year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Return the full state needed by the manual distribution panel UI.

    Aggregates three views in one round trip:
      * ``renewal_allocations`` — approved renewals grouped by
        ``(sub_type, renewal_year)``, each marked ``has_challenge`` if a
        downstream challenge targets it.
      * ``available_quotas`` — per ``(sub_type, allocation_year)``: total /
        used / remaining where ``used`` comes from approved renewals.
      * ``candidates`` — non-renewal applicants in ranking order, with
        ``is_challenge`` and a ``challenged_renewal`` block when present.

    See ``ManualDistributionService.compute_distribution_state`` for details.
    """
    service = ManualDistributionService(db)
    try:
        state = await service.compute_distribution_state(scholarship_type_id, academic_year)
    except ValueError as e:
        # _get_active_config raises ValueError when no active config exists.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return {
        "success": True,
        "message": "OK",
        "data": state,
    }


@router.post("/auto-allocate-preview")
async def auto_allocate_preview(
    request: AutoAllocatePreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Generate auto-allocation suggestions without persisting.

    Pass `college_code` to run the distribution for a single college; quotas are
    still evaluated against the global live remaining, so the result matches what
    a whole-scholarship run would suggest for that college.

    Pass `staged` — the caller's on-screen allocations for every row it renders,
    every college — to have the suggestions computed against that state instead
    of the saved one. Unticked rows free their slot immediately; hand-ticked rows
    are treated as decided. POST rather than GET because that state is a body,
    not a query string; nothing is written either way.
    """
    try:
        service = ManualDistributionService(db)
        suggestions = await service.auto_allocate_preview(
            scholarship_type_id=request.scholarship_type_id,
            academic_year=request.academic_year,
            semester=request.semester,
            college_code=request.college_code,
            staged=[item.model_dump() for item in request.staged] if request.staged is not None else None,
        )
        return {
            "success": True,
            "message": "Auto-allocation preview generated",
            "data": {"suggestions": suggestions},
        }
    except ValueError as e:
        # A malformed overlay (e.g. the same ranking item staged twice) — same
        # 400 `allocate` gives for the same wire shape.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.error("Error generating auto-allocation preview: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate auto-allocation preview") from e


@router.post("/preview-distribution")
async def preview_distribution(
    request: AllocateRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Dry-run: compute the release_chain for the proposed allocations.

    For each proposed allocation whose application is a challenge, returns
    the renewal that would be cancelled and the next pure-new waitlist
    candidate who would inherit the freed slot. Nothing is persisted.

    Used by the admin Manual Distribution panel to surface release-chain
    impact before commit (spec Section 14.2).
    """
    service = ManualDistributionService(db)
    try:
        preview = await service.preview_release_chain([a.model_dump() for a in request.allocations])
        return {
            "success": True,
            "message": "Preview computed",
            "data": preview,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


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
            admin_user_id=current_user.id,
        )
        await db.commit()
        return {
            "success": True,
            "message": f"Updated {result['updated_count']} allocations",
            "data": result,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


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
            admin_user_id=current_user.id,
        )
        await db.commit()
        return {
            "success": True,
            "message": f"Distribution finalized: {result['approved_count']} approved, {result['rejected_count']} rejected",
            "data": result,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e


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
        logger.exception("Error retrieving distribution history")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve distribution history",
        ) from e


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
            admin_user_id=current_user.id,
        )

        await db.commit()
        message = f"Restored {restore_result['restored_count']} allocations from history"
        if restore_result.get("skipped_rejected"):
            message += f" ({restore_result['skipped_rejected']} skipped: sub-type rejected in review)"
        if restore_result.get("skipped_cancelled"):
            message += f" ({restore_result['skipped_cancelled']} skipped: application revoked/suspended)"
        return {
            "success": True,
            "message": message,
            "data": restore_result,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.exception("Error restoring from history")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to restore from history",
        ) from e


class _AllocatedGroup(NamedTuple):
    """One 分發 group: sub_type × 消耗配額 config, with its allocated items."""

    sub_type: str
    allocation_config_id: Optional[int]
    allocation_year: Optional[int]
    items: list  # CollegeRankingItem, with .application / .allocation_config loaded


async def _load_allocated_groups(
    db: AsyncSession,
    *,
    scholarship_type_id: int,
    academic_year: int,
    semester: str,
) -> Optional[list[_AllocatedGroup]]:
    """Load every allocated student, grouped by (sub_type, allocation_config_id).

    Shared by the distribution-summary JSON endpoint and its file export, so the
    exported file can never disagree with the 分發結果名單 panel.

    Returns ``None`` when NO finalized+executed ranking exists (尚未完成分發) —
    distinct from ``[]``, which means the distribution ran but zero students are
    currently allocated.
    """
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
            CollegeRanking.is_finalized.is_(True),
            CollegeRanking.distribution_executed.is_(True),
        )
    )
    ranking_result = await db.execute(ranking_stmt)
    rankings = ranking_result.scalars().all()
    if not rankings:
        return None

    ranking_ids = [r.id for r in rankings]

    # 取得所有已分配的 ranking items
    items_stmt = (
        select(CollegeRankingItem)
        .where(
            and_(
                CollegeRankingItem.ranking_id.in_(ranking_ids),
                CollegeRankingItem.is_allocated.is_(True),
            )
        )
        .options(
            selectinload(CollegeRankingItem.application),
            selectinload(CollegeRankingItem.allocation_config),
        )
    )
    items_result = await db.execute(items_stmt)
    allocated_items = items_result.scalars().all()

    # 按 (sub_type, allocation_config_id) 分組；顯示年度取自消耗的配置
    grouped: dict[tuple, list] = {}
    for item in allocated_items:
        sub_type = item.allocated_sub_type or "general"
        grouped.setdefault((sub_type, item.allocation_config_id), []).append(item)

    groups: list[_AllocatedGroup] = []
    # None allocation_config_id (whole-period sentinel) sorts first via -1
    for (sub_type, config_id), items in sorted(
        grouped.items(),
        key=lambda kv: (kv[0][0], kv[0][1] if kv[0][1] is not None else -1),
    ):
        # Display year = consumed config's academic_year (falls back to the
        # requesting year for whole-period rows with no linked config).
        consumed = items[0].allocation_config if items else None
        alloc_year = consumed.academic_year if consumed else academic_year
        groups.append(
            _AllocatedGroup(
                sub_type=sub_type,
                allocation_config_id=config_id,
                allocation_year=alloc_year,
                items=items,
            )
        )
    return groups


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
    try:
        groups = await _load_allocated_groups(
            db,
            scholarship_type_id=scholarship_type_id,
            academic_year=academic_year,
            semester=semester,
        )
        if groups is None:
            return {
                "success": True,
                "message": "尚未完成分發",
                "data": {"groups": [], "total_allocated": 0},
            }

        group_data = []
        total_allocated = 0
        for group in groups:
            students = []
            for item in group.items:
                app = item.application
                sd = (app.student_data or {}) if app else {}
                students.append(
                    {
                        "ranking_item_id": item.id,
                        "application_id": item.application_id,
                        "student_name": sd.get("std_cname", ""),
                        "student_id": sd.get("std_stdcode", ""),
                        "college_code": sd.get("std_academyno") or sd.get("trm_academyno", ""),
                        "college_name": sd.get("trm_academyname", ""),
                        "department_name": sd.get("trm_depname", ""),
                        "rank_position": item.rank_position,
                        # The panel renders a red "N" instead of the rank for these.
                        # An allocated-but-college-rejected row is legitimate: admin
                        # may allocate over a college rejection (see CollegeRankingItem
                        # .college_rejected), so the list must not hide it.
                        "college_rejected": bool(item.college_rejected),
                        "is_supplementary": bool(item.is_supplementary),
                        "is_renewal": app.is_renewal if app else False,
                        "renewal_year": app.renewal_year if app else None,
                    }
                )
            total_allocated += len(students)
            group_data.append(
                {
                    "sub_type": group.sub_type,
                    "allocation_config_id": group.allocation_config_id,
                    "allocation_year": group.allocation_year,
                    "count": len(students),
                    "students": students,
                }
            )

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
        ) from e


_SEMESTER_EXPORT_LABELS = {"first": "第一學期", "second": "第二學期"}


def _export_sort_key(item) -> tuple:
    """(學院代碼, 名次, id) for one allocated ranking item.

    The college code comes from the same snapshot keys the JSON summary uses, so
    the export and the panel bucket a student into the same college.
    """
    app = item.application
    sd = (app.student_data or {}) if app else {}
    college = sd.get("std_academyno") or sd.get("trm_academyno") or ""
    return (str(college), item.rank_position or 0, item.id)


@router.get("/distribution-summary/export")
async def export_distribution_summary(
    request: Request,
    scholarship_type_id: int = Query(...),
    academic_year: int = Query(...),
    semester: str = Query(...),
    format: Literal["xlsx", "pdf"] = Query("xlsx", description="Output format: xlsx (default) or pdf"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """Export the 分發結果名單 as Excel (default) or PDF — 受獎名冊 layout.

    Reads through the SAME ``_load_allocated_groups`` loader as the JSON
    endpoint, so the file can never show a student the panel would not.

    Carries no 身分證字號 and no 匯款帳號, but it is NOT the PII-free case the
    college 分發結果 export is: on top of 學號/姓名/系所 it emits 國籍, 性別,
    碩士畢業院/校/系所 and 首次註冊入學日期, plus three derived flags that label a
    student as 在職生 / 陸港澳生 / 休學. That is personal data about identified
    students leaving the system in bulk, so it writes a ``pii_access`` AuditLog
    like the 學生資料彙整表 export does.
    """
    log_extra = {
        "actor_user_id": current_user.id,
        "actor_role": (current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)),
        "scholarship_type_id": scholarship_type_id,
        "academic_year": academic_year,
        "semester": semester,
        "export_format": format,
    }

    groups = await _load_allocated_groups(
        db,
        scholarship_type_id=scholarship_type_id,
        academic_year=academic_year,
        semester=semester,
    )
    if groups is None:
        logger.warning("distribution-summary export rejected: no finalized distribution", extra=log_extra)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="尚未完成分發，無法匯出")
    if not groups:
        logger.warning("distribution-summary export rejected: no allocated students", extra=log_extra)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="尚無已分配的學生可匯出")

    # Sub-type display labels from configuration (NOT the hardcoded legacy maps);
    # unknown / historical codes fall through as the raw code. Deliberately no
    # is_active filter: a finalized distribution may reference a since-disabled
    # sub-type and its label must still render.
    label_rows = await db.execute(
        select(ScholarshipSubTypeConfig.sub_type_code, ScholarshipSubTypeConfig.name).where(
            ScholarshipSubTypeConfig.scholarship_type_id == scholarship_type_id
        )
    )
    sub_type_labels = {code: name for code, name in label_rows.all()}

    # scalar_one() not scalar_one_or_none(): finalized rankings exist for this id
    # (checked above) and they FK onto scholarship_types — a miss here is a broken
    # invariant that must surface, not be papered over with a default title.
    scholarship_name = (
        await db.execute(select(ScholarshipType.name).where(ScholarshipType.id == scholarship_type_id))
    ).scalar_one()

    export_groups = []
    _seq_counter = 0
    for group in groups:
        # Order by 學院 first, then rank. rank_position is scoped to ONE college's
        # CollegeRanking, so sorting on it alone interleaves colleges (工學院 #1,
        # 電機 #1, 工學院 #2 …) and the roster reads as if the ranks were global.
        # Matches get_students_for_distribution's (college_code, rank_position).
        ordered_items = sorted(group.items, key=_export_sort_key)
        rows = []
        for _it in ordered_items:
            _seq_counter += 1
            rows.append(build_recipient_row(_seq_counter, _it.application))
        export_groups.append(
            RecipientExportGroup(
                label=sub_type_labels.get(group.sub_type, group.sub_type),
                sub_type_code=group.sub_type,
                allocation_year=group.allocation_year,
                rows=rows,
            )
        )

    semester_label = _SEMESTER_EXPORT_LABELS.get(semester, "")
    title = f"{academic_year}學年度{semester_label}{scholarship_name}分發名單"
    stem = sanitise_filename_part(f"分發名單_{scholarship_name}_{academic_year}學年度{semester_label}".rstrip("_"))
    encoded = _url_quote(f"{stem}.{format}", safe="")

    service = ManualDistributionExportService()
    if format == "pdf":
        payload = service.build_pdf(groups=export_groups, title=title)
        media_type = "application/pdf"
    else:
        payload = service.build_workbook(groups=export_groups, title=title)
        media_type = XLSX_MEDIA_TYPE

    student_count = sum(len(g.rows) for g in export_groups)
    logger.info(
        "distribution-summary export issued: groups=%d students=%d size_bytes=%d",
        len(export_groups),
        student_count,
        len(payload),
        extra={**log_extra, "export_filename": f"{stem}.{format}", "size_bytes": len(payload)},
    )

    exported_app_ids = [item.application_id for group in groups for item in group.items]
    try:
        db.add(
            AuditLog(
                user_id=current_user.id,
                action=AuditAction.pii_access.value,
                resource_type="scholarship_type",
                resource_id=str(scholarship_type_id),
                resource_name=f"{stem}.{format}",
                description=(
                    f"匯出分發名單（含國籍/性別/學籍檢核）: scholarship_type_id={scholarship_type_id}, "
                    f"academic_year={academic_year}, records={student_count}"
                ),
                ip_address=(request.client.host if request.client else None),
                user_agent=request.headers.get("user-agent"),
                request_method=request.method,
                request_url=str(request.url.path),
                status="success",
                meta_data={
                    "scholarship_type_id": scholarship_type_id,
                    "academic_year": academic_year,
                    "semester": semester,
                    "record_count": student_count,
                    "application_ids": exported_app_ids,
                    "pii_fields": ["std_cname", "std_stdcode", "std_nation", "std_sex", "std_enrollyear"],
                    "export_format": format,
                },
            )
        )
        await db.commit()
    except Exception:  # noqa: BLE001 — audit failure must not block the download
        logger.exception("Failed to record pii_access audit log for distribution-summary export")
        await db.rollback()

    return StreamingResponse(
        iter([payload]),
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
            "Content-Length": str(len(payload)),
        },
    )


class GenerateRostersRequest(BaseModel):
    scholarship_type_id: int
    academic_year: int
    semester: str
    student_verification_enabled: bool = False  # 預設不驗證，加快速度
    force_regenerate: bool = False


def _build_roster_generation_message(created: int, skipped: int, locked: int) -> str:
    """Honest summary of a batch roster generation (issue #1033).

    Existing rosters are never silently reported as a blank success: skipped
    ones name how to rebuild (force_regenerate), and locked ones say why they
    could not be rebuilt. Pure function so the wording stays under test.
    """
    message = f"成功產生 {created} 個造冊"
    if skipped:
        message += (
            f"；另有 {skipped} 個造冊已存在、未重新產生。" "如需以最新分發/學生資料重建，請帶 force_regenerate=true。"
        )
    if locked:
        message += f"；有 {locked} 個造冊已鎖定，無法重新產生。"
    return message


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
        result = service.generate_rosters_from_distribution(
            scholarship_type_id=request.scholarship_type_id,
            academic_year=request.academic_year,
            semester=request.semester,
            created_by_user_id=current_user.id,
            student_verification_enabled=request.student_verification_enabled,
            force_regenerate=request.force_regenerate,
        )

        def _summarize(r):
            return {
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

        roster_summaries = [_summarize(r) for r in result.created]
        skipped_summaries = [_summarize(r) for r in result.skipped]
        locked_summaries = [_summarize(r) for r in result.locked]

        message = _build_roster_generation_message(len(result.created), len(result.skipped), len(result.locked))

        return {
            "success": True,
            "message": message,
            "data": {
                "rosters_created": len(result.created),
                "rosters_skipped": len(result.skipped),
                "rosters_locked": len(result.locked),
                "rosters": roster_summaries,
                "skipped_rosters": skipped_summaries,
                "locked_rosters": locked_summaries,
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Error generating rosters from distribution: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="造冊產生失敗") from e


async def _send_cancellation_email(
    to: str,
    subject: str,
    body: str,
    action_label: str,
    application_id: int,
    sent_by_user_id: int,
) -> None:
    """Background task: deliver a prepared 停發/撤銷 notification email.

    Opens its own session — it runs after the request's session is closed.
    Best-effort: any failure is logged and never surfaces to the admin."""
    try:
        async with AsyncSessionLocal() as session:
            await EmailService().send_email(
                to=to,
                subject=subject,
                body=body,
                db=session,
                email_category=EmailCategory.system,
                application_id=application_id,
                sent_by_user_id=sent_by_user_id,
            )
    except Exception:
        logger.exception(
            "Failed to send %s notification email to admin %s for application %s",
            action_label,
            to,
            application_id,
        )


async def _notify_admin_of_cancellation(
    db: AsyncSession,
    background_tasks: BackgroundTasks,
    application_id: int,
    admin_user: User,
    action_label: str,
    reason: str,
) -> None:
    """Queue a record of a 停發/撤銷 operation to be emailed to the acting admin.

    The message is composed here (the action is already committed), but the
    SMTP delivery runs as a background task AFTER the response is sent — an
    unreachable/slow mail server must not stall the revoke/suspend API."""
    if not admin_user.email:
        logger.warning(
            "Admin %s has no email address; skipping %s notification for application %s",
            admin_user.id,
            action_label,
            application_id,
        )
        return

    try:
        result = await db.execute(select(Application).where(Application.id == application_id))
        application = result.scalar_one_or_none()
        if application is None:
            logger.warning("Application %s not found; skipping %s notification email", application_id, action_label)
            return
        student_data = application.student_data or {}
        student_name = student_data.get("std_cname", "")
        student_id = student_data.get("std_stdcode", "")
        operated_at = now_taipei_str()
        # name is nullable until SSO populates it on first login
        admin_name = admin_user.name or admin_user.nycu_id

        subject = f"【獎學金系統】{action_label}操作通知 - {application.app_id}"
        body = (
            f"{admin_name} 您好：\n\n"
            f"您已對下列獎學金申請執行「{action_label}」操作：\n\n"
            f"申請編號：{application.app_id}\n"
            f"學生姓名：{student_name}（{student_id}）\n"
            f"獎學金：{application.scholarship_name or ''}\n"
            f"{action_label}原因：{reason}\n"
            f"操作時間：{operated_at}\n\n"
            "此郵件為系統自動發送的操作紀錄通知，請勿直接回覆。"
        )

        background_tasks.add_task(
            _send_cancellation_email,
            admin_user.email,
            subject,
            body,
            action_label,
            application_id,
            admin_user.id,
        )
    except Exception:
        logger.exception(
            "Failed to queue %s notification email to admin %s for application %s",
            action_label,
            admin_user.email,
            application_id,
        )


@router.post("/applications/{application_id}/revoke")
async def revoke_application_allocation(
    application_id: int,
    request: RevokeRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
    http_request: Request = None,
):
    """撤銷學生獎學金：從未鎖定造冊移除 + 標記 application 為 cancelled/revoked。

    分發前後皆可執行——分發前撤銷等同把該生排除於本次分發（預設分發不再建議、
    確認分發會略過）。復原時會回到撤銷當下的狀態。"""
    service = ManualDistributionService(db)
    try:
        result = await service.revoke_allocation(
            application_id=application_id,
            admin_user_id=current_user.id,
            reason=request.reason,
        )
        await db.commit()
        await ApplicationAuditService(db).log_application_revoke(
            application_id=application_id,
            app_id=result.get("app_id", f"APP-{application_id}"),
            user=current_user,
            reason=request.reason,
            prior_quota_status=result.get("prior_quota_allocation_status"),
            affected_unlocked_rosters=result.get("affected_unlocked_rosters"),
            request=http_request,
        )
        await _notify_admin_of_cancellation(db, background_tasks, application_id, current_user, "撤銷", request.reason)
        return {"success": True, "message": "已撤銷", "data": result}
    except ValueError as e:
        msg = str(e)
        if "already" in msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e


@router.post("/applications/{application_id}/suspend")
async def suspend_application_allocation(
    application_id: int,
    request: SuspendRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
    http_request: Request = None,
):
    """停發學生獎學金：從未鎖定造冊移除 + 標記 application 為 cancelled/suspended。

    分發前後皆可執行——分發前停發（休學/退學/畢業）等同把該生排除於本次分發。
    復原時會回到停發當下的狀態。"""
    service = ManualDistributionService(db)
    try:
        result = await service.suspend_allocation(
            application_id=application_id,
            admin_user_id=current_user.id,
            reason=request.reason,
        )
        await db.commit()
        await ApplicationAuditService(db).log_application_suspend(
            application_id=application_id,
            app_id=result.get("app_id", f"APP-{application_id}"),
            user=current_user,
            reason=request.reason,
            prior_quota_status=result.get("prior_quota_allocation_status"),
            affected_unlocked_rosters=result.get("affected_unlocked_rosters"),
            request=http_request,
        )
        await _notify_admin_of_cancellation(db, background_tasks, application_id, current_user, "停發", request.reason)
        return {"success": True, "message": "已停發", "data": result}
    except ValueError as e:
        msg = str(e)
        if "already" in msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e


@router.post("/applications/{application_id}/restore")
async def restore_application_allocation(
    application_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
    http_request: Request = None,
):
    """恢復已撤銷/停發學生：回到撤銷/停發當下的狀態。

    分發後撤銷者回到 approved/allocated 並重新佔用名額；分發前撤銷者回到當時的
    申請狀態，重新成為可分發的候選人。不會自動還原造冊項目，需重新生成造冊。"""
    service = ManualDistributionService(db)
    try:
        result = await service.restore_allocation(
            application_id=application_id,
            admin_user_id=current_user.id,
        )
        await db.commit()
        # G9 (#971): link the restore to the original revoke/suspend log row.
        original_log = await db.execute(
            select(AuditLog.id)
            .where(
                AuditLog.resource_type == "application",
                AuditLog.resource_id == str(application_id),
                AuditLog.action.in_((AuditAction.revoke.value, AuditAction.suspend.value)),
            )
            .order_by(AuditLog.id.desc())
            .limit(1)
        )
        original_log_id = original_log.scalar_one_or_none()
        await ApplicationAuditService(db).log_application_restore(
            application_id=application_id,
            app_id=result.get("app_id", f"APP-{application_id}"),
            user=current_user,
            prior_status=result.get("restored_from", "unknown"),
            restored_quota_status=result.get("quota_allocation_status"),
            prior_reason=result.get("restored_reason"),
            original_cancellation_log_id=original_log_id,
            request=http_request,
        )
        return {"success": True, "message": "已恢復", "data": result}
    except ValueError as e:
        msg = str(e)
        # "not revoked/suspended" is a state conflict (the app isn't in a
        # restorable state) — surface it as 409, consistent with revoke/suspend.
        if "not revoked/suspended" in msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e
