"""
Professor-Student Relationship Management API Endpoints

Manages relationships between professors and students for access control
and academic oversight.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin, require_roles
from app.db.deps import get_db
from app.models.professor_student import ProfessorStudentRelationship
from app.models.user import User, UserRole

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("")
async def get_professor_student_relationships(
    professor_id: Optional[int] = Query(None, description="Filter by professor ID"),
    student_id: Optional[int] = Query(None, description="Filter by student ID"),
    relationship_type: Optional[str] = Query(None, description="Filter by relationship type"),
    status: Optional[str] = Query(None, description="Filter by active status (active/inactive)"),
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(require_roles(UserRole.professor, UserRole.admin, UserRole.super_admin)),
    db: AsyncSession = Depends(get_db),
):
    """
    Get professor-student relationships with optional filtering

    Professors can only view their own relationships.
    Admins can view all relationships.
    """
    try:
        # Build query
        query = select(ProfessorStudentRelationship)

        # Apply filters
        if professor_id is not None:
            query = query.where(ProfessorStudentRelationship.professor_id == professor_id)
        elif current_user.role == "professor":
            # Professors can only see their own relationships
            query = query.where(ProfessorStudentRelationship.professor_id == current_user.id)

        if student_id is not None:
            query = query.where(ProfessorStudentRelationship.student_id == student_id)

        if relationship_type:
            query = query.where(ProfessorStudentRelationship.relationship_type == relationship_type)

        if status:
            is_active = status.lower() == "active"
            query = query.where(ProfessorStudentRelationship.is_active == is_active)

        # Apply pagination
        query = query.offset((page - 1) * size).limit(size)

        # Execute query
        result = await db.execute(query)
        relationships = result.scalars().all()

        # Convert to dict
        relationships_data = [
            {
                "id": rel.id,
                "professor_id": rel.professor_id,
                "student_id": rel.student_id,
                "relationship_type": rel.relationship_type,
                "status": "active" if rel.is_active else "inactive",
                "start_date": rel.created_at.isoformat() if rel.created_at else None,
                "end_date": rel.updated_at.isoformat() if not rel.is_active and rel.updated_at else None,
                "notes": rel.notes,
            }
            for rel in relationships
        ]

        logger.info(f"Retrieved {len(relationships_data)} professor-student relationships")

        return {
            "success": True,
            "message": "查詢成功",
            "data": relationships_data,
        }

    except Exception as e:
        logger.error(f"Error fetching professor-student relationships: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while fetching relationships",
        )


@router.post("")
async def create_professor_student_relationship(
    professor_id: int,
    student_id: int,
    relationship_type: str,
    status: Optional[str] = "active",
    start_date: Optional[str] = None,
    notes: Optional[str] = None,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new professor-student relationship

    Only admins can create relationships.
    """
    try:
        # Verify users exist
        prof_query = await db.execute(select(User).where(User.id == professor_id))
        professor = prof_query.scalar_one_or_none()
        if not professor or professor.role not in ["professor", "admin"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid professor ID or user is not a professor",
            )

        student_query = await db.execute(select(User).where(User.id == student_id))
        student = student_query.scalar_one_or_none()
        if not student or student.role != "student":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid student ID or user is not a student",
            )

        # Check for existing relationship
        existing_query = await db.execute(
            select(ProfessorStudentRelationship).where(
                ProfessorStudentRelationship.professor_id == professor_id,
                ProfessorStudentRelationship.student_id == student_id,
                ProfessorStudentRelationship.relationship_type == relationship_type,
            )
        )
        existing = existing_query.scalar_one_or_none()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Relationship already exists",
            )

        # Create relationship
        relationship = ProfessorStudentRelationship(
            professor_id=professor_id,
            student_id=student_id,
            relationship_type=relationship_type,
            is_active=(status == "active"),
            notes=notes,
            created_by=current_user.id,
        )

        db.add(relationship)
        await db.commit()
        await db.refresh(relationship)

        logger.info(f"Created professor-student relationship: {relationship.id}")

        return {
            "success": True,
            "message": "關係建立成功",
            "data": {
                "id": relationship.id,
                "professor_id": relationship.professor_id,
                "student_id": relationship.student_id,
                "relationship_type": relationship.relationship_type,
                "status": "active" if relationship.is_active else "inactive",
                "start_date": relationship.created_at.isoformat() if relationship.created_at else None,
                "notes": relationship.notes,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating professor-student relationship: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while creating relationship",
        )


@router.put("/{id}")
async def update_professor_student_relationship(
    id: int = Path(..., description="Relationship ID"),
    relationship_type: Optional[str] = None,
    status: Optional[str] = None,
    end_date: Optional[str] = None,
    notes: Optional[str] = None,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Update an existing professor-student relationship

    Only admins can update relationships.
    """
    try:
        # Get existing relationship
        query = await db.execute(select(ProfessorStudentRelationship).where(ProfessorStudentRelationship.id == id))
        relationship = query.scalar_one_or_none()

        if not relationship:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Relationship not found",
            )

        # Update fields
        if relationship_type is not None:
            relationship.relationship_type = relationship_type

        if status is not None:
            relationship.is_active = status == "active"

        if notes is not None:
            relationship.notes = notes

        await db.commit()
        await db.refresh(relationship)

        logger.info(f"Updated professor-student relationship: {relationship.id}")

        return {
            "success": True,
            "message": "關係更新成功",
            "data": {
                "id": relationship.id,
                "professor_id": relationship.professor_id,
                "student_id": relationship.student_id,
                "relationship_type": relationship.relationship_type,
                "status": "active" if relationship.is_active else "inactive",
                "start_date": relationship.created_at.isoformat() if relationship.created_at else None,
                "end_date": (
                    relationship.updated_at.isoformat()
                    if not relationship.is_active and relationship.updated_at
                    else None
                ),
                "notes": relationship.notes,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating professor-student relationship: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while updating relationship",
        )


@router.delete("/{id}")
async def delete_professor_student_relationship(
    id: int = Path(..., description="Relationship ID"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a professor-student relationship

    Only admins can delete relationships.
    """
    try:
        # Get existing relationship
        query = await db.execute(select(ProfessorStudentRelationship).where(ProfessorStudentRelationship.id == id))
        relationship = query.scalar_one_or_none()

        if not relationship:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Relationship not found",
            )

        # Delete relationship
        await db.delete(relationship)
        await db.commit()

        logger.info(f"Deleted professor-student relationship: {id}")

        return {
            "success": True,
            "message": "關係刪除成功",
            "data": None,
        }

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting professor-student relationship: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while deleting relationship",
        )
