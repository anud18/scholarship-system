"""
Admin API Helper Functions

Shared utilities for admin endpoints including:
- Permission checks
- Common query filters
- Response formatters
"""

import logging
from typing import List

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin
from app.db.deps import get_db
from app.models.user import AdminScholarship, User, UserRole

logger = logging.getLogger(__name__)


def require_super_admin(current_user: User = Depends(require_admin)) -> User:
    """Require super admin role"""
    if not current_user.is_super_admin():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin access required")
    return current_user


async def get_allowed_scholarship_ids(current_user: User, db: AsyncSession) -> List[int]:
    """
    Get list of scholarship IDs the user has permission to access

    Returns:
        Empty list for super admin (has access to all)
        List of scholarship_type_ids for admin/college users
    """
    if current_user.is_super_admin():
        # Super admin can see all scholarships
        return []

    if current_user.role in [UserRole.admin, UserRole.college]:
        # Get user's scholarship permissions
        permission_stmt = select(AdminScholarship.scholarship_id).where(AdminScholarship.admin_id == current_user.id)
        permission_result = await db.execute(permission_stmt)
        return [row[0] for row in permission_result.fetchall()]

    return []


def apply_scholarship_filter(stmt, scholarship_type_id_column, allowed_scholarship_ids: List[int]):
    """
    Apply scholarship permission filter to a SQLAlchemy statement

    Args:
        stmt: SQLAlchemy select statement
        scholarship_type_id_column: Column to filter on (e.g., Application.scholarship_type_id)
        allowed_scholarship_ids: List of allowed scholarship IDs (empty for super admin)

    Returns:
        Modified statement with filter applied (if needed)
    """
    if allowed_scholarship_ids:
        # Apply filter for non-super-admin users
        return stmt.where(scholarship_type_id_column.in_(allowed_scholarship_ids))
    return stmt
