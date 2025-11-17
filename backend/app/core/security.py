"""
Security utilities for authentication and authorization
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.db.deps import get_db
from app.models.user import User, UserRole

# JWT token bearer
security = HTTPBearer(auto_error=False)

# Note: Password functions removed since this system uses SSO authentication
# For testing purposes, you can add them back if needed, but they're not used in production


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt


def create_refresh_token(data: Dict[str, Any]) -> str:
    """Create JWT refresh token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
    to_encode.update({"exp": expire, "type": "refresh"})

    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt


def verify_token(token: str) -> Dict[str, Any]:
    """Verify and decode JWT token"""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Token has expired")
    except jwt.PyJWTError:
        raise AuthenticationError("Invalid token")


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get current authenticated user"""
    if credentials is None:
        raise AuthenticationError("Authorization header missing")

    try:
        payload = verify_token(credentials.credentials)
        user_id_str: str = payload.get("sub")
        if user_id_str is None:
            raise AuthenticationError("Invalid token")
        user_id = int(user_id_str)  # Convert string back to int
    except AuthenticationError:
        raise  # Re-raise authentication errors as-is
    except Exception:
        raise AuthenticationError("Could not validate credentials")

    # Get user from database with relationships that will be used in-request
    stmt = select(User).options(selectinload(User.admin_scholarships)).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        raise AuthenticationError("User not found")

    return user


def require_role(required_role: UserRole):
    """Role-based access control decorator"""

    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if not current_user.has_role(required_role):
            raise AuthorizationError(f"Access denied. Required role: {required_role.value}")
        return current_user

    return role_checker


def require_roles(*required_roles: UserRole):
    """Multiple roles access control decorator"""

    def roles_checker(current_user: User = Depends(get_current_user)) -> User:
        if not any(current_user.has_role(role) for role in required_roles):
            role_names = [role.value for role in required_roles]
            raise AuthorizationError(f"Access denied. Required roles: {', '.join(role_names)}")
        return current_user

    return roles_checker


def check_user_roles(required_roles: List[UserRole], current_user: User) -> None:
    """Check if user has any of the required roles - utility function for direct use"""
    if not any(current_user.has_role(role) for role in required_roles):
        role_names = [role.value for role in required_roles]
        raise AuthorizationError(f"Access denied. Required roles: {', '.join(role_names)}")


# Role-specific dependencies
def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require admin or super admin role"""
    if not (current_user.is_admin() or current_user.is_super_admin()):
        raise AuthorizationError("Admin access required")
    return current_user


def require_super_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require super admin role only"""
    if not current_user.is_super_admin():
        raise AuthorizationError("Super admin access required")
    return current_user


def require_scholarship_manager(current_user: User = Depends(get_current_user)) -> User:
    """Require admin, super admin, or college role for scholarship management"""
    if not (current_user.is_admin() or current_user.is_super_admin() or current_user.is_college()):
        raise AuthorizationError("Scholarship management access required")
    return current_user


def require_student(current_user: User = Depends(get_current_user)) -> User:
    """Require student role"""
    if not current_user.is_student():
        raise AuthorizationError("Student access required")
    return current_user


def require_professor(current_user: User = Depends(get_current_user)) -> User:
    """Require professor role"""
    if not current_user.is_professor():
        raise AuthorizationError("Professor access required")
    return current_user


def require_college(current_user: User = Depends(get_current_user)) -> User:
    """Require college role"""
    if not current_user.is_college():
        raise AuthorizationError("College access required")
    return current_user


def require_staff(current_user: User = Depends(get_current_user)) -> User:
    """Require staff access (admin, college, professor, or super_admin)"""
    if not any(
        [
            current_user.is_admin(),
            current_user.is_college(),
            current_user.is_professor(),
            current_user.is_super_admin(),
        ]
    ):
        raise AuthorizationError("Staff access required")
    return current_user


def require_scholarship_permission(scholarship_type_id: int):
    """Require permission to manage a specific scholarship"""

    def permission_checker(current_user: User = Depends(require_admin)) -> User:
        if not current_user.has_scholarship_permission(scholarship_type_id):
            raise AuthorizationError(f"Access denied. No permission to manage scholarship type {scholarship_type_id}")
        return current_user

    return permission_checker


def check_scholarship_permission(user: User, scholarship_type_id: int) -> None:
    """Check if user has permission for a scholarship type and raise exception if not"""
    if not user.has_scholarship_permission(scholarship_type_id):
        raise AuthorizationError(f"Access denied. No permission to manage scholarship type {scholarship_type_id}")


# College Review Permission Checks
async def check_college_scholarship_permission(user: User, scholarship_type_id: int, db: AsyncSession) -> bool:
    """Check if college user has permission for specific scholarship type"""
    if user.role in [UserRole.admin, UserRole.super_admin]:
        return True

    # Check if user is assigned to this scholarship type
    from app.models.user import AdminScholarship

    stmt = select(AdminScholarship).where(
        (AdminScholarship.admin_id == user.id) & (AdminScholarship.scholarship_id == scholarship_type_id)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


async def check_college_academic_year_permission(user: User, academic_year: int, db: AsyncSession) -> bool:
    """Check if user has permission for specific academic year"""
    if user.role in [UserRole.admin, UserRole.super_admin]:
        return True

    # College users can only access current and previous academic year
    current_year = datetime.now().year - 1911  # ROC year
    allowed_years = [current_year - 1, current_year, current_year + 1]
    return academic_year in allowed_years


async def check_college_application_review_permission(user: User, application_id: int, db: AsyncSession) -> bool:
    """Check if user can review specific application"""
    if user.role in [UserRole.admin, UserRole.super_admin]:
        return True

    # Get application details to check permissions
    from app.models.application import Application

    stmt = select(Application).where(Application.id == application_id)
    result = await db.execute(stmt)
    application = result.scalar_one_or_none()

    if not application:
        return False

    # Check scholarship type permission
    if application.scholarship_type_id:
        return await check_college_scholarship_permission(user, application.scholarship_type_id, db)

    # Check academic year permission
    if application.academic_year:
        return await check_college_academic_year_permission(user, application.academic_year, db)

    return True  # Default allow if no specific restrictions
