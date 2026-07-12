"""Renewal-students import endpoints (approved renewals for 造冊).

Mirrors the batch-import endpoints (upload / confirm / history / details /
template) but is gated on the scholarship configuration's *renewal* application
window and creates approved renewal applications via ``RenewalImportService``.
"""

import logging
from io import BytesIO
from typing import Optional

import magic
import pandas as pd
from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BatchImportError
from app.core.security import get_current_user
from app.db.deps import get_db
from app.models.audit_log import AuditAction, AuditLog
from app.models.batch_import import BatchImport, BatchImportStatus
from app.models.enums import Semester
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole
from app.schemas.renewal_import import (
    RenewalImportConfirmRequest,
    RenewalImportConfirmResponse,
    RenewalImportDetailResponse,
    RenewalImportHistoryItem,
    RenewalImportHistoryResponse,
    RenewalImportUploadResponse,
)
from app.services.renewal_import_service import RenewalImportService, _to_semester_enum

router = APIRouter()
logger = logging.getLogger(__name__)

# Fixed renewal-import template columns (Traditional Chinese, ordered).
RENEWAL_TEMPLATE_COLUMNS = [
    "編號",
    "學院",
    "系所",
    "學生姓名",
    "學號",
    "學生年級",
    "學生是否申請續領",
    "續領審核結果",
    "獎學金類別",
    "郵局帳號",
    "指導教授本校人事編號",
]

# MIME types accepted for Excel/CSV uploads.
ALLOWED_UPLOAD_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
    "application/vnd.ms-excel",  # .xls
    "application/x-ole-storage",  # .xls (alternative)
    "text/csv",  # .csv
    "text/plain",  # .csv (sometimes detected as plain text)
    "application/csv",  # .csv (alternative)
}


def require_college_role(current_user: User = Depends(get_current_user)) -> User:
    """Dependency to require college, admin, or super admin role."""
    if current_user.role not in [UserRole.college, UserRole.admin, UserRole.super_admin]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="此功能僅限學院或管理員角色使用",
        )
    return current_user


async def _load_config_in_renewal_period(
    db: AsyncSession,
    scholarship_type_id: int,
    academic_year: int,
    semester: Optional[str],
) -> ScholarshipConfiguration:
    """Load the (year, semester) config and require it to be in its renewal window."""
    semester_enum = _to_semester_enum(semester)
    stmt = select(ScholarshipConfiguration).where(
        ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
        ScholarshipConfiguration.academic_year == academic_year,
    )
    stmt = (
        stmt.where(ScholarshipConfiguration.semester.is_(None))
        if semester_enum in (None, Semester.yearly)
        else stmt.where(ScholarshipConfiguration.semester == semester_enum)
    )
    config = (await db.execute(stmt)).scalar_one_or_none()
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"找不到 {academic_year} 學年度的獎學金配置",
        )
    if not config.is_renewal_application_period:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="此獎學金配置目前不在續領期間，無法匯入續領生",
        )
    return config


