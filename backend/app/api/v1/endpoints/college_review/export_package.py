"""
Export Package API Endpoint

Validates the request, then streams a ZIP of application materials organised
by department for college review. The archive is produced on the fly in
bounded-size chunks (issue #1376): nothing is buffered whole, so there is no
Content-Length and the transfer is chunked. ``dry_run=true`` runs the same
checks and answers with a small ApiResponse instead of the archive.
"""

import logging
import time
from typing import AsyncIterator, Dict, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_roles
from app.db.deps import get_db
from app.models.user import User, UserRole
from app.services.export_package_service import ExportPackageService, ExportPlan
from app.services.minio_service import MinIOService
from app.utils.export_download import ZIP_MEDIA_TYPE

from ._helpers import _check_academic_year_permission, _check_scholarship_permission, normalize_semester_value

logger = logging.getLogger(__name__)

router = APIRouter()


async def _stream_with_audit(
    service: ExportPackageService, plan: ExportPlan, log_extra: Dict[str, object]
) -> AsyncIterator[bytes]:
    """Relay the ZIP chunks and log how the transfer ended.

    The status line and headers are already on the wire, so a failure here
    cannot become a 4xx/5xx: it is logged and re-raised, which aborts the
    connection and leaves the client with a visibly failed download rather
    than a silently short ZIP. A client disconnect closes the generator, so
    the final log line then carries completed=False.
    """
    started = time.monotonic()
    streamed = 0
    completed = False
    try:
        async for chunk in service.iter_export_zip(plan):
            streamed += len(chunk)
            yield chunk
        completed = True
    except Exception:
        logger.exception("export-package stream failed", extra=log_extra)
        raise
    finally:
        logger.info(
            "export-package stream ended: filename=%s size_bytes=%d completed=%s elapsed_s=%.1f",
            plan.zip_filename,
            streamed,
            completed,
            time.monotonic() - started,
            extra={**log_extra, "size_bytes": streamed, "completed": completed},
        )


async def _require_export_permissions(
    current_user: User, scholarship_type_id: int, academic_year: int, db: AsyncSession, log_extra: Dict[str, object]
) -> None:
    """403 unless the actor may see this scholarship type AND academic year.

    Denials are logged at warning level so repeated attempts can be flagged as
    potential bypass probing.
    """
    if not await _check_scholarship_permission(current_user, scholarship_type_id, db):
        logger.warning("export-package denied: scholarship permission missing", extra=log_extra)
        raise HTTPException(status_code=403, detail="無權限存取此獎學金類型")

    if not await _check_academic_year_permission(current_user, academic_year, db):
        logger.warning("export-package denied: academic-year permission missing", extra=log_extra)
        raise HTTPException(status_code=403, detail="無權限存取此學年度")


@router.get("/export-package")
async def export_application_package(
    scholarship_type_id: int = Query(..., description="Scholarship type ID"),
    academic_year: int = Query(..., description="Academic year"),
    semester: Optional[str] = Query(None, description="Semester (first/second/null for annual)"),
    dry_run: bool = Query(False, description="只檢查匯出條件（權限、資料筆數），不產生 ZIP"),
    current_user: User = Depends(require_roles(UserRole.college, UserRole.admin, UserRole.super_admin)),
    db: AsyncSession = Depends(get_db),
):
    """Stream a ZIP package of all application materials for a scholarship period.

    ``dry_run=true`` performs the same permission checks and data validation
    but answers with an ApiResponse (filename + application count) instead of
    the archive, so the UI can surface a 400/403 reason before handing the real
    download to the browser's download manager.

    SECURITY: Bulk PII export. Every call is audit-logged with the actor's
    user_id and role, scholarship/period filters and application count, and
    the end of the stream is logged with the bytes actually sent. 403
    (permission-denied) paths are also logged at warning level so repeated
    denials can be flagged as potential bypass attempts.
    """
    # Normalize semester using shared helper (handles "yearly" → None, enum values, etc.)
    semester = normalize_semester_value(semester)

    log_extra = {
        "actor_user_id": current_user.id,
        "actor_role": current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
        "scholarship_type_id": scholarship_type_id,
        "academic_year": academic_year,
        "semester": semester,
    }

    await _require_export_permissions(current_user, scholarship_type_id, academic_year, db, log_extra)

    # Determine college_code for filtering
    college_code = current_user.college_code if current_user.role == UserRole.college else None

    # Everything that can still turn into a 4xx/5xx happens here, before the
    # response starts; the streaming phase below does no DB work.
    try:
        service = ExportPackageService(db, MinIOService())
        plan = await service.prepare_export(
            scholarship_type_id=scholarship_type_id,
            academic_year=academic_year,
            semester=semester,
            college_code=college_code,
            # The precheck only needs the filename and count; skip the workbooks.
            include_summary_tables=not dry_run,
        )
    except ValueError as e:
        logger.warning("export-package rejected: %s", e, extra=log_extra, exc_info=True)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("export-package preparation failed", extra=log_extra)
        raise HTTPException(status_code=500, detail="匯出檔案產生失敗") from e

    logger.info(
        "export-package %s: filename=%s applications=%d college_code=%s",
        "precheck passed" if dry_run else "issued",
        plan.zip_filename,
        plan.application_count,
        college_code,
        extra={
            "actor_user_id": current_user.id,
            **log_extra,
            "export_filename": plan.zip_filename,
            "application_count": plan.application_count,
            "college_code": college_code,
            "dry_run": dry_run,
        },
    )

    if dry_run:
        return {
            "success": True,
            "message": "可匯出",
            "data": {"filename": plan.zip_filename, "application_count": plan.application_count},
        }

    # The stream does no DB work, but FastAPI tears request dependencies down
    # only after the last byte is sent: release the pooled connection now
    # rather than pinning it for a client-paced multi-GB download.
    await db.close()

    stream_extra = {**log_extra, "export_filename": plan.zip_filename, "college_code": college_code}
    return StreamingResponse(
        _stream_with_audit(service, plan, stream_extra),
        media_type=ZIP_MEDIA_TYPE,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(plan.zip_filename)}"},
    )
