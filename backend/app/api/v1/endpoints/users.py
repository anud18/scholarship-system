"""
User management API endpoints
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.functions import count

from app.core.security import get_current_user, require_admin
from app.db.deps import get_db
from app.models.user import EmployeeStatus, User, UserRole, UserType
from app.schemas.user import BulkScholarshipAssignRequest, BulkScholarshipAssignResponse, UserCreate, UserUpdate
from app.services.auth_service import AuthService

router = APIRouter()


def convert_user_to_dict(user: User) -> dict:
    """Convert User model to dictionary for Pydantic validation - handles None values from SSO workflow"""
    return {
        "id": user.id,
        "nycu_id": user.nycu_id,
        "name": user.name,  # May be None if SSO hasn't populated yet
        "email": user.email,  # May be None if SSO hasn't populated yet
        "user_type": user.user_type.value if user.user_type else None,
        "status": user.status.value if user.status else None,
        "dept_code": user.dept_code,
        "dept_name": user.dept_name,
        "college_code": user.college_code,
        "role": user.role.value if hasattr(user.role, "value") else str(user.role),
        "comment": user.comment,
        "created_at": user.created_at.isoformat(),
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


@router.get("/me")
async def get_my_profile(current_user: User = Depends(get_current_user)):
    """Get current user profile"""
    return {
        "success": True,
        "message": "User profile retrieved successfully",
        "data": convert_user_to_dict(current_user),
    }


@router.get("/student-info")
async def get_student_info(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Get student information including all semester data"""
    from app.services.application_service import get_student_data_from_user
    from app.services.student_service import StudentService

    if current_user.role != UserRole.student:
        raise HTTPException(status_code=403, detail="Only students can access student information")

    # Get student profile
    student = await get_student_data_from_user(current_user)

    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    # Get semester data for recent years (last 3 years)
    student_service = StudentService()
    semesters = []
    current_year = 113  # TODO: Get from system settings
    student_code = student.get("std_stdcode", "")

    if student_code:
        for year in range(current_year, current_year - 3, -1):
            for term in ["1", "2"]:
                try:
                    term_data = await student_service.get_student_term_info(student_code, str(year), term)
                    if term_data:
                        semesters.append({"academic_year": str(year), "term": term, **term_data})
                except Exception:
                    # Log but continue - some semesters may not exist
                    pass

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
            },
            "semesters": semesters,
        },
    }