@router.post("/upload")
async def upload_renewal_import(
    file: UploadFile = File(..., description="續領生 Excel 或 CSV 檔案"),
    scholarship_type: str = Query(..., description="獎學金類型代碼", pattern=r"^[a-z_]{1,50}$"),
    academic_year: int = Query(..., description="學年度", ge=100, le=200),
    semester: Optional[str] = Query(None, description="學期", pattern=r"^(first|second|yearly)$"),
    current_user: User = Depends(require_college_role),
    db: AsyncSession = Depends(get_db),
):
    """上傳續領生名單，解析並回傳預覽（僅保留「是 + 通過」的續領生）。"""
    from app.core.config import settings

    stmt = select(ScholarshipType).where(ScholarshipType.code == scholarship_type)
    scholarship = (await db.execute(stmt)).scalar_one_or_none()
    if not scholarship:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"獎學金類型 {scholarship_type} 不存在",
        )

    normalized_semester = (semester.strip() if isinstance(semester, str) else semester) or None

    # Renewal-window gate — must run BEFORE reading the file.
    await _load_config_in_renewal_period(db, scholarship.id, academic_year, normalized_semester)

    college_code = current_user.college_code
    file_content = await file.read()
    if len(file_content) > settings.max_file_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"檔案大小超過限制 ({settings.max_file_size / 1024 / 1024:.1f}MB)",
        )

    mime_type = magic.from_buffer(file_content, mime=True)
    if mime_type not in ALLOWED_UPLOAD_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"不支援的檔案格式 ({mime_type})，請上傳 Excel (.xlsx, .xls) 或 CSV 檔案",
        )

    service = RenewalImportService(db)
    parsed, skipped, errors = await service.parse_renewal_excel(
        file_content, scholarship.id, academic_year, normalized_semester
    )
    val_errors, warnings = await service.validate_and_preview(
        parsed, college_code or "", scholarship.id, academic_year, normalized_semester
    )
    errors = list(errors) + list(val_errors)

    batch = await service.create_renewal_import_record(
        importer_id=current_user.id,
        college_code=college_code or "admin",
        scholarship_type_id=scholarship.id,
        academic_year=academic_year,
        semester=normalized_semester,
        file_name=file.filename,
        total_records=len(parsed),
    )

    # MinIO store (best-effort) — object 'renewal-imports/{id}/{filename}'.
    try:
        from app.services.minio_service import MinIOService

        MinIOService().client.put_object(
            bucket_name=settings.minio_bucket,
            object_name=f"renewal-imports/{batch.id}/{file.filename}",
            data=BytesIO(file_content),
            length=len(file_content),
            content_type=mime_type,
        )
        batch.file_path = f"renewal-imports/{batch.id}/{file.filename}"
    except Exception:
        logger.warning("Failed to upload renewal import file to MinIO", exc_info=True)

    batch.parsed_data = {"data": parsed, "skipped": skipped, "errors": errors, "warnings": warnings}
    db.add(
        AuditLog.create_log(
            user_id=current_user.id,
            action=AuditAction.create.value,
            resource_type="renewal_import",
            resource_id=str(batch.id),
            resource_name=file.filename,
            description=f"renewal import upload: {file.filename} ({len(parsed)} passed / {len(skipped)} skipped)",
        )
    )
    await db.commit()

    error_student_ids = {e["student_id"] for e in errors if e.get("student_id")}
    resp = RenewalImportUploadResponse(
        batch_id=batch.id,
        file_name=file.filename,
        total_records=len(parsed),
        skipped_records=len(skipped),
        preview_data=parsed,
        validation_summary={
            "valid_count": len(parsed) - len(error_student_ids),
            "invalid_count": len(errors),
            "skipped_count": len(skipped),
            "errors": errors[:50],
            "warnings": warnings[:50],
        },
    )
    return {
        "success": True,
        "message": f"上傳成功：{len(parsed)} 筆通過、{len(skipped)} 筆跳過、{len(errors)} 筆錯誤",
        "data": resp.model_dump(),
    }


