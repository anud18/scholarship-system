"""
Who wins the role at Portal SSO login.

Login asks SIS live on every login (no cache). This file pins how its answer combines with
the Portal ``userType`` and with roles an administrator set:

- an admin-set college / admin role and its ``college_code`` survive login, even when
  SIS reports the account as a student (e.g. a PhD student working as college staff)
- SIS has no record → the Portal ``userType`` decides (a just-enrolled student whose
  SIS record is not there yet still gets the student role)
- SIS unreachable → the same Portal fallback
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ServiceUnavailableError
from app.models.user import User, UserRole, UserType
from app.services.portal_sso_service import PortalSSOService

NYCU_ID = "314540001"
SIS_STUDENT = {"std_stdcode": NYCU_ID, "std_cname": "王小明", "std_depno": "4540", "std_depname": "電機系"}


def _portal_data(user_type: str) -> dict:
    return {
        "nycuID": NYCU_ID,
        "txtID": NYCU_ID,
        "txtName": "王小明",
        "mail": "wang@nycu.edu.tw",
        "userType": user_type,
        "dept": "電機學院",
        "deptCode": "E000",
        "employeestatus": "在學",
    }


async def _login(db: AsyncSession, monkeypatch, user_type: str, sis_answer) -> User:
    service = PortalSSOService(db)

    async def _verify(token: str) -> dict:
        return _portal_data(user_type)

    monkeypatch.setattr(service, "verify_portal_token", _verify)
    service.student_service = MagicMock(api_enabled=True)
    if isinstance(sis_answer, Exception):
        service.student_service.get_student_basic_info = AsyncMock(side_effect=sis_answer)
    else:
        service.student_service.get_student_basic_info = AsyncMock(return_value=sis_answer)

    await service.process_portal_login("portal-token")

    service.student_service.get_student_basic_info.assert_awaited_once_with(NYCU_ID, fresh=True, retry_empty=False)
    db.expire_all()
    return (await db.execute(select(User).where(User.nycu_id == NYCU_ID))).scalar_one()


@pytest.mark.asyncio
@pytest.mark.parametrize("admin_role", [UserRole.college, UserRole.admin])
async def test_admin_set_role_and_college_survive_a_sis_student_login(db: AsyncSession, monkeypatch, admin_role):
    db.add(
        User(
            nycu_id=NYCU_ID,
            name="王小明",
            email="wang@nycu.edu.tw",
            user_type=UserType.employee,
            role=admin_role,
            college_code="E",
        )
    )
    await db.commit()

    user = await _login(db, monkeypatch, user_type="student", sis_answer=dict(SIS_STUDENT))

    assert user.role == admin_role
    assert user.college_code == "E"


@pytest.mark.asyncio
async def test_new_student_missing_from_sis_falls_back_to_portal_user_type(db: AsyncSession, monkeypatch):
    user = await _login(db, monkeypatch, user_type="student", sis_answer=None)

    assert user.role == UserRole.student
    assert user.user_type == UserType.student


@pytest.mark.asyncio
async def test_sis_outage_falls_back_to_portal_user_type(db: AsyncSession, monkeypatch):
    user = await _login(
        db, monkeypatch, user_type="student", sis_answer=ServiceUnavailableError("Student API request timed out")
    )

    assert user.role == UserRole.student


@pytest.mark.asyncio
async def test_staff_missing_from_sis_gets_the_portal_employee_role(db: AsyncSession, monkeypatch):
    user = await _login(db, monkeypatch, user_type="employee", sis_answer=None)

    assert user.role == UserRole.professor
    assert user.user_type == UserType.employee
