"""
Developer Profile Service for development environment
Allows developers to create and manage their own test user profiles
"""

from typing import Dict, List, Optional

from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import EmployeeStatus, User, UserRole, UserType
from app.services.auth_service import AuthService


class DeveloperProfile(BaseModel):
    """Developer profile configuration"""

    developer_id: str
    name: str
    chinese_name: Optional[str] = None
    english_name: Optional[str] = None
    role: UserRole
    email_domain: str = "dev.local"
    custom_attributes: Dict = {}


class DeveloperProfileService:
    """Service for managing developer profiles and test users"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.auth_service = AuthService(db)

    async def create_developer_user(
        self, developer_id: str, profile: DeveloperProfile
    ) -> User:
        """Create a test user for a specific developer"""
        nycu_id = f"dev_{developer_id}_{profile.role.value}"
        email = f"{nycu_id}@{profile.email_domain}"

        # Check if user already exists
        stmt = select(User).where(User.nycu_id == nycu_id)
        result = await self.db.execute(stmt)
        existing_user = result.scalar_one_or_none()

        if existing_user:
            # Update existing user
            existing_user.name = profile.name
            existing_user.chinese_name = profile.chinese_name
            existing_user.english_name = profile.english_name
            existing_user.role = profile.role
            await self.db.commit()
            await self.db.refresh(existing_user)
            return existing_user

        # Create new user
        user = User(
            nycu_id=nycu_id,
            name=profile.name,
            email=email,
            user_type=UserType.STUDENT
            if profile.role == UserRole.STUDENT
            else UserType.EMPLOYEE,
            status=EmployeeStatus.在學
            if profile.role == UserRole.STUDENT
            else EmployeeStatus.在職,
            dept_code="5802",  # Default department code
            dept_name="校務資訊組",  # Default department name
            role=profile.role,
            comment=f"Developer test user for {developer_id}",
            raw_data={
                "chinese_name": profile.chinese_name,
                "english_name": profile.english_name,
                "custom_attributes": profile.custom_attributes,
            },
        )

        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        return user

    async def get_developer_users(self, developer_id: str) -> List[User]:
        """Get all test users for a specific developer"""
        stmt = select(User).where(User.nycu_id.like(f"dev_{developer_id}_%"))
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def delete_developer_user(self, developer_id: str, role: UserRole) -> bool:
        """Delete a specific test user for a developer"""
        nycu_id = f"dev_{developer_id}_{role.value}"
        stmt = delete(User).where(User.nycu_id == nycu_id)
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount > 0

    async def delete_all_developer_users(self, developer_id: str) -> int:
        """Delete all test users for a developer"""
        stmt = delete(User).where(User.nycu_id.like(f"dev_{developer_id}_%"))
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount

    async def create_developer_test_suite(
        self, developer_id: str, profiles: List[DeveloperProfile]
    ) -> List[User]:
        """Create a complete test suite for a developer"""
        created_users = []

        for profile in profiles:
            user = await self.create_developer_user(developer_id, profile)
            created_users.append(user)

        return created_users

    async def get_all_developer_ids(self) -> List[str]:
        """Get list of all developer IDs that have test users"""
        stmt = select(User.nycu_id).where(User.nycu_id.like("dev_%"))
        result = await self.db.execute(stmt)
        nycu_ids = result.scalars().all()

        # Extract unique developer IDs
        developer_ids = set()
        for nycu_id in nycu_ids:
            if nycu_id.startswith("dev_"):
                parts = nycu_id.split("_", 2)
                if len(parts) >= 2:
                    developer_ids.add(parts[1])

        return list(developer_ids)

    def get_default_test_profiles(self, developer_id: str) -> List[DeveloperProfile]:
        """Get default test profiles for a developer"""
        return [
            DeveloperProfile(
                developer_id=developer_id,
                name=f"{developer_id.title()} Student",
                chinese_name=f"{developer_id}學生",
                english_name=f"{developer_id.title()} Student",
                role=UserRole.STUDENT,
                custom_attributes={"gpa": 3.5, "year": "sophomore"},
            ),
            DeveloperProfile(
                developer_id=developer_id,
                name=f"Prof. {developer_id.title()}",
                chinese_name=f"{developer_id}教授",
                english_name=f"Professor {developer_id.title()}",
                role=UserRole.PROFESSOR,
                custom_attributes={"department": "Computer Science"},
            ),
            DeveloperProfile(
                developer_id=developer_id,
                name=f"{developer_id.title()} Admin",
                chinese_name=f"{developer_id}管理員",
                english_name=f"{developer_id.title()} Administrator",
                role=UserRole.ADMIN,
                custom_attributes={"permissions": ["full_access"]},
            ),
        ]

    async def quick_setup_developer(self, developer_id: str) -> List[User]:
        """Quick setup for a developer with default profiles"""
        profiles = self.get_default_test_profiles(developer_id)
        return await self.create_developer_test_suite(developer_id, profiles)


# Helper class for developer profile management
class DeveloperProfileManager:
    """High-level interface for developer profile management"""

    @staticmethod
    def create_custom_profile(
        developer_id: str,
        role: UserRole,
        name: str,
        chinese_name: Optional[str] = None,
        english_name: Optional[str] = None,
        **custom_attributes,
    ) -> DeveloperProfile:
        """Create a custom developer profile"""
        return DeveloperProfile(
            developer_id=developer_id,
            name=name,
            chinese_name=chinese_name,
            english_name=english_name,
            role=role,
            custom_attributes=custom_attributes,
        )

    @staticmethod
    def create_student_profiles(developer_id: str) -> List[DeveloperProfile]:
        """Create various student profiles for testing"""
        return [
            DeveloperProfile(
                developer_id=developer_id,
                name=f"{developer_id.title()} Freshman",
                chinese_name=f"{developer_id}大一生",
                english_name=f"{developer_id.title()} Freshman",
                role=UserRole.STUDENT,
                custom_attributes={
                    "student_type": "undergraduate",
                    "year": "freshman",
                    "gpa": 3.2,
                },
            ),
            DeveloperProfile(
                developer_id=developer_id,
                name=f"{developer_id.title()} Graduate",
                chinese_name=f"{developer_id}研究生",
                english_name=f"{developer_id.title()} Graduate",
                role=UserRole.STUDENT,
                custom_attributes={
                    "student_type": "graduate",
                    "year": "master",
                    "gpa": 3.8,
                },
            ),
            DeveloperProfile(
                developer_id=developer_id,
                name=f"{developer_id.title()} PhD",
                chinese_name=f"{developer_id}博士生",
                english_name=f"{developer_id.title()} PhD Student",
                role=UserRole.STUDENT,
                custom_attributes={
                    "student_type": "graduate",
                    "year": "phd",
                    "gpa": 3.9,
                },
            ),
        ]

    @staticmethod
    def create_staff_profiles(developer_id: str) -> List[DeveloperProfile]:
        """Create various staff profiles for testing"""
        return [
            DeveloperProfile(
                developer_id=developer_id,
                name=f"Dr. {developer_id.title()}",
                chinese_name=f"{developer_id}博士",
                english_name=f"Dr. {developer_id.title()}",
                role=UserRole.PROFESSOR,
                custom_attributes={
                    "department": "Computer Science",
                    "title": "Assistant Professor",
                },
            ),
            DeveloperProfile(
                developer_id=developer_id,
                name=f"Prof. {developer_id.title()}",
                chinese_name=f"{developer_id}教授",
                english_name=f"Professor {developer_id.title()}",
                role=UserRole.PROFESSOR,
                custom_attributes={
                    "department": "Electrical Engineering",
                    "title": "Full Professor",
                },
            ),
            DeveloperProfile(
                developer_id=developer_id,
                name=f"{developer_id.title()} College Admin",
                chinese_name=f"{developer_id}學院管理員",
                english_name=f"{developer_id.title()} College Administrator",
                role=UserRole.COLLEGE,
                custom_attributes={
                    "department": "College of Engineering",
                    "permissions": ["college_review"],
                },
            ),
            DeveloperProfile(
                developer_id=developer_id,
                name=f"{developer_id.title()} System Admin",
                chinese_name=f"{developer_id}系統管理員",
                english_name=f"{developer_id.title()} System Administrator",
                role=UserRole.SUPER_ADMIN,
                custom_attributes={"permissions": ["full_access", "system_config"]},
            ),
        ]