@router.post("/{batch_id}/confirm")
async def confirm_renewal_import(
    batch_id: int,
    request: RenewalImportConfirmRequest | None = Body(None),
    current_user: User = Depends(require_college_role),
    db: AsyncSession = Depends(get_db),
):
    """確認匯入續領生，建立已核准的續領申請（供造冊使用）。"""
    batch = await db.get(BatchImport, batch_id)
    if not batch or batch.import_type != "renewal":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"續領匯入記錄 {batch_id} 不存在",
        )
    if batch.importer_id != current_user.id and current_user.role != UserRole.super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="僅能確認自己上傳的匯入",
        )
    if batch.import_status not in (
        BatchImportStatus.pending,
        BatchImportStatus.pending.value,
        BatchImportStatus.failed,
        BatchImportStatus.failed.value,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"此批次狀態為 {batch.import_status}，無法再次確認",
        )

    if request is not None and not request.confirm:
        batch.import_status = BatchImportStatus.cancelled.value
        await db.commit()
        return {
            "success": True,
            "message": "匯入已取消",
            "data": RenewalImportConfirmResponse(batch_id=batch_id, success_count=0, failed_count=0).model_dump(),
        }

    if not batch.parsed_data or "data" not in batch.parsed_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="匯入資料已過期，請重新上傳",
        )

    error_ids = {e["student_id"] for e in (batch.parsed_data.get("errors") or []) if e.get("student_id")}
    clean = [r for r in batch.parsed_data["data"] if r["student_id"] not in error_ids]
    if not clean:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="沒有可匯入的資料（皆有錯誤）",
        )

    batch.import_status = BatchImportStatus.processing.value
    await db.commit()

    service = RenewalImportService(db)
    try:
        normalized_semester = (batch.semester.strip() if isinstance(batch.semester, str) else batch.semester) or None
        created_ids, creation_errors = await service.create_renewals_from_batch(
            batch_import=batch,
            parsed_rows=clean,
            scholarship_type_id=batch.scholarship_type_id,
            academic_year=batch.academic_year,
            semester=normalized_semester,
        )
        batch.success_count = len(created_ids)
        batch.failed_count = len(creation_errors)
        batch.import_status = (
            BatchImportStatus.completed.value if not creation_errors else BatchImportStatus.partial.value
        )
        for cid in created_ids:
            db.add(
                AuditLog.create_log(
                    user_id=current_user.id,
                    action=AuditAction.import_.value,
                    resource_type="application",
                    resource_id=str(cid),
                    description=f"approved renewal created via renewal import {batch_id}",
                    meta_data={"batch_id": batch_id},
                )
            )
        await db.commit()
        return {
            "success": True,
            "message": f"匯入完成：建立 {len(created_ids)} 筆續領",
            "data": RenewalImportConfirmResponse(
                batch_id=batch_id,
                success_count=len(created_ids),
                failed_count=len(creation_errors),
                created_application_ids=created_ids,
            ).model_dump(),
        }
    except BatchImportError as e:
        logger.exception("Renewal import confirm failed", extra={"batch_id": batch_id})
        # Pre-try lookups (scholarship/config) raise before the service's own
        # rollback→failed handler runs, leaving the batch stuck in `processing`
        # (the state guard then blocks both retry and cancel). Reset it here so
        # the admin can act. In-try errors already set `failed`, so guard on it.
        if batch.import_status == BatchImportStatus.processing.value:
            batch.import_status = BatchImportStatus.failed.value
            await db.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=e.message,
        ) from e


@router.get("/history")
async def get_renewal_import_history(
    skip: int = Query(0, ge=0, description="跳過筆數"),
    limit: int = Query(20, ge=1, le=100, description="每頁筆數"),
    current_user: User = Depends(require_college_role),
    db: AsyncSession = Depends(get_db),
):
    """查詢續領匯入歷史記錄（僅顯示已確認的批次）。"""
    confirmed_statuses = [
        BatchImportStatus.completed,
        BatchImportStatus.partial,
        BatchImportStatus.failed,
        BatchImportStatus.cancelled,
    ]

    filters = [
        BatchImport.import_status.in_(confirmed_statuses),
        BatchImport.import_type == "renewal",
    ]
    if current_user.role != UserRole.super_admin:
        filters.append(BatchImport.importer_id == current_user.id)

    stmt = select(BatchImport).where(*filters).order_by(desc(BatchImport.created_at)).offset(skip).limit(limit)
    count_stmt = select(BatchImport).where(*filters)

    batch_imports = (await db.execute(stmt)).scalars().all()
    total = len((await db.execute(count_stmt)).scalars().all())

    importer_ids = {batch.importer_id for batch in batch_imports if batch.importer_id}
    importer_map = {}
    if importer_ids:
        importer_stmt = select(User.id, User.name).where(User.id.in_(importer_ids))
        importer_map = {row[0]: row[1] for row in (await db.execute(importer_stmt)).fetchall()}

    items = [
        RenewalImportHistoryItem(
            id=batch.id,
            college_code=batch.college_code,
            scholarship_type_id=batch.scholarship_type_id,
            academic_year=batch.academic_year,
            semester=batch.semester,
            file_name=batch.file_name,
            total_records=batch.total_records,
            success_count=batch.success_count,
            failed_count=batch.failed_count,
            import_status=batch.import_status.value if batch.import_status else "unknown",
            created_at=batch.created_at,
            importer_name=importer_map.get(batch.importer_id) if batch.importer_id else None,
        )
        for batch in batch_imports
    ]

    response_data = RenewalImportHistoryResponse(total=total, items=items)
    return {
        "success": True,
        "message": "查詢成功",
        "data": response_data.model_dump(),
    }


