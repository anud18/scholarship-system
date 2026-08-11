"""補充匯入 (Supplementary Import) API endpoints.

A college submits applications on behalf of students it is responsible for. It
replaced 批次匯入 for colleges, so both the downloadable template and the accepted
upload are the batch-import workbook — one generator, one parser, shared with the
admin panel (see batch_import_template_service / BatchImportService).

The rows become ordinary submitted applications — no rank, no CollegeRankingItem
— so the students flow through professor review and the college ranking exactly
like self-submitting applicants.

Gated per period by ScholarshipConfiguration.allow_supplementary_import, which
admin toggles from 系統管理 → 獎學金配置.
"""

import logging
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ValidationError
from app.core.security import require_college
from app.db.deps import get_db
from app.models.audit_log import AuditAction, AuditLog
from app.models.enums import Semester
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User
from app.schemas.response import ApiResponse
from app.services.batch_import_template_service import build_batch_import_template
from app.services.supplementary_import_service import SupplementaryImportService
from app.utils.application_helpers import get_college_code_from_data

from .college_review._helpers import _check_scholarship_permission, normalize_semester_value

logger = logging.getLogger(__name__)

router = APIRouter()

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

# Shared query-parameter contract with the batch-import endpoints so both college
# import panels address a period the same way.
_SCHOLARSHIP_TYPE_QUERY = Query(..., description="獎學金類型代碼", pattern=r"^[a-z_]{1,50}$")
_ACADEMIC_YEAR_QUERY = Query(..., description="學年度", ge=100, le=200)
_SEMESTER_QUERY = Query(None, description="學期", pattern=r"^(first|second|yearly)?$")


async def _resolve_scholarship(db: AsyncSession, scholarship_type: str) -> ScholarshipType:
    """Load the ScholarshipType (with sub-type configs) or 404."""
    stmt = (
        select(ScholarshipType)
        .options(selectinload(ScholarshipType.sub_type_configs))
        .where(ScholarshipType.code == scholarship_type)
    )
    scholarship = (await db.execute(stmt)).scalar_one_or_none()
    if not scholarship:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"獎學金類型 {scholarship_type} 不存在",
        )
    return scholarship


async def _resolve_configuration(
    db: AsyncSession,
    scholarship_type_id: int,
    academic_year: int,
    semester: Optional[str],
) -> Optional[ScholarshipConfiguration]:
    """Find the active configuration for a period.

    Yearly cycles store the semester as either NULL or "yearly" — match both,
    the same rule CollegeReviewService.assert_ranking_within_deadline uses.
    """
    normalized_semester = normalize_semester_value(semester)
    conditions = [
        ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
        ScholarshipConfiguration.academic_year == academic_year,
        ScholarshipConfiguration.is_active.is_(True),
    ]
    if normalized_semester is None:
        conditions.append(
            or_(
                ScholarshipConfiguration.semester.is_(None),
                ScholarshipConfiguration.semester == Semester.yearly.value,
            )
        )
    else:
        conditions.append(ScholarshipConfiguration.semester == normalized_semester)

    # A yearly cycle matches BOTH semester IS NULL and semester = 'yearly', so the
    # filter can hit two rows despite the (type, year, semester) unique constraint.
    # Order explicitly so availability and upload can never resolve different configs.
    stmt = (
        select(ScholarshipConfiguration)
        .options(selectinload(ScholarshipConfiguration.scholarship_type))
        .where(and_(*conditions))
        .order_by(ScholarshipConfiguration.id)
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


def _assert_bound_to_college(current_user: User) -> str:
    """補充匯入 imports only the caller's own students, so an unbound college
    account has no scope to import into."""
    college_code = (current_user.college_code or "").strip()
    if not college_code:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="使用者未綁定學院，無法使用補充匯入",
        )
    return college_code


async def _assert_scholarship_permission(db: AsyncSession, current_user: User, scholarship_type_id: int) -> None:
    if not await _check_scholarship_permission(current_user, scholarship_type_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="無權限操作此獎學金",
        )


