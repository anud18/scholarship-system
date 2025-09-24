"""
Pre-authorization API endpoints for managing user permissions before first login
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.deps import get_db
from app.models.user import User, UserRole
from app.schemas.pre_authorization import (
    AdminScholarshipList,
    AssignScholarshipRequest,
    AssignScholarshipResponse,
    PreAuthorizedUserList,
    PreAuthorizeUserRequest,
    PreAuthorizeUserResponse,
)
from app.services.pre_authorization_service import PreAuthorizationService

router = APIRouter()


@router.post("/pre-authorize/user", response_model=PreAuthorizeUserResponse)
async def pre_authorize_user(
    request: PreAuthorizeUserRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Pre-authorize a user with nycu_id and role"""

    # Check permissions
    if not current_user.can_assign_roles():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to pre-authorize users",
        )

    try:
        pre_auth_service = PreAuthorizationService(db)
        user = await pre_auth_service.create_pre_authorized_user(
            nycu_id=request.nycu_id,
            role=UserRole(request.role),
            assigned_by=current_user.nycu_id,
            comment=request.comment,
        )

        return PreAuthorizeUserResponse(
            success=True,
            message=f"User {request.nycu_id} pre-authorized as {request.role}",
            data={
                "nycu_id": user.nycu_id,
                "role": user.role.value,
                "comment": user.comment,
            },
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/assign-scholarship", response_model=AssignScholarshipResponse)
async def assign_scholarship_to_admin(
    request: AssignScholarshipRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Assign a scholarship to an admin"""

    # Check permissions
    if not current_user.can_assign_roles():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to assign scholarships",
        )

    try:
        pre_auth_service = PreAuthorizationService(db)
        assignment = await pre_auth_service.assign_admin_to_scholarship(
            admin_nycu_id=request.admin_nycu_id,
            scholarship_id=request.scholarship_id,
            assigned_by=current_user.nycu_id,
            comment=request.comment,
        )

        return AssignScholarshipResponse(
            success=True,
            message=f"Scholarship {request.scholarship_id} assigned to admin {request.admin_nycu_id}",
            data={
                "admin_nycu_id": request.admin_nycu_id,
                "scholarship_id": assignment.scholarship_id,
                "assigned_at": assignment.assigned_at.isoformat(),
            },
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/pre-authorized-users", response_model=PreAuthorizedUserList)
async def get_pre_authorized_users(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """Get all pre-authorized users"""

    # Check permissions
    if not current_user.can_assign_roles():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to view pre-authorized users",
        )

    pre_auth_service = PreAuthorizationService(db)
    users = await pre_auth_service.get_pre_authorized_users()

    user_list = []
    for user in users:
        user_list.append(
            {
                "nycu_id": user.nycu_id,
                "name": user.name,
                "email": user.email,
                "role": user.role.value,
                "created_at": user.created_at.isoformat(),
                "comment": user.comment,
            }
        )

    return PreAuthorizedUserList(
        success=True,
        message=f"Found {len(user_list)} pre-authorized users",
        data=user_list,
    )


@router.get("/admin-scholarships/{admin_nycu_id}", response_model=AdminScholarshipList)
async def get_admin_scholarships(
    admin_nycu_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all scholarship assignments for an admin"""

    # Check permissions - admin can only view their own assignments
    if not current_user.can_assign_roles() and current_user.nycu_id != admin_nycu_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to view admin scholarships",
        )

    pre_auth_service = PreAuthorizationService(db)
    assignments = await pre_auth_service.get_admin_scholarships(admin_nycu_id)

    assignment_list = []
    for assignment in assignments:
        assignment_list.append(
            {
                "admin_nycu_id": admin_nycu_id,
                "scholarship_id": assignment.scholarship_id,
                "assigned_at": assignment.assigned_at.isoformat(),
            }
        )

    return AdminScholarshipList(
        success=True,
        message=f"Found {len(assignment_list)} scholarship assignments for {admin_nycu_id}",
        data=assignment_list,
    )


@router.delete("/admin-scholarships/{admin_nycu_id}/{scholarship_id}")
async def remove_admin_from_scholarship(
    admin_nycu_id: str,
    scholarship_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove admin from scholarship assignment"""

    # Check permissions
    if not current_user.can_assign_roles():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to remove scholarship assignments",
        )

    try:
        pre_auth_service = PreAuthorizationService(db)
        success = await pre_auth_service.remove_admin_from_scholarship(
            admin_nycu_id=admin_nycu_id,
            scholarship_id=scholarship_id,
            removed_by=current_user.nycu_id,
        )

        return {
            "success": True,
            "message": f"Removed admin {admin_nycu_id} from scholarship {scholarship_id}",
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/user/{nycu_id}")
async def get_user_by_nycu_id(
    nycu_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user by nycu_id"""

    # Check permissions - users can only view their own info unless they have admin rights
    if not current_user.can_assign_roles() and current_user.nycu_id != nycu_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to view user information",
        )

    pre_auth_service = PreAuthorizationService(db)
    user = await pre_auth_service.get_user_by_nycu_id(nycu_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with nycu_id {nycu_id} not found",
        )

    return {
        "success": True,
        "message": "User found",
        "data": {
            "nycu_id": user.nycu_id,
            "name": user.name,
            "email": user.email,
            "role": user.role.value,
            "user_type": user.user_type.value if user.user_type else None,
            "status": user.status.value if user.status else None,
            "dept_code": user.dept_code,
            "dept_name": user.dept_name,
            "last_login_at": user.last_login_at.isoformat()
            if user.last_login_at
            else None,
            "comment": user.comment,
        },
    }
