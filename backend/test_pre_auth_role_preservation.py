"""
Test script to verify pre-authorized role preservation during Portal SSO login
"""
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.user import EmployeeStatus, User, UserRole, UserType
from app.services.portal_sso_service import PortalSSOService


async def test_pre_auth_role_preservation():
    """Test that pre-authorized roles are preserved during Portal SSO login"""

    # Create async engine
    engine = create_async_engine(settings.database_url, echo=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Step 1: Create a pre-authorized admin user
        pre_auth_user = User(
            nycu_id="test_admin_123",
            name="Pre-authorized Admin",
            email="test_admin_123@nycu.edu.tw",
            user_type=UserType.employee,
            status=EmployeeStatus.active,
            role=UserRole.admin,  # Pre-authorized as admin
            comment="Pre-authorized by super_admin",
        )
        session.add(pre_auth_user)
        await session.commit()
        await session.refresh(pre_auth_user)

        print(f"✅ Created pre-authorized user: {pre_auth_user.nycu_id}")
        print(f"   Role: {pre_auth_user.role.value}")
        print(f"   Comment: {pre_auth_user.comment}")

        # Step 2: Simulate Portal SSO login
        portal_sso_service = PortalSSOService(session)

        # Mock portal data (employee type would normally result in professor role)
        portal_data = {
            "txtID": "test_admin_123",
            "nycuID": "test_admin_123",
            "txtName": "Test Admin User",
            "mail": "test_admin_123@nycu.edu.tw",
            "dept": "資訊工程學系",
            "deptCode": "5743",
            "userType": "employee",  # This would normally trigger professor role
            "employeestatus": "在職",
        }

        # Call _find_or_create_user to simulate login
        updated_user = await portal_sso_service._find_or_create_user(
            nycu_id="test_admin_123",
            name=portal_data["txtName"],
            email=portal_data["mail"],
            dept_name=portal_data["dept"],
            dept_code=portal_data["deptCode"],
            user_type=UserType.employee,
            user_role=UserRole.professor,  # Portal would assign professor
            status="在職",
            raw_data=portal_data,
        )

        # Step 3: Verify role is preserved
        print(f"\n✅ User after login: {updated_user.nycu_id}")
        print(f"   Role: {updated_user.role.value}")
        print(f"   Name: {updated_user.name}")

        # Check if role was preserved
        if updated_user.role == UserRole.admin:
            print("\n✅ SUCCESS: Pre-authorized admin role was preserved!")
            return True
        else:
            print(f"\n❌ FAILED: Role was changed from admin to {updated_user.role.value}")
            return False

        # Cleanup
        await session.delete(pre_auth_user)
        await session.commit()


async def main():
    try:
        result = await test_pre_auth_role_preservation()
        if result:
            print("\n🎉 Test passed!")
        else:
            print("\n❌ Test failed!")
    except Exception as e:
        print(f"\n❌ Test error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