@router.get("/{batch_id}/details")
async def get_renewal_import_details(
    batch_id: int,
    current_user: User = Depends(require_college_role),
    db: AsyncSession = Depends(get_db),
):
    """查詢續領匯入詳細資訊。"""
    from app.models.application import Application

    batch_import = await db.get(BatchImport, batch_id)
    if not batch_import or batch_import.import_type != "renewal":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"續領匯入記錄 {batch_id} 不存在",
        )

    if batch_import.importer_id != current_user.id and current_user.role != UserRole.super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="僅能查看自己上傳的匯入記錄",
        )

    app_stmt = select(Application.id).where(Application.batch_import_id == batch_id)
    created_app_ids = [row[0] for row in (await db.execute(app_stmt)).fetchall()]

    importer_name = None
    if batch_import.importer_id:
        importer_stmt = select(User.name).where(User.id == batch_import.importer_id)
        importer_name = (await db.execute(importer_stmt)).scalar_one_or_none()

    response_data = RenewalImportDetailResponse(
        id=batch_import.id,
        college_code=batch_import.college_code,
        scholarship_type_id=batch_import.scholarship_type_id,
        academic_year=batch_import.academic_year,
        semester=batch_import.semester,
        file_name=batch_import.file_name,
        total_records=batch_import.total_records,
        success_count=batch_import.success_count,
        failed_count=batch_import.failed_count,
        error_summary=batch_import.error_summary,
        import_status=batch_import.import_status.value if batch_import.import_status else "unknown",
        created_at=batch_import.created_at,
        created_applications=created_app_ids,
    )

    return {
        "success": True,
        "message": "查詢成功",
        "data": response_data.model_dump(),
    }


@router.get("/template")
async def download_renewal_import_template(
    scholarship_type: str = Query(..., description="獎學金類型代碼", pattern=r"^[a-z_]{1,50}$"),
    current_user: User = Depends(require_college_role),
    db: AsyncSession = Depends(get_db),
):
    """下載續領匯入範例 Excel 檔案。

    **固定欄位**（繁體中文）：編號、學院、系所、學生姓名、學號、學生年級、
    學生是否申請續領、續領審核結果、獎學金類別、郵局帳號、指導教授本校人事編號。

    **注意**: 「獎學金類別」欄位可填 `國科會` 或 `教育部`；僅「學生是否申請續領=是」
    且「續領審核結果=通過」的列會被匯入。

    **權限**: 僅限 college 角色。
    """
    stmt = select(ScholarshipType).where(ScholarshipType.code == scholarship_type)
    scholarship = (await db.execute(stmt)).scalar_one_or_none()
    if not scholarship:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"獎學金類型 {scholarship_type} 不存在",
        )

    # Two example rows: one 否 (skipped), one 是/通過 (imported).
    sample_data = [
        {
            "編號": 1,
            "學院": "電機學院",
            "系所": "電機工程學系",
            "學生姓名": "王小明",
            "學號": "111111111",
            "學生年級": "博一",
            "學生是否申請續領": "否",
            "續領審核結果": "領獎期滿，無續領",
            "獎學金類別": "",
            "郵局帳號": "",
            "指導教授本校人事編號": "",
        },
        {
            "編號": 2,
            "學院": "電機學院",
            "系所": "電機工程學系",
            "學生姓名": "陳小華",
            "學號": "222222222",
            "學生年級": "博二",
            "學生是否申請續領": "是",
            "續領審核結果": "通過",
            "獎學金類別": "國科會",
            "郵局帳號": "1234567890123",
            "指導教授本校人事編號": "P001234",
        },
    ]

    df = pd.DataFrame(sample_data, columns=RENEWAL_TEMPLATE_COLUMNS)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="續領匯入範例")

        from openpyxl.utils import get_column_letter

        worksheet = writer.sheets["續領匯入範例"]
        for idx, col in enumerate(df.columns, 1):
            column_values = df.iloc[:, idx - 1].astype(str).tolist()
            all_content = [str(col)] + column_values
            max_length = max(len(text) for text in all_content) if all_content else 0
            max_chinese_in_cell = (
                max(sum(1 for c in text if "一" <= c <= "鿿") for text in all_content) if all_content else 0
            )
            adjusted_width = max_length + max_chinese_in_cell * 1.2 + 2
            worksheet.column_dimensions[get_column_letter(idx)].width = adjusted_width

    output.seek(0)

    from urllib.parse import quote

    filename = f"{scholarship.name}_續領匯入範例.xlsx"
    encoded_filename = quote(filename, encoding="utf-8")

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )
