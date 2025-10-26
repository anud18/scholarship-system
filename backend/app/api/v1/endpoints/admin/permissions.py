"""
Admin Scholarship Permissions Management API Endpoints

Handles scholarship permission operations for admin and college users
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import check_scholarship_permission, get_current_user, require_admin
from app.db.deps import get_db
from app.models.scholarship import ScholarshipType
from app.models.user import AdminScholarship, User, UserRole
from app.schemas.common import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/scholarship-permissions")
async def get_scholarship_permissions(
    user_id: Optional[int] = Query(None, description="Filter by user ID"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get scholarship permissions (admin only)"""

    # Special handling for super_admin when filtering by user_id
    if user_id:
        # Check if the filtered user is a super_admin
        target_user_stmt = select(User).where(User.id == user_id)
        target_user_result = await db.execute(target_user_stmt)
        target_user = target_user_result.scalar_one_or_none()

        if target_user and target_user.is_super_admin():
            # Super admin has access to all scholarships
            from app.models.scholarship import ScholarshipType

            all_scholarships_stmt = select(ScholarshipType)
            all_scholarships_result = await db.execute(all_scholarships_stmt)
            all_scholarships = all_scholarships_result.scalars().all()

            permission_list = []
            for idx, scholarship in enumerate(all_scholarships):
                permission_list.append(
                    {
                        "id": -(idx + 1),  # Negative ID to indicate virtual permission
                        "user_id": user_id,
                        "scholarship_id": scholarship.id,
                        "scholarship_name": scholarship.name,
                        "scholarship_name_en": scholarship.name_en,
                        "comment": "Super admin has automatic access to all scholarships",
                        "created_at": target_user.created_at.isoformat(),
                        "updated_at": target_user.updated_at.isoformat(),
                    }
                )

            return {
                "success": True,
                "message": f"Retrieved {len(permission_list)} scholarship permissions (super admin has access to all)",
                "data": permission_list,
            }

    # Build query for regular permissions
    stmt = select(AdminScholarship).options(
        selectinload(AdminScholarship.admin), selectinload(AdminScholarship.scholarship)
    )

    if user_id:
        stmt = stmt.where(AdminScholarship.admin_id == user_id)

    result = await db.execute(stmt)
    permissions = result.scalars().all()

    # Convert to response format
    permission_list = []
    for permission in permissions:
        permission_list.append(
            {
                "id": permission.id,
                "user_id": permission.admin_id,
                "scholarship_id": permission.scholarship_id,
                "scholarship_name": permission.scholarship.name,
                "scholarship_name_en": permission.scholarship.name_en,
                "comment": "",  # AdminScholarship doesn't have comment field
                "created_at": permission.assigned_at.isoformat(),
                "updated_at": permission.assigned_at.isoformat(),
            }
        )

    # If no user_id filter and current user is SUPER_ADMIN, also include virtual permissions for all scholarships
    if not user_id and current_user.is_super_admin():
        from app.models.scholarship import ScholarshipType

        all_scholarships_stmt = select(ScholarshipType)
        all_scholarships_result = await db.execute(all_scholarships_stmt)
        all_scholarships = all_scholarships_result.scalars().all()

        # Add virtual permissions for scholarships not already in the list
        existing_scholarship_ids = {perm["scholarship_id"] for perm in permission_list}

        for idx, scholarship in enumerate(all_scholarships):
            if scholarship.id not in existing_scholarship_ids:
                permission_list.append(
                    {
                        "id": -(idx + 1000),  # Negative ID to indicate virtual permission
                        "user_id": current_user.id,
                        "scholarship_id": scholarship.id,
                        "scholarship_name": scholarship.name,
                        "scholarship_name_en": scholarship.name_en,
                        "comment": "Super admin has automatic access to all scholarships",
                        "created_at": current_user.created_at.isoformat(),
                        "updated_at": current_user.updated_at.isoformat(),
                    }
                )

    return {
        "success": True,
        "message": f"Retrieved {len(permission_list)} scholarship permissions",
        "data": permission_list,
    }


