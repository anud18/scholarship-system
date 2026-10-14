"""Validation for the college_code an admin assigns to a user account.

college_code scopes what a college-role reviewer can see, so an arbitrary
string (a typo, or a scanner probe like "../../etc/passwd") silently strands
the account with an empty college view. Every admin write path — POST /users,
PUT /users/{id}, PATCH /users/{id}/college, POST /auth/register — goes
through require_known_college_code.
"""

import logging
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.college_mappings import normalize_academy_code
from app.models.student import Academy

logger = logging.getLogger(__name__)

UNKNOWN_COLLEGE_CODE = "學院代碼不存在"


def normalize_college_code(college_code: Optional[str]) -> Optional[str]:
    """Trim, uppercase and remap retired codes (Y -> E); blank becomes None."""
    if college_code is None:
        return None
    code = college_code.strip().upper()
    return normalize_academy_code(code) if code else None


async def require_known_college_code(
    db: AsyncSession, college_code: Optional[str], *, actor_id: Optional[int] = None
) -> Optional[str]:
    """Return the normalized code if it is an academies.code, None for blank, else 422.

    The rejected value is logged server-side but never echoed in the response.
    """
    code = normalize_college_code(college_code)
    if code is None:
        return None
    if await db.scalar(select(Academy.id).where(Academy.code == code)) is not None:
        return code
    logger.warning(
        "Rejected unknown college_code %r",
        college_code,
        extra={"attempted_college_code": college_code, "actor_user_id": actor_id},
    )
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=UNKNOWN_COLLEGE_CODE)
