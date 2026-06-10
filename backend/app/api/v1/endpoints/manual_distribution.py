"""
Manual Distribution API Endpoints

Provides endpoints for admin to manually allocate scholarships to students.
"""

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_admin_user, get_db
from app.db.deps import get_sync_db
from app.db.session import AsyncSessionLocal
from app.models.application import Application
from app.models.college_review import CollegeRanking, CollegeRankingItem, ManualDistributionHistory
from app.models.email_management import EmailCategory
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User
from app.schemas.application import RevokeRequest, SuspendRequest
from app.services.email_service import EmailService
from app.services.manual_distribution_service import ManualDistributionService
from app.utils.date_utils import now_taipei_str

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
        )

        await db.commit()
        return {
            "success": True,
            "message": f"Restored {restore_result['restored_count']} allocations from history",
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
                CollegeRanking.is_finalized.is_(True),
                CollegeRanking.distribution_executed.is_(True),
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
        groups: dict[tuple, list] = {}
        for item in allocated_items:
            sub_type = item.allocated_sub_type or "general"
            key = (sub_type, item.allocation_config_id)
            groups.setdefault(key, []).append(item)

        group_data = []
        total_allocated = 0
        # None allocation_config_id (whole-period sentinel) sorts first via -1
        for (sub_type, config_id), items in sorted(
            groups.items(),
            key=lambda kv: (kv[0][0], kv[0][1] if kv[0][1] is not None else -1),
        ):
            # Display year = consumed config's academic_year (falls back to the
            # requesting year for whole-period rows with no linked config).
            consumed = items[0].allocation_config if items else None
            alloc_year = consumed.academic_year if consumed else academic_year
            students = []
            for item in items:
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
                        "is_renewal": app.is_renewal if app else False,
                        "renewal_year": app.renewal_year if app else None,
                    }
                )
            total_allocated += len(students)
            group_data.append(
                {
                    "sub_type": sub_type,
                    "allocation_config_id": config_id,
                    "allocation_year": alloc_year,
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Error generating rosters from distribution: {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="造冊產生失敗") from e


@router.post("/import-received-months")
async def import_received_months(
    scholarship_type_id: int = Query(..., description="Scholarship type ID"),
    academic_year: int = Query(..., description="Academic year"),
    semester: str = Query(..., description="Semester"),
    file: UploadFile = File(..., description="Excel file with columns: 學號, 已領月份數"),
    current_user=Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Import received months from Excel for students in a distribution."""
    import openpyxl
    from io import BytesIO

    # Validate file type
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="請上傳 Excel 檔案 (.xlsx)",
        )

    # Read Excel with size limit
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="檔案過大 (上限 5MB)")

    try:
        wb = openpyxl.load_workbook(BytesIO(content), read_only=True)
        ws = wb.active
        # Parse rows: expect header row then data rows
        rows = list(ws.iter_rows(min_row=2, values_only=True))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"無法解析 Excel 檔案，請確認格式正確: {type(e).__name__}",
        ) from e

    if not rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Excel 檔案沒有資料列")

    # Build student_id -> months mapping
    import_data: dict[str, int] = {}
    for row in rows:
        if len(row) < 2 or row[0] is None or row[1] is None:
            continue
        student_id = str(row[0]).strip()
        try:
            months = int(row[1])
        except (ValueError, TypeError):
            continue
        if months < 0:
            continue
        import_data[student_id] = months

    if not import_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="無法解析任何有效資料")

    # Find rankings matching the scholarship/year/semester combination
    if semester == "yearly":
        sem_condition = or_(
            CollegeRanking.semester.is_(None),
            CollegeRanking.semester == "annual",
            CollegeRanking.semester == "yearly",
        )
    else:
        sem_condition = CollegeRanking.semester == semester
    ranking_stmt = select(CollegeRanking.id).where(
        and_(
            CollegeRanking.scholarship_type_id == scholarship_type_id,
            CollegeRanking.academic_year == academic_year,
            sem_condition,
        )
    )
    ranking_result = await db.execute(ranking_stmt)
    ranking_ids = [r[0] for r in ranking_result.all()]

    if not ranking_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到對應的排名資料")

    # Get ranking items with their applications for student ID matching
    # Exclude soft-deleted applications
    stmt = (
        select(CollegeRankingItem, Application)
        .join(Application, CollegeRankingItem.application_id == Application.id)
        .where(
            and_(
                CollegeRankingItem.ranking_id.in_(ranking_ids),
                Application.deleted_at.is_(None),
            )
        )
    )
    result = await db.execute(stmt)
    item_pairs = result.all()

    # matched = unique students from the Excel that had a ranking item.
    # updated = number of ranking rows actually touched (same student can have
    # multiple items, e.g. different sub_types, and all of them are updated).
    matched_sids: set[str] = set()
    updated = 0

    for item, app in item_pairs:
        student_data = app.student_data or {}
        sid = student_data.get("std_stdcode", "")
        if sid in import_data:
            item.received_months = import_data[sid]
            item.received_months_source = "imported"
            updated += 1
            matched_sids.add(sid)

    not_found = [sid for sid in import_data if sid not in matched_sids]
    matched = len(matched_sids)

    await db.commit()

    return {
        "success": True,
        "message": f"成功匯入 {matched} 位學生（{updated} 筆紀錄）",
        "data": {
            "matched": matched,
            "not_found": not_found,
            "updated": updated,
        },
    }


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
):
    """撤銷已分發學生：從未鎖定造冊移除 + 標記 application 為 cancelled/revoked。"""
    service = ManualDistributionService(db)
    try:
        result = await service.revoke_allocation(
            application_id=application_id,
            admin_user_id=current_user.id,
            reason=request.reason,
        )
        await db.commit()
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
):
    """停發已分發學生：從未鎖定造冊移除 + 標記 application 為 cancelled/suspended。"""
    service = ManualDistributionService(db)
    try:
        result = await service.suspend_allocation(
            application_id=application_id,
            admin_user_id=current_user.id,
            reason=request.reason,
        )
        await db.commit()
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
):
    """恢復已撤銷/停發學生為正常分發（quota_allocation_status -> allocated）。
    不會自動還原造冊項目，需重新生成造冊。"""
    service = ManualDistributionService(db)
    try:
        result = await service.restore_allocation(
            application_id=application_id,
            admin_user_id=current_user.id,
        )
        await db.commit()
        return {"success": True, "message": "已恢復", "data": result}
    except ValueError as e:
        msg = str(e)
        # "not revoked/suspended" is a state conflict (the app isn't in a
        # restorable state) — surface it as 409, consistent with revoke/suspend.
        if "not revoked/suspended" in msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e
