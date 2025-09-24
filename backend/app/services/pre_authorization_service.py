"""
Pre-authorization service for managing user permissions before first login
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.scholarship import Scholarship
from app.models.user import AdminScholarship, EmployeeStatus, User, UserRole, UserType


class PreAuthorizationService:
    """Service for managing pre-authorization of users"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_pre_authorized_user(
        self,
        nycu_id: str,
        role: UserRole,
        assigned_by: str,
        comment: Optional[str] = None,
    ) -> User:
        """Create a pre-authorized user with nycu_id and role"""

        # Check if user already exists
        existing_user = await self.get_user_by_nycu_id(nycu_id)
        if existing_user:
            raise ValidationError(f"User with nycu_id {nycu_id} already exists")

        # Validate role assignment permissions
        if not await self._can_assign_role(assigned_by, role):
            raise ValidationError(f"User {assigned_by} cannot assign role {role.value}")

        # Create pre-authorized user
        user = User(
            nycu_id=nycu_id,
            name=f"Pre-authorized {role.value.title()}",  # Placeholder name
            email=f"{nycu_id}@nycu.edu.tw",  # Placeholder email
            user_type=UserType.EMPLOYEE if role != UserRole.STUDENT else UserType.STUDENT,
            status=EmployeeStatus.ACTIVE,
            role=role,
            comment=comment or f"Pre-authorized by {assigned_by}",
        )

        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        return user

    async def assign_admin_to_scholarship(
        self,
        admin_nycu_id: str,
        scholarship_id: int,
        assigned_by: str,
        comment: Optional[str] = None,
    ) -> AdminScholarship:
        """Assign an admin to manage a specific scholarship"""

        # Check if admin exists (pre-authorized or regular)
        admin = await self.get_user_by_nycu_id(admin_nycu_id)
        if not admin:
            raise NotFoundError(f"Admin with nycu_id {admin_nycu_id} not found")

        # Check if scholarship exists
        scholarship = await self._get_scholarship(scholarship_id)
        if not scholarship:
            raise NotFoundError(f"Scholarship with id {scholarship_id} not found")

        # Validate assignment permissions
        if not await self._can_assign_scholarship(assigned_by, admin):
            raise ValidationError(f"User {assigned_by} cannot assign scholarship to {admin_nycu_id}")

        # Check if assignment already exists
        existing = await self._get_admin_scholarship(admin.id, scholarship_id)
        if existing:
            raise ValidationError(f"Admin {admin_nycu_id} is already assigned to scholarship {scholarship_id}")

        # Create assignment
        assignment = AdminScholarship(admin_id=admin.id, scholarship_id=scholarship_id)

        self.db.add(assignment)
        await self.db.commit()
        await self.db.refresh(assignment)

        return assignment

    async def get_pre_authorized_users(self) -> List[User]:
        """Get all pre-authorized users (users with comment indicating pre-authorization)"""
        stmt = select(User).where(User.comment.like("%Pre-authorized%"))
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_user_by_nycu_id(self, nycu_id: str) -> Optional[User]:
        """Get user by nycu_id"""
        stmt = select(User).where(User.nycu_id == nycu_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_user_from_portal(self, nycu_id: str, portal_data: Dict) -> User:
        """Update user data when they first login from portal"""

        user = await self.get_user_by_nycu_id(nycu_id)
        if not user:
            # Create new user from portal data
            user = await self._create_user_from_portal(nycu_id, portal_data)
        else:
            # Update existing user (especially pre-authorized ones)
            user = await self._update_user_from_portal(user, portal_data)

        return user

    async def _create_user_from_portal(self, nycu_id: str, portal_data: Dict) -> User:
        """Create new user from portal data"""

        # Determine default role based on userType
        default_role = self._get_default_role_from_portal(portal_data)

        user = User(
            nycu_id=nycu_id,
            name=portal_data.get("txtName", ""),
            email=portal_data.get("mail", ""),
            user_type=self._map_user_type(portal_data.get("userType")),
            status=self._map_employee_status(portal_data.get("employeestatus")),
            dept_code=portal_data.get("deptCode"),
            dept_name=portal_data.get("dept"),
            role=default_role,
            raw_data=portal_data,
        )

        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        return user

    async def _update_user_from_portal(self, user: User, portal_data: Dict) -> User:
        """Update existing user with portal data"""

        # Update basic info
        user.name = portal_data.get("txtName", user.name)
        user.email = portal_data.get("mail", user.email)
        user.user_type = self._map_user_type(portal_data.get("userType"))
        user.status = self._map_employee_status(portal_data.get("employeestatus"))
        user.dept_code = portal_data.get("deptCode")
        user.dept_name = portal_data.get("dept")
        user.raw_data = portal_data
        user.last_login_at = datetime.now(timezone.utc)

        # If this was a pre-authorized user, update comment
        if user.comment and "Pre-authorized" in user.comment:
            user.comment = f"Activated from portal on {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"

        await self.db.commit()
        await self.db.refresh(user)

        return user

    def _get_default_role_from_portal(self, portal_data: Dict) -> UserRole:
        """Get default role based on portal userType"""
        user_type = portal_data.get("userType")

        if user_type == "student":
            return UserRole.STUDENT
        else:
            # All employees default to professor
            return UserRole.PROFESSOR

    def _map_user_type(self, portal_user_type: Optional[str]) -> UserType:
        """Map portal userType to internal UserType enum"""
        if portal_user_type == "student":
            return UserType.STUDENT
        elif portal_user_type == "employee":
            return UserType.EMPLOYEE
        return UserType.EMPLOYEE  # Default to employee

    def _map_employee_status(self, portal_status: Optional[str]) -> EmployeeStatus:
        """Map portal employeestatus to internal EmployeeStatus enum"""
        if portal_status == "在職":
            return EmployeeStatus.ACTIVE
        elif portal_status == "退休":
            return EmployeeStatus.RETIRED
        elif portal_status == "在學":
            return EmployeeStatus.STUDENT
        elif portal_status == "畢業":
            return EmployeeStatus.GRADUATED
        return EmployeeStatus.ACTIVE  # Default to active

    async def _can_assign_role(self, assigned_by: str, role: UserRole) -> bool:
        """Check if user can assign the specified role"""
        assigner = await self.get_user_by_nycu_id(assigned_by)
        if not assigner:
            return False

        # Super admin can assign any role
        if assigner.is_super_admin():
            return True

        # Admin can assign college and professor roles
        if assigner.role == UserRole.ADMIN:
            return role in [UserRole.COLLEGE, UserRole.PROFESSOR]

        return False

    async def _can_assign_scholarship(self, assigned_by: str, admin: User) -> bool:
        """Check if user can assign scholarship to admin"""
        assigner = await self.get_user_by_nycu_id(assigned_by)
        if not assigner:
            return False

        # Super admin can assign to any admin
        if assigner.is_super_admin():
            return admin.role in [UserRole.ADMIN, UserRole.COLLEGE]

        # Admin can assign to college users
        if assigner.role == UserRole.ADMIN:
            return admin.role == UserRole.COLLEGE

        return False

    async def _get_scholarship(self, scholarship_id: int) -> Optional[Scholarship]:
        """Get scholarship by ID"""
        stmt = select(Scholarship).where(Scholarship.id == scholarship_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_admin_scholarship(self, admin_id: int, scholarship_id: int) -> Optional[AdminScholarship]:
        """Get admin scholarship assignment"""
        stmt = select(AdminScholarship).where(
            and_(
                AdminScholarship.admin_id == admin_id,
                AdminScholarship.scholarship_id == scholarship_id,
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_admin_scholarships(self, admin_nycu_id: str) -> List[AdminScholarship]:
        """Get all scholarship assignments for an admin"""
        admin = await self.get_user_by_nycu_id(admin_nycu_id)
        if not admin:
            return []

        stmt = select(AdminScholarship).where(AdminScholarship.admin_id == admin.id)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def remove_admin_from_scholarship(self, admin_nycu_id: str, scholarship_id: int, removed_by: str) -> bool:
        """Remove admin from scholarship assignment"""

        admin = await self.get_user_by_nycu_id(admin_nycu_id)
        if not admin:
            raise NotFoundError(f"Admin with nycu_id {admin_nycu_id} not found")

        assignment = await self._get_admin_scholarship(admin.id, scholarship_id)
        if not assignment:
            raise NotFoundError(f"Assignment not found for admin {admin_nycu_id} and scholarship {scholarship_id}")

        # Check permissions
        assigner = await self.get_user_by_nycu_id(removed_by)
        if not assigner or not assigner.can_assign_roles():
            raise ValidationError(f"User {removed_by} cannot remove scholarship assignments")

        await self.db.delete(assignment)
        await self.db.commit()

        return True
