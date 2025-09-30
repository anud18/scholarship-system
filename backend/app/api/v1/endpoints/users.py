"""
User management API endpoints
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, require_admin
from app.db.deps import get_db
from app.models.user import EmployeeStatus, User, UserRole, UserType
from app.schemas.user import UserCreate, UserUpdate
from app.services.auth_service import AuthService

router = APIRouter()


def convert_user_to_dict(user: User) -> dict:
    """Convert User model to dictionary for Pydantic validation"""
    return {
        "id": user.id,
        "nycu_id": user.nycu_id,
        "name": user.name,
        "email": user.email,
        "user_type": user.user_type.value if user.user_type else None,
        "status": user.status.value if user.status else None,
        "dept_code": user.dept_code,
        "dept_name": user.dept_name,
        "role": user.role.value if hasattr(user.role, "value") else str(user.role),
        "comment": user.comment,
        "created_at": user.created_at.isoformat(),
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


@router.get("me")
async def get_my_profile(current_user: User = Depends(get_current_user)):
    """Get current user profile"""
    return {
        "success": True,
        "message": "User profile retrieved successfully",
        "data": convert_user_to_dict(current_user),
    }


@router.get("student-info")
async def get_student_info(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Get student information"""
    from app.services.application_service import get_student_data_from_user

    if current_user.role != UserRole.student:
        raise HTTPException(status_code=403, detail="Only students can access student information")

    # Get student profile
    student = await get_student_data_from_user(current_user)

    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    # Return student information with new structure
    return {
        "success": True,
        "message": "Student information retrieved successfully",
        "data": {
            "student": {
                "id": current_user.id,
                "std_stdno": student.get("std_stdno", ""),
                "std_stdcode": student.get("std_stdcode", ""),
                "std_pid": student.get("std_pid", ""),
                "std_cname": student.get("std_cname", ""),
                "std_ename": student.get("std_ename", ""),
                "std_degree": student.get("std_degree", ""),
                "std_studingstatus": student.get("std_studingstatus", ""),
                "std_sex": student.get("std_sex", ""),
                "std_enrollyear": student.get("std_enrollyear", ""),
                "std_enrollterm": student.get("std_enrollterm", ""),
                "std_termcount": student.get("std_termcount", ""),
                "std_nation": student.get("std_nation", ""),
                "std_schoolid": student.get("std_schoolid", ""),
                "std_identity": student.get("std_identity", ""),
                "std_depno": student.get("std_depno", ""),
                "std_depname": student.get("std_depname", ""),
                "std_aca_no": student.get("std_aca_no", ""),
                "std_aca_cname": student.get("std_aca_cname", ""),
                "std_highestschname": student.get("std_highestschname", ""),
                "com_cellphone": student.get("com_cellphone", ""),
                "com_email": student.get("com_email", ""),
                "com_commzip": student.get("com_commzip", ""),
                "com_commadd": student.get("com_commadd", ""),
                "std_enrolled_date": student.get("std_enrolled_date", ""),
                "std_bank_account": student.get("std_bank_account", ""),
                "notes": student.get("notes", ""),
            }
        },
    }


