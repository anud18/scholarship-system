"""
Shared helper functions for college review endpoints
"""

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scholarship import ScholarshipType
from app.models.user import AdminScholarship, User

logger = logging.getLogger(__name__)


def normalize_semester_value(value: Optional[Any]) -> Optional[str]:
    """Normalize semester representations (None/yearly/enum) to canonical values."""
    if value is None:
        return None

    candidate = value.value if hasattr(value, "value") else str(value).strip()
    candidate_lower = candidate.lower()

    if candidate_lower.startswith("semester."):
        candidate_lower = candidate_lower.split(".", 1)[1]

    if candidate_lower in {"", "none", "yearly"}:
        return None

    return candidate_lower


async def _check_scholarship_permission(user: User, scholarship_type_id: int, db: AsyncSession) -> bool:
    """
    Check if a user has permission to access a specific scholarship type.

    Returns True if:
    - User is super_admin or admin
    - User has explicit permission for this scholarship
    """
    if user.is_super_admin() or user.is_admin():
        return True

    # Check if scholarship type exists and is active
    scholarship_stmt = select(ScholarshipType).where(ScholarshipType.id == scholarship_type_id)
    scholarship_result = await db.execute(scholarship_stmt)
    scholarship = scholarship_result.scalar_one_or_none()

    if not scholarship or scholarship.status != "active":
        return False

    # For college users, check if they have explicit permission
    if user.is_college():
        permission_stmt = select(AdminScholarship).where(
            AdminScholarship.admin_id == user.id, AdminScholarship.scholarship_id == scholarship_type_id
        )
        permission_result = await db.execute(permission_stmt)
        return permission_result.scalar_one_or_none() is not None

    return False


async def _check_academic_year_permission(user: User, academic_year: int, db: AsyncSession) -> bool:
    """
    Check if a user has permission to access a specific academic year.

    Returns True if:
    - User is super_admin or admin
    - User has configurations for this academic year
    """
    from app.models.scholarship import ScholarshipConfiguration

    if user.is_super_admin() or user.is_admin():
        return True

    # For college users, check if they have any configuration for this year
    if user.is_college():
        # Get scholarship IDs that user has permission for
        scholarship_ids_stmt = select(AdminScholarship.scholarship_id).where(AdminScholarship.admin_id == user.id)
        scholarship_ids_result = await db.execute(scholarship_ids_stmt)
        scholarship_ids = [row[0] for row in scholarship_ids_result.fetchall()]

        if not scholarship_ids:
            return False

        # Check if there are active configurations for this year
        config_stmt = select(ScholarshipConfiguration).where(
            ScholarshipConfiguration.scholarship_type_id.in_(scholarship_ids),
            ScholarshipConfiguration.academic_year == academic_year,
            ScholarshipConfiguration.is_active.is_(True),
        )
        config_result = await db.execute(config_stmt)
        return config_result.scalar_one_or_none() is not None

    return False


async def _check_application_review_permission(user: User, application_id: int, db: AsyncSession) -> bool:
    """
    Check if a user has permission to review a specific application.

    Returns True if:
    - User is super_admin or admin
    - User is college and has permission for the application's scholarship type
    """
    if user.is_super_admin() or user.is_admin():
        return True

    if not user.is_college():
        return False

    # Get the application and its scholarship type
    from app.models.application import Application

    app_stmt = select(Application).where(Application.id == application_id)
    app_result = await db.execute(app_stmt)
    application = app_result.scalar_one_or_none()

    if not application:
        return False

    # Check if user has permission for this scholarship type
    return await _check_scholarship_permission(user, application.scholarship_type_id, db)
