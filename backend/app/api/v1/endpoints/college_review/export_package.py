"""
Export Package API Endpoint

Generates and streams a ZIP file containing application materials
organized by department for college review.
"""

import logging
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_roles
from app.db.deps import get_db
from app.models.user import User, UserRole
from app.services.export_package_service import ExportPackageService
from app.services.minio_service import MinIOService

from ._helpers import _check_academic_year_permission, _check_scholarship_permission, normalize_semester_value

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/export-package")
async def export_application_package(
    scholarship_type_id: int = Query(..., description="Scholarship type ID"),
    academic_year: int = Query(..., description="Academic year"),
    semester: Optional[str] = Query(None, description="Semester (first/second/null for annual)"),
    current_user: User = Depends(require_roles(UserRole.college, UserRole.admin, UserRole.super_admin)),
    db: AsyncSession = Depends(get_db),
):
    """Download a ZIP package of all application materials for a scholarship period.

    SECURITY: Bulk PII export. Every call is audit-logged with the actor's
    user_id and role, scholarship/period filters, and the resulting file
    size. 403 (permission-denied) paths are also logged at warning level
    so repeated denials can be flagged as potential bypass attempts.
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

    # Permission checks
    if not await _check_scholarship_permission(current_user, scholarship_type_id, db):
        logger.warning("export-package denied: scholarship permission missing", extra=log_extra)
        raise HTTPException(status_code=403, detail="無權限存取此獎學金類型")

    if not await _check_academic_year_permission(current_user, academic_year, db):
        logger.warning("export-package denied: academic-year permission missing", extra=log_extra)
        raise HTTPException(status_code=403, detail="無權限存取此學年度")

    # Determine college_code for filtering
    college_code = current_user.college_code if current_user.role == UserRole.college else None

    try:
        minio_service = MinIOService()
        service = ExportPackageService(db, minio_service)
        zip_buffer, zip_filename = await service.generate_export_zip(
            scholarship_type_id=scholarship_type_id,
            academic_year=academic_year,
            semester=semester,
            college_code=college_code,
        )
    except ValueError as e:
        logger.warning("export-package rejected: %s", e, extra=log_extra)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception("export-package zip generation failed", extra=log_extra)
        raise HTTPException(status_code=500, detail="匯出檔案產生失敗") from e

    file_size = zip_buffer.getbuffer().nbytes
    logger.info(
        "export-package issued: filename=%s size_bytes=%d college_code=%s",
        zip_filename,
        file_size,
        college_code,
        extra={**log_extra, "filename": zip_filename, "size_bytes": file_size, "college_code": college_code},
    )

    encoded_filename = quote(zip_filename)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
            "Content-Length": str(file_size),
        },
    )
