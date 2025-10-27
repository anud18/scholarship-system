"""
Scholarship utility functions

Helper functions for scholarship-related operations across the application.
"""

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application


async def get_distinct_sub_types(
    db: AsyncSession,
    scholarship_type_id: Optional[int] = None,
    academic_year: Optional[int] = None,
    semester: Optional[str] = None,
) -> List[str]:
    """
    Get distinct sub-types from applications (configuration-driven)

    Args:
        db: Database session
        scholarship_type_id: If provided, only get sub-types for this scholarship type
        academic_year: If provided, filter by academic year
        semester: If provided, filter by semester

    Returns:
        List of distinct sub-type codes, defaults to ["general"] if none found
    """
    query = select(Application.sub_scholarship_type).distinct()

    if scholarship_type_id:
        query = query.where(Application.scholarship_type_id == scholarship_type_id)

    if academic_year:
        query = query.where(Application.academic_year == academic_year)

    if semester:
        query = query.where(Application.semester == semester)

    query = query.filter(Application.sub_scholarship_type.isnot(None))

    result = await db.execute(query)
    sub_types = result.scalars().all()

    return list(sub_types) if sub_types else ["general"]


def get_distinct_sub_types_sync(
    session,
    scholarship_type_id: Optional[int] = None,
    academic_year: Optional[int] = None,
    semester: Optional[str] = None,
) -> List[str]:
    """
    Synchronous version of get_distinct_sub_types for sync database sessions

    Args:
        session: Synchronous database session
        scholarship_type_id: If provided, only get sub-types for this scholarship type
        academic_year: If provided, filter by academic year
        semester: If provided, filter by semester

    Returns:
        List of distinct sub-type codes, defaults to ["general"] if none found
    """
    query = session.query(Application.sub_scholarship_type).distinct()

    if scholarship_type_id:
        query = query.filter(Application.scholarship_type_id == scholarship_type_id)

    if academic_year:
        query = query.filter(Application.academic_year == academic_year)

    if semester:
        query = query.filter(Application.semester == semester)

    query = query.filter(Application.sub_scholarship_type.isnot(None))

    result = query.all()
    sub_types = [st[0] for st in result] if result else []

    return sub_types if sub_types else ["general"]