@router.get("/availability")
async def get_supplementary_import_availability(
    scholarship_type: str = _SCHOLARSHIP_TYPE_QUERY,
    academic_year: int = _ACADEMIC_YEAR_QUERY,
    semester: Optional[str] = _SEMESTER_QUERY,
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """查詢某學年期是否已開放補充匯入。

    不因未開放而回 403 — 回傳 allowed=false 讓前端顯示說明，避免學院上傳後才被擋。

    **權限**: 僅限學院角色
    """
    _assert_bound_to_college(current_user)
    scholarship = await _resolve_scholarship(db, scholarship_type)
    await _assert_scholarship_permission(db, current_user, scholarship.id)

    cfg = await _resolve_configuration(db, scholarship.id, academic_year, semester)

    return ApiResponse(
        success=True,
        message="查詢成功",
        data={
            "allowed": bool(cfg and cfg.allow_supplementary_import),
            "configuration_id": cfg.id if cfg else None,
            "academic_year": academic_year,
            "semester": normalize_semester_value(semester),
        },
    )


@router.get("/template")
async def download_supplementary_import_template(
    scholarship_type: str = _SCHOLARSHIP_TYPE_QUERY,
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """下載補充匯入範本。

    內容與管理員的批次匯入範例檔完全相同（同一個產生器），因為兩者讀的是同一種
    檔案格式。不受 allow_supplementary_import 限制 — 學院可先準備資料，等管理員
    開放再上傳。

    **權限**: 僅限學院角色
    """
    _assert_bound_to_college(current_user)
    scholarship = await _resolve_scholarship(db, scholarship_type)
    await _assert_scholarship_permission(db, current_user, scholarship.id)

    payload = await build_batch_import_template(db, scholarship)

    filename = f"{scholarship.name}_補充匯入範例.xlsx"
    encoded = quote(filename, safe="")
    return StreamingResponse(
        iter([payload]),
        media_type=XLSX_MIME,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
            "Content-Length": str(len(payload)),
        },
    )


@router.post("/upload")
async def upload_supplementary_import(
    scholarship_type: str = _SCHOLARSHIP_TYPE_QUERY,
    academic_year: int = _ACADEMIC_YEAR_QUERY,
    semester: Optional[str] = _SEMESTER_QUERY,
    file: UploadFile = File(..., description="批次匯入格式的 Excel (.xlsx)"),
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """學院上傳批次匯入格式的 Excel，為新的申請學生建立申請。

    接受的檔案與管理員的批次匯入完全相同（同一個解析器），從本頁下載的範本即可。
    建立的是一般「已送出」申請：不帶名次、不寫入排名名單，學生依一般流程進入
    教授審查與學院排名。

    **權限**: 僅限學院角色，且該學年期需由管理員開放補充匯入
    """
    expected_college = _assert_bound_to_college(current_user)
    scholarship = await _resolve_scholarship(db, scholarship_type)

    # Authorize on the scholarship BEFORE reading the flag, so a college without
    # a grant gets a clear "no permission" 403 instead of a misleading
    # "feature not open" — and we don't leak another period's flag state.
    await _assert_scholarship_permission(db, current_user, scholarship.id)

    cfg = await _resolve_configuration(db, scholarship.id, academic_year, semester)
    if not cfg or not cfg.allow_supplementary_import:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="補充匯入功能尚未開放")

    if file.content_type and file.content_type != XLSX_MIME:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="只接受 .xlsx 檔案",
        )
    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="檔案大小不能超過 10 MB",
        )

    service = SupplementaryImportService(db)

    normalized_semester = normalize_semester_value(semester)
    rows, parse_errors = await service.parse_file(
        file_bytes,
        scholarship_type_id=scholarship.id,
        academic_year=academic_year,
        semester=normalized_semester,
    )
    if parse_errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="\n".join(parse_errors),
        )
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="檔案中沒有可匯入的學生資料",
        )

    semester_for_check = normalized_semester or "yearly"
    conflicts = await service.validate_no_duplicate_applications(
        rows,
        scholarship_type_id=scholarship.id,
        academic_year=academic_year,
        semester=semester_for_check,
    )
    if conflicts:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"以下學號已有申請記錄：{', '.join(conflicts)}",
        )

    student_ids = [r["student_id"] for r in rows]
    try:
        student_data_map, missing_ids, errored_ids = await service.fetch_student_data_bulk(
            student_ids,
            academic_year=academic_year,
            semester=normalize_semester_value(semester),
        )
    except ValueError as exc:
        logger.error("Supplementary import could not reach the student API: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="學籍系統目前無法使用，請稍後再試",
        ) from exc
    # A lookup that errored is NOT a wrong 學號 — say so, or the college goes
    # looking for a typo that isn't there.
    if errored_ids:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"學籍系統查詢失敗（未建立任何申請），請稍後重試：{', '.join(errored_ids)}",
        )
    if missing_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"學籍系統查無以下學號：{', '.join(missing_ids)}",
        )

    # A college may only import its own students. Use the canonical extractor so
    # we honor std_academyno → academy_code → college_code → std_college precedence.
    mismatched = []
    for sid, data in student_data_map.items():
        student_college = (get_college_code_from_data(data) or "").strip()
        if student_college != expected_college:
            mismatched.append(f"{sid}({student_college or '無學院'})")
    if mismatched:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"以下學生不屬於本學院（{expected_college}），無法匯入：{', '.join(mismatched)}",
        )

    try:
        user_map = await service.find_or_create_users(student_data_map)
        profile_map = await service.upsert_user_profiles(user_map, rows)
        imported_count, unresolved_professors = await service.create_applications(
            rows,
            user_map,
            student_data_map,
            cfg,
            importer_id=current_user.id,
            profile_map=profile_map,
        )
        await db.commit()
    except ValidationError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.message) from exc
    except IntegrityError as exc:
        # validate_no_duplicate_applications ran before the SIS fetch, so a student
        # who self-submitted (or was uploaded in a parallel sheet) in between only
        # collides at COMMIT, on uq_user_pure_new_app. Name the culprits — the
        # generic 500 below would send the college re-uploading the same file.
        await db.rollback()
        logger.warning("Supplementary import hit a duplicate-application race: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "匯入期間有學生已建立申請，未建立任何申請。" f"請移除已重複的學號後重新上傳：{', '.join(student_ids)}"
            ),
        ) from exc
    except Exception as exc:
        await db.rollback()
        logger.error("Supplementary import failed for user %s: %s", current_user.id, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="補充匯入失敗，未建立任何申請，請稍後再試或聯絡管理員",
        ) from exc

    logger.info(
        "Supplementary import: config_id=%s imported=%s by user=%s",
        cfg.id,
        imported_count,
        current_user.id,
    )

    try:
        audit_log = AuditLog.create_log(
            user_id=current_user.id,
            # Closest fit — Application/User/UserProfile rows created with PII
            action=AuditAction.pii_access.value,
            resource_type="scholarship_configuration",
            resource_id=str(cfg.id),
            description=f"補充匯入：建立 {imported_count} 筆申請",
            new_values={
                "configuration_id": cfg.id,
                "scholarship_type_id": scholarship.id,
                "academic_year": academic_year,
                "semester": normalize_semester_value(semester),
                "college_code": expected_college,
                "imported_count": imported_count,
                "student_ids": student_ids,
                "unresolved_professors": unresolved_professors,
            },
            status="success",
        )
        db.add(audit_log)
        await db.commit()
    except Exception as exc:  # audit failure must not block the import
        logger.warning("Failed to record supplementary import audit log: %s", exc, exc_info=True)
        await db.rollback()

    return ApiResponse(
        success=True,
        message=f"補充匯入成功，共新增 {imported_count} 位學生",
        data={
            "configuration_id": cfg.id,
            "imported_count": imported_count,
            "student_ids": student_ids,
            "unresolved_professors": unresolved_professors,
        },
    )
