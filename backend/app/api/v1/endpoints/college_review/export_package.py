"""
Export Package API Endpoint

Generates and streams a ZIP file containing application materials
organized by department for college review.
"""

import logging
from io import BytesIO
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
    """Download a ZIP package of all application materials for a scholarship period."""

    # Normalize semester using shared helper (handles "yearly" → None, enum values, etc.)
    semester = normalize_semester_value(semester)

    # Permission checks
    if not await _check_scholarship_permission(current_user, scholarship_type_id, db):
        raise HTTPException(status_code=403, detail="無權限存取此獎學金類型")

    if not await _check_academic_year_permission(current_user, academic_year, db):
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
        raise HTTPException(status_code=400, detail=str(e))

    encoded_filename = quote(zip_filename)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
            "Content-Length": str(zip_buffer.getbuffer().nbytes),
        },
    )