@router.put("/me")
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
    include_permissions: bool = Query(False, description="Include scholarship permissions"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get all users with pagination (admin only)"""
    from app.models.scholarship import ScholarshipType
    from app.models.user import AdminScholarship

    # Base query
    stmt = select(User)

    # Apply role filters
    if roles:
        # Handle multiple roles (comma-separated)
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
    count_stmt = select(count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar()

    # Apply pagination and ordering
    offset = (page - 1) * size
    stmt = stmt.offset(offset).limit(size).order_by(desc(User.created_at))

    # Execute query
    result = await db.execute(stmt)
    users = result.scalars().all()

    # Convert to response format and optionally include permissions
    user_list = []
    for user in users:
        user_dict = convert_user_to_dict(user)

        # Include scholarship permissions if requested
        if include_permissions:
            # Get user's scholarship permissions
            perm_stmt = (
                select(ScholarshipType)
                .join(AdminScholarship, AdminScholarship.scholarship_id == ScholarshipType.id)
                .where(AdminScholarship.admin_id == user.id)
            )
            perm_result = await db.execute(perm_stmt)
            scholarships = perm_result.scalars().all()

            user_dict["scholarships"] = [{"id": s.id, "code": s.code, "name": s.name} for s in scholarships]
            user_dict["scholarship_count"] = len(scholarships)
        else:
            user_dict["scholarships"] = []
            user_dict["scholarship_count"] = 0

        user_list.append(user_dict)

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


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new user (admin only)"""
    auth_service = AuthService(db)

    # Check if user already exists (only check email if provided)
    if user_data.email:
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


@router.patch("/{user_id}/college")
async def update_user_college(
    user_id: int,
    college_code: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update user's college code (super admin only)"""
    # Only super admin can change college assignments
    if current_user.role != UserRole.super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admin can update college assignments",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.college_code = college_code
    await db.commit()
    await db.refresh(user)

    return {
        "success": True,
        "message": "College assignment updated successfully",
        "data": convert_user_to_dict(user),
    }


@router.post("/{user_id}/scholarships/bulk", response_model=BulkScholarshipAssignResponse)
async def bulk_assign_scholarships(
    user_id: int,
    request: BulkScholarshipAssignRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Bulk assign/remove scholarships to/from user (super admin only)"""
    from app.models.scholarship import ScholarshipType
    from app.models.user import AdminScholarship

    # Only super admin can manage scholarship permissions
    if current_user.role != UserRole.super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admin can manage scholarship permissions",
        )

    # Get user
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    assigned_count = 0
    removed_count = 0

    if request.operation == "set":
        # Remove all existing assignments
        delete_stmt = select(AdminScholarship).where(AdminScholarship.admin_id == user_id)
        delete_result = await db.execute(delete_stmt)
        existing_assignments = delete_result.scalars().all()

        for assignment in existing_assignments:
            await db.delete(assignment)
            removed_count += 1

        # Add new assignments
        for scholarship_id in request.scholarship_ids:
            # Verify scholarship exists
            scholarship = await db.get(ScholarshipType, scholarship_id)
            if not scholarship:
                raise HTTPException(status_code=404, detail=f"Scholarship {scholarship_id} not found")

            assignment = AdminScholarship(admin_id=user_id, scholarship_id=scholarship_id)
            db.add(assignment)
            assigned_count += 1

    elif request.operation == "add":
        # Add new assignments (skip duplicates)
        for scholarship_id in request.scholarship_ids:
            # Verify scholarship exists
            scholarship = await db.get(ScholarshipType, scholarship_id)
            if not scholarship:
                raise HTTPException(status_code=404, detail=f"Scholarship {scholarship_id} not found")

            # Check if already assigned
            check_stmt = select(AdminScholarship).where(
                AdminScholarship.admin_id == user_id, AdminScholarship.scholarship_id == scholarship_id
            )
            check_result = await db.execute(check_stmt)
            if not check_result.scalar_one_or_none():
                assignment = AdminScholarship(admin_id=user_id, scholarship_id=scholarship_id)
                db.add(assignment)
                assigned_count += 1

    else:
        raise HTTPException(status_code=400, detail="Invalid operation. Use 'set' or 'add'")

    await db.commit()

    # Get final scholarship list
    final_stmt = (
        select(ScholarshipType)
        .join(AdminScholarship, AdminScholarship.scholarship_id == ScholarshipType.id)
        .where(AdminScholarship.admin_id == user_id)
    )
    final_result = await db.execute(final_stmt)
    scholarships = final_result.scalars().all()

    return BulkScholarshipAssignResponse(
        user_id=user_id,
        assigned_count=assigned_count,
        removed_count=removed_count,
        total_scholarships=len(scholarships),
        scholarships=[{"id": s.id, "code": s.code, "name": s.name} for s in scholarships],
    )


@router.get("/stats/overview")
async def get_user_stats(current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Get user statistics (admin only)"""
    # Total users by role
    role_stats = {}
    for role in UserRole:
        stmt = select(count(User.id)).where(User.role == role)
        result = await db.execute(stmt)
        user_count = result.scalar()
        role_stats[role.value] = user_count

    # User type distribution
    user_type_stats = {}
    for user_type in UserType:
        stmt = select(count(User.id)).where(User.user_type == user_type)
        result = await db.execute(stmt)
        user_count = result.scalar()
        user_type_stats[user_type.value] = user_count

    # Status distribution
    status_stats = {}
    for employee_status in EmployeeStatus:
        stmt = select(count(User.id)).where(User.status == employee_status)
        result = await db.execute(stmt)
        user_count = result.scalar()
        status_stats[employee_status.value] = user_count

    # Recent registrations (last 30 days)
    from datetime import datetime, timedelta

    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    recent_stmt = select(count(User.id)).where(User.created_at >= thirty_days_ago)
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
