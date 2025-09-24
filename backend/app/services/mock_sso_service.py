"""
Mock SSO service for development environment
Uses test data from init_db instead of predefined users
"""

import time
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole
from app.services.auth_service import AuthService


class MockSSOService:
    """Mock SSO service for development - Uses init_db test data"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.auth_service = AuthService(db)

    async def get_mock_users(self) -> List[Dict]:
        """Get list of available users from database for development login"""
        stmt = select(User).order_by(User.role, User.nycu_id)
        result = await self.db.execute(stmt)
        db_users = result.scalars().all()

        user_list = []
        for user in db_users:
            # Generate role-based description
            if user.is_student():
                description = f"Student ({user.nycu_id}) - {user.name}"
            elif user.is_professor():
                description = f"Professor - {user.name}"
            elif user.is_college():
                description = f"College Reviewer - {user.name}"
            elif user.is_admin():
                description = f"Administrator - {user.name}"
            elif user.is_super_admin():
                description = f"Super Administrator - {user.name}"
            else:
                description = f"{user.role.value.title()} - {user.name}"

            user_list.append(
                {
                    "id": str(user.id),
                    "nycu_id": user.nycu_id,
                    "username": user.nycu_id,  # 向後相容性
                    "email": user.email,
                    "name": user.name,
                    "full_name": user.name,  # 向後相容性
                    "role": user.role.value,
                    "user_type": user.user_type.value if user.user_type else "student",
                    "status": user.status.value if user.status else "在學",
                    "dept_code": user.dept_code,
                    "dept_name": user.dept_name,
                    "comment": user.comment,
                    "raw_data": user.raw_data,
                    "description": description,
                    "created_at": user.created_at.isoformat() if user.created_at else None,
                    "updated_at": user.updated_at.isoformat() if user.updated_at else None,
                }
            )

        return user_list

    async def get_portal_sso_data(self, username: str) -> Dict:
        """Get user data in real portal SSO format"""
        user = await self.authenticate_mock_user(username)

        # Map user data to portal format
        portal_data = {
            "iat": int(time.time()),
            "txtID": user.nycu_id,
            "nycuID": user.nycu_id,
            "txtName": user.name,
            "idno": "A123456789",  # Default ID number
            "mail": user.email,
            "dept": user.dept_name or "校務資訊組",
            "deptCode": user.dept_code or "5802",
            "userType": self._map_role_to_user_type(user.role),
            "oldEmpNo": user.nycu_id,
            "employeestatus": user.status.value if user.status else "在職",
        }

        return portal_data

    def _map_role_to_user_type(self, role: UserRole) -> str:
        """Map internal role to portal userType"""
        role_mapping = {
            UserRole.STUDENT: "student",
            UserRole.PROFESSOR: "employee",
            UserRole.COLLEGE: "employee",
            UserRole.ADMIN: "employee",
            UserRole.SUPER_ADMIN: "employee",
        }
        return role_mapping.get(role, "employee")

    async def authenticate_mock_user(self, username: str) -> User:
        """Authenticate and return user from database"""
        stmt = select(User).where(User.nycu_id == username)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise ValueError(f"User {username} not found")

        return user

    async def mock_sso_login(self, username: str):
        """Simulate SSO login for user"""
        user = await self.authenticate_mock_user(username)
        return await self.auth_service.create_tokens(user)
