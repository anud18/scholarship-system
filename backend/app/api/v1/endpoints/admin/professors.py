"""
Admin Professors Management API Endpoints

Handles professor-related operations including:
- Professor listing and search
- Professor-student relationships
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin
from app.db.deps import get_db
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/professors")
async def get_available_professors(
    search: Optional[str] = Query(None, description="Search by name or NYCU ID"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get list of available professors for assignment."""

    try:
        stmt = select(User).where(User.role == UserRole.professor)

        if search:
            search_term = f"%{search.lower()}%"
            stmt = stmt.where(or_(func.lower(User.name).like(search_term), func.lower(User.nycu_id).like(search_term)))

        result = await db.execute(stmt)
        professors = result.scalars().all() if result else []

        serialized = [
            {
                "id": getattr(professor, "id", None),
                "name": getattr(professor, "name", ""),
                "email": getattr(professor, "email", ""),
                "nycu_id": getattr(professor, "nycu_id", ""),
            }
            for professor in professors
        ]

        return {"success": True, "message": f"Retrieved {len(serialized)} professors", "data": serialized}

    except SQLAlchemyError as exc:
        logger.error(f"Database error fetching professors: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch professors due to a database error.",
        ) from exc
    except Exception as exc:  # pragma: no cover - unexpected failure path
        logger.error(f"Unexpected error fetching professors: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch professors due to an unexpected error.",
        ) from exc


@router.get("/professor-student-relationships")
async def get_professor_student_relationships(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get all professor-student relationships with pagination"""
    # This endpoint needs to be implemented based on your relationship model
    # For now, return a placeholder response
    return {
        "success": True,
        "message": "Professor-student relationships retrieved successfully",
        "data": {
            "items": [],
            "total": 0,
            "page": page,
            "size": size,
            "pages": 0,
        },
    }


@router.post("/professor-student-relationships")
async def create_professor_student_relationship(
    relationship_data: Any,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new professor-student relationship"""
    # This endpoint needs to be implemented based on your relationship model
    # For now, return a placeholder response
    return {
        "success": True,
        "message": "Professor-student relationship created successfully",
        "data": relationship_data,
    }