@router.put("me")
async def update_my_profile(
    update_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user profile"""
    # Update only fields defined in the Pydantic schema to prevent mass assignment
    # This automatically stays in sync with schema changes
    allowed_fields = set(update_data.model_fields.keys())

    update_dict = update_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        if field in allowed_fields and hasattr(current_user, field):
            setattr(current_user, field, value)

    await db.commit()
    await db.refresh(current_user)

    return {
        "success": True,
        "message": "Profile updated successfully",
        "data": convert_user_to_dict(current_user),
    }


# ==================== 管理員專用API ====================


@router.get("")
async def get_all_users(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
    role: Optional[str] = Query(None, description="Filter by role"),
    roles: Optional[str] = Query(None, description="Filter by multiple roles (comma-separated)"),
    search: Optional[str] = Query(None, description="Search by name, email, or nycu_id"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get all users with pagination (admin only)"""

    # Base query
    stmt = select(User)

    # Apply role filters
    if roles:
        # Handle multiple roles (comma-separated)
        # Convert to lowercase and handle both snake_case and SCREAMING_CASE
        role_list = [r.strip().lower() for r in roles.split(",") if r.strip()]
        try:
            user_roles = [UserRole(r) for r in role_list]
            stmt = stmt.where(User.role.in_(user_roles))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid role in roles parameter: {e}")
    elif role:
        # Handle single role (backward compatibility)
        try:
            user_role = UserRole(role.lower())
            stmt = stmt.where(User.role == user_role)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid role: {role}")

    if search:
        stmt = stmt.where(
            (User.name.icontains(search))
            | (User.email.icontains(search))
            | (User.nycu_id.icontains(search))
            | (User.dept_name.icontains(search))
        )

    # Remove is_active filter since we removed that field
    # All users are considered active in the new model

    # Get total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar()

    # Apply pagination and ordering
    offset = (page - 1) * size
    stmt = stmt.offset(offset).limit(size).order_by(desc(User.created_at))

    # Execute query
    result = await db.execute(stmt)
    users = result.scalars().all()

    # Convert to response format
    user_list = [convert_user_to_dict(user) for user in users]

    return {
        "success": True,
        "message": "Users retrieved successfully",
        "data": {
            "items": user_list,
            "total": total,
            "page": page,
            "size": size,
            "pages": (total + size - 1) // size,
        },
    }


@router.get("/{user_id}")
async def get_user_by_id(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get user by ID (admin only)"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "success": True,
        "message": "User retrieved successfully",
        "data": convert_user_to_dict(user),
    }


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new user (admin only)"""
    auth_service = AuthService(db)

    # Check if user already exists
    existing_user = await auth_service.get_user_by_email(user_data.email)
    if existing_user:
        raise HTTPException(status_code=409, detail="User with this email already exists")

    existing_nycu_id = await auth_service.get_user_by_nycu_id(user_data.nycu_id)
    if existing_nycu_id:
        raise HTTPException(status_code=409, detail="NYCU ID already taken")

    # Create user
    user = await auth_service.register_user(user_data)

    return {
        "success": True,
        "message": "User created successfully",
        "data": convert_user_to_dict(user),
    }


@router.put("/{user_id}")
async def update_user(
    user_id: int,
    update_data: UserUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update user (admin only)"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Update only fields defined in the Pydantic schema to prevent mass assignment
    # This automatically stays in sync with schema changes
    allowed_fields = set(update_data.model_fields.keys())

    update_dict = update_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        if field in allowed_fields and hasattr(user, field):
            setattr(user, field, value)

    await db.commit()
    await db.refresh(user)

    return {
        "success": True,
        "message": "User updated successfully",
        "data": convert_user_to_dict(user),
    }


@router.get("stats/overview")
async def get_user_stats(current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Get user statistics (admin only)"""
    # Total users by role
    role_stats = {}
    for role in UserRole:
        stmt = select(func.count(User.id)).where(User.role == role)
        result = await db.execute(stmt)
        count = result.scalar()
        role_stats[role.value] = count

    # User type distribution
    user_type_stats = {}
    for user_type in UserType:
        stmt = select(func.count(User.id)).where(User.user_type == user_type)
        result = await db.execute(stmt)
        count = result.scalar()
        user_type_stats[user_type.value] = count

    # Status distribution
    status_stats = {}
    for employee_status in EmployeeStatus:
        stmt = select(func.count(User.id)).where(User.status == employee_status)
        result = await db.execute(stmt)
        count = result.scalar()
        status_stats[employee_status.value] = count

    # Recent registrations (last 30 days)
    from datetime import datetime, timedelta

    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    recent_stmt = select(func.count(User.id)).where(User.created_at >= thirty_days_ago)
    recent_result = await db.execute(recent_stmt)
    recent_count = recent_result.scalar()

    return {
        "success": True,
        "message": "User statistics retrieved successfully",
        "data": {
            "total_users": sum(role_stats.values()),
            "role_distribution": role_stats,
            "user_type_distribution": user_type_stats,
            "status_distribution": status_stats,
            "recent_registrations": recent_count,
        },
    }
