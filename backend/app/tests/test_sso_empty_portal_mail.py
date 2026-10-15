"""
Accounts whose NYCU Portal record has no email (`mail: ""`).

Production incident: a staff account first logged in with an empty Portal mail.
The empty string was stored as `users.email = ''`, and EmailStr rejects it, so

  - the user's own SSO login failed (`UserResponse.model_validate` -> HTTP 400), and
  - the admin 權限管理 form could not save a role for them (it PUTs the stored
    email back -> HTTP 422).

Covered here:
- request schemas read a blank email as "no email" (and an update treats it as
  "unchanged"), still reject a malformed one, and the response schema never
  re-validates a stored address
- `normalize_portal_email` turns anything unusable from the Portal payload into None
- SSO login and pre-authorization store NULL for it, heal an `''` left by older
  logins, and keep the stored address when Portal sends none
"""

from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole, UserType
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.services.portal_sso_service import PortalSSOService
from app.services.pre_authorization_service import PreAuthorizationService
from app.utils.portal_email import normalize_portal_email

# ─── schemas ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("blank", ["", "   "])
def test_user_update_ignores_a_blank_email(blank):
    """The edit form echoes the stored (empty) address back; that must neither 422
    nor wipe an address, so the field counts as not supplied."""
    update = UserUpdate(email=blank, role=UserRole.college)

    assert update.email is None
    assert update.model_dump(exclude_unset=True) == {"role": UserRole.college}


@pytest.mark.parametrize("blank", ["", "   "])
def test_user_create_reads_blank_email_as_none(blank):
    assert UserCreate(nycu_id="ED0891", email=blank).email is None


@pytest.mark.parametrize("stored", ["", "wang@portal.local"])
def test_user_response_never_revalidates_a_stored_email(stored):
    """Login serializes whatever is stored; a rejected address must not block it."""
    row = User(id=1, nycu_id="ED0891", name="王雍豪", email=stored, role=UserRole.professor)
    row.created_at = row.updated_at = datetime.now(timezone.utc)

    assert UserResponse.model_validate(row).email == stored


@pytest.mark.parametrize("schema", [UserUpdate, UserCreate])
def test_malformed_email_is_still_rejected(schema):
    kwargs: dict[str, Any] = {"nycu_id": "ED0891"} if schema is UserCreate else {}
    with pytest.raises(ValidationError):
        schema(email="not-an-email", **kwargs)


def test_user_update_keeps_a_valid_email():
    assert UserUpdate(email="wang@nycu.edu.tw").model_dump(exclude_unset=True) == {"email": "wang@nycu.edu.tw"}


# ─── normalize_portal_email ──────────────────────────────────────────


@pytest.mark.parametrize("raw", ["", "   ", None, "not-an-email", "a@b@c", ["a@nycu.edu.tw"], 123])
def test_unusable_portal_mail_becomes_none(raw):
    assert normalize_portal_email(raw) is None


def test_valid_portal_mail_is_returned_stripped():
    assert normalize_portal_email("  wang@nycu.edu.tw ") == "wang@nycu.edu.tw"


# ─── SSO login ───────────────────────────────────────────────────────


def _portal_data(mail: Any) -> dict:
    return {
        "nycuID": "ED0891",
        "txtID": "ED0891",
        "txtName": "王雍豪",
        "mail": mail,
        "userType": "employee",
        "dept": "藥學院",
        "deptCode": "A210",
        "employeestatus": "在職",
    }


@pytest.fixture
def sso_login(db: AsyncSession, monkeypatch):
    """Run the real process_portal_login with the Portal and SIS calls stubbed."""

    async def _login(mail: Any) -> dict:
        service = PortalSSOService(db)

        async def _verify(token: str) -> dict:
            return _portal_data(mail)

        async def _not_a_student(nycu_id: str) -> tuple[bool, None]:
            return False, None

        monkeypatch.setattr(service, "verify_portal_token", _verify)
        monkeypatch.setattr(service, "_verify_student_status", _not_a_student)
        return await service.process_portal_login("portal-token")

    return _login


async def _stored_user(db: AsyncSession) -> User:
    db.expire_all()
    return (await db.execute(select(User).where(User.nycu_id == "ED0891"))).scalar_one()


@pytest.mark.asyncio
@pytest.mark.parametrize("mail", ["", "  ", None, "not-an-email", ["wang@nycu.edu.tw"]])
async def test_first_login_with_unusable_portal_mail_succeeds_and_stores_null(db: AsyncSession, sso_login, mail):
    result = await sso_login(mail)

    assert result["access_token"]
    assert result["user"]["email"] is None
    assert (await _stored_user(db)).email is None


@pytest.mark.asyncio
async def test_login_heals_an_empty_string_email_left_by_an_older_login(db: AsyncSession, sso_login):
    db.add(User(nycu_id="ED0891", name="王雍豪", email="", user_type=UserType.employee, role=UserRole.professor))
    await db.commit()

    result = await sso_login("")

    assert result["access_token"]
    assert (await _stored_user(db)).email is None


@pytest.mark.asyncio
async def test_empty_portal_mail_keeps_the_stored_email(db: AsyncSession, sso_login):
    db.add(
        User(
            nycu_id="ED0891",
            name="王雍豪",
            email="wang@nycu.edu.tw",
            user_type=UserType.employee,
            role=UserRole.college,
        )
    )
    await db.commit()

    await sso_login("")

    stored = await _stored_user(db)
    assert stored.email == "wang@nycu.edu.tw"
    assert stored.role == UserRole.college


@pytest.mark.asyncio
async def test_portal_mail_still_updates_the_stored_email(db: AsyncSession, sso_login):
    db.add(User(nycu_id="ED0891", name="王雍豪", email="old@nycu.edu.tw", user_type=UserType.employee))
    await db.commit()

    await sso_login("new@nycu.edu.tw")

    assert (await _stored_user(db)).email == "new@nycu.edu.tw"


# ─── pre-authorization (second Portal -> User writer) ────────────────


@pytest.mark.asyncio
async def test_pre_authorization_creates_a_user_with_null_email_for_empty_portal_mail(db: AsyncSession):
    user = await PreAuthorizationService(db).update_user_from_portal("ED0891", _portal_data(""))

    assert user.email is None


@pytest.mark.asyncio
async def test_pre_authorization_keeps_the_placeholder_when_portal_mail_is_empty(db: AsyncSession):
    db.add(User(nycu_id="ED0891", name="王雍豪", email="ED0891@nycu.edu.tw", role=UserRole.college))
    await db.commit()

    user = await PreAuthorizationService(db).update_user_from_portal("ED0891", _portal_data(""))

    assert user.email == "ED0891@nycu.edu.tw"