@router.get("/scholarship-permissions/current-user")
async def get_current_user_scholarship_permissions(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Get current user's scholarship permissions"""

    # Only admin and college roles can have scholarship permissions
    if current_user.role not in [UserRole.admin, UserRole.college, UserRole.super_admin]:
        return {"success": True, "message": "User role does not require scholarship permissions", "data": []}

    # Super admin has access to all scholarships (no specific permissions needed)
    if current_user.is_super_admin():
        return {"success": True, "message": "Super admin has access to all scholarships", "data": []}

    # Get permissions for admin/college users
    stmt = (
        select(AdminScholarship)
        .options(selectinload(AdminScholarship.scholarship))
        .where(AdminScholarship.admin_id == current_user.id)
    )

    result = await db.execute(stmt)
    permissions = result.scalars().all()

    # Convert to response format
    permission_list = []
    for permission in permissions:
        permission_list.append(
            {
                "id": permission.id,
                "user_id": permission.admin_id,
                "scholarship_id": permission.scholarship_id,
                "scholarship_name": permission.scholarship.name,
                "scholarship_name_en": permission.scholarship.name_en,
                "comment": "",
                "created_at": permission.assigned_at.isoformat(),
                "updated_at": permission.assigned_at.isoformat(),
            }
        )

    return {
        "success": True,
        "message": f"Retrieved {len(permission_list)} scholarship permissions for current user",
        "data": permission_list,
    }


@router.post("/scholarship-permissions")
async def create_scholarship_permission(
    permission_data: Dict[str, Any], current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """Create new scholarship permission (admin can only assign scholarships they have permission for)"""

    user_id = permission_data.get("user_id")
    scholarship_id = permission_data.get("scholarship_id")
    comment = permission_data.get("comment", "")

    if not user_id or not scholarship_id:
        raise HTTPException(status_code=400, detail="user_id and scholarship_id are required")

    # Check if admin is trying to modify their own permissions (not allowed)
    if current_user.role == UserRole.admin and user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin users cannot modify their own permissions"
        )

    # Check if user exists
    user_stmt = select(User).where(User.id == user_id)
    user_result = await db.execute(user_stmt)
    user = user_result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check if scholarship exists
    scholarship_stmt = select(ScholarshipType).where(ScholarshipType.id == scholarship_id)
    scholarship_result = await db.execute(scholarship_stmt)
    scholarship = scholarship_result.scalar_one_or_none()

    if not scholarship:
        raise HTTPException(status_code=404, detail="Scholarship not found")

    # Check if current user has permission for this scholarship
    check_scholarship_permission(current_user, scholarship_id)

    # Check if permission already exists
    existing_stmt = select(AdminScholarship).where(
        AdminScholarship.admin_id == user_id, AdminScholarship.scholarship_id == scholarship_id
    )
    existing_result = await db.execute(existing_stmt)
    existing = existing_result.scalar_one_or_none()

    if existing:
        raise HTTPException(status_code=409, detail="Permission already exists")

    # Create new permission

    new_permission = AdminScholarship(admin_id=user_id, scholarship_id=scholarship_id)

    db.add(new_permission)
    await db.commit()
    await db.refresh(new_permission)

    return {
        "success": True,
        "message": "Scholarship permission created successfully",
        "data": {
            "id": new_permission.id,
            "user_id": new_permission.admin_id,
            "scholarship_id": new_permission.scholarship_id,
            "scholarship_name": scholarship.name,
            "scholarship_name_en": scholarship.name_en,
            "comment": comment,
            "created_at": new_permission.assigned_at.isoformat(),
            "updated_at": new_permission.assigned_at.isoformat(),
        },
    }


@router.put("/scholarship-permissions/{id}")
async def update_scholarship_permission(
    id: int,
    permission_data: Dict[str, Any],
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update scholarship permission (admin only)"""

    # Check if permission exists
    stmt = select(AdminScholarship).options(selectinload(AdminScholarship.scholarship)).where(AdminScholarship.id == id)
    result = await db.execute(stmt)
    permission = result.scalar_one_or_none()

    if not permission:
        raise HTTPException(status_code=404, detail="Permission not found")

    # Update fields (only comment is updatable in this model)
    # Note: AdminScholarship model doesn't have comment field, so we'll skip updates
    # In a real implementation, you might want to add a comment field to the model

    await db.commit()
    await db.refresh(permission)

    return {
        "success": True,
        "message": "Scholarship permission updated successfully",
        "data": {
            "id": permission.id,
            "user_id": permission.admin_id,
            "scholarship_id": permission.scholarship_id,
            "scholarship_name": permission.scholarship.name,
            "scholarship_name_en": permission.scholarship.name_en,
            "comment": "",
            "created_at": permission.assigned_at.isoformat(),
            "updated_at": permission.assigned_at.isoformat(),
        },
    }


@router.delete("/scholarship-permissions/{id}")
async def delete_scholarship_permission(
    id: int, current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """Delete scholarship permission (admin can only delete permissions for scholarships they manage, and cannot delete their own permissions)"""

    # Check if permission exists
    stmt = select(AdminScholarship).options(selectinload(AdminScholarship.scholarship)).where(AdminScholarship.id == id)
    result = await db.execute(stmt)
    permission = result.scalar_one_or_none()

    if not permission:
        raise HTTPException(status_code=404, detail="Permission not found")

    # Check if admin is trying to delete their own permissions (not allowed)
    if current_user.role == UserRole.admin and permission.admin_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin users cannot delete their own permissions"
        )

    # Check if current user has permission for this scholarship
    check_scholarship_permission(current_user, permission.scholarship_id)

    # Delete permission
    await db.delete(permission)
    await db.commit()

    return {"success": True, "message": "Scholarship permission deleted successfully", "data": None}
