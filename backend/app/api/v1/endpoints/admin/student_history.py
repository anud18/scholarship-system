"""Admin endpoint: GET /admin/student-history/{student_number}."""

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.security import require_admin
from app.db.deps import get_db
from app.models.user import User
from app.services.student_scholarship_history_service import (
    StudentScholarshipHistoryService,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_STUDENT_NUMBER_PATTERN = re.compile(r"^[A-Za-z0-9]{4,15}$")


@router.get("/{student_number}")
async def get_student_scholarship_history(
    student_number: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Single-student scholarship history lookup. See spec for response shape."""
    if not _STUDENT_NUMBER_PATTERN.match(student_number):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="學號格式不正確",
        )

    service = StudentScholarshipHistoryService()
    try:
        data = await service.get_history(db, student_number)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    return {
        "success": True,
        "message": "Student history retrieved",
        "data": data.model_dump(mode="json"),
    }
