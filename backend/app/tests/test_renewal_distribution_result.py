"""Tests for the admin renewal distribution result endpoint.

Covers:
- GET /api/v1/renewals/distribution-result?scholarship_type_id=X&academic_year=Y

The endpoint groups approved renewals by (sub_type, renewal_year), separates
rejected renewals into their own list, and marks renewals whose sub_type was
challenged by a downstream challenge application (Application_C pointing back
via `challenges_application_id`).

Auth is mocked via `app.dependency_overrides[get_current_admin_user]` so tests
don't need real JWT tokens.
"""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_admin_user
from app.main import app
from app.models.application import Application
from app.models.enums import ApplicationStatus, SubTypeSelectionMode
from app.models.scholarship import ScholarshipType
from app.models.user import User, UserRole, UserType

CURRENT_ACADEMIC_YEAR = 114
PRIOR_ACADEMIC_YEAR = 113


# --------------------------------------------------------------------------- #
# Helpers / Fixtures
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def admin_user(db: AsyncSession) -> User:
    """Create an admin user for endpoint authorization."""
    user = User(
        nycu_id="admin_dist",
        name="Distribution Admin",
        email="dist_admin@university.edu",
        user_type=UserType.employee,
        role=UserRole.admin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_client(client: AsyncClient, admin_user: User):
    """Yield a client whose `get_current_admin_user` always returns admin_user."""

    async def override_admin():
        return admin_user

    app.dependency_overrides[get_current_admin_user] = override_admin
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_current_admin_user, None)


async def _make_student(db: AsyncSession, *, nycu_id: str, name: str) -> User:
    user = User(
        nycu_id=nycu_id,
        name=name,
        email=f"{nycu_id}@university.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _make_renewal_app(
    db: AsyncSession,
    *,
    user: User,
    scholarship_type: ScholarshipType,
    sub_type: str,
    renewal_year: int,
    status: ApplicationStatus = ApplicationStatus.approved,
    previous_application_id: int | None = None,
    app_id_suffix: str = "00001",
    academic_year: int = CURRENT_ACADEMIC_YEAR,
) -> Application:
    """Insert an `is_renewal=True` Application."""
    app_row = Application(
        app_id=f"APP-{academic_year}-0-{app_id_suffix}",
        user_id=user.id,
        scholarship_type_id=scholarship_type.id,
        scholarship_subtype_list=[sub_type],
        sub_type_selection_mode=SubTypeSelectionMode.single,
        sub_scholarship_type=sub_type,
        academic_year=academic_year,
        semester=None,
        status=status,
        is_renewal=True,
        renewal_year=renewal_year,
        previous_application_id=previous_application_id,
        agree_terms=True,
    )
    db.add(app_row)
    await db.commit()
    await db.refresh(app_row)
    return app_row


async def _make_challenge_app(
    db: AsyncSession,
    *,
    user: User,
    scholarship_type: ScholarshipType,
    target_sub_type: str,
    challenges_application_id: int,
    app_id_suffix: str = "90001",
    academic_year: int = CURRENT_ACADEMIC_YEAR,
) -> Application:
    """Insert an `is_renewal=False` challenge application pointing at a renewal."""
    app_row = Application(
        app_id=f"APP-{academic_year}-0-{app_id_suffix}",
        user_id=user.id,
        scholarship_type_id=scholarship_type.id,
        scholarship_subtype_list=[target_sub_type],
        sub_type_selection_mode=SubTypeSelectionMode.single,
        sub_scholarship_type=target_sub_type,
        academic_year=academic_year,
        semester=None,
        status=ApplicationStatus.under_review,
        is_renewal=False,
        challenges_application_id=challenges_application_id,
        agree_terms=True,
    )
    db.add(app_row)
    await db.commit()
    await db.refresh(app_row)
    return app_row


@pytest.fixture(autouse=True)
def freeze_current_academic_year(monkeypatch):
    """Pin academic year to 114 so the endpoint's year filter is deterministic."""
    from app.utils import academic_period

    def _fake_current_period():
        return {"academic_year": CURRENT_ACADEMIC_YEAR, "semester": "first", "western_year": 2025}

    monkeypatch.setattr(academic_period, "get_current_academic_period", _fake_current_period)


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_groups_by_sub_type_and_renewal_year(
    db: AsyncSession,
    admin_client: AsyncClient,
    test_scholarship: ScholarshipType,
):
    """Different (sub_type, renewal_year) combinations should produce separate groups."""
    s1 = await _make_student(db, nycu_id="stu_a", name="Student A")
    s2 = await _make_student(db, nycu_id="stu_b", name="Student B")
    s3 = await _make_student(db, nycu_id="stu_c", name="Student C")

    # Group 1: nstc / 113
    await _make_renewal_app(
        db,
        user=s1,
        scholarship_type=test_scholarship,
        sub_type="nstc",
        renewal_year=PRIOR_ACADEMIC_YEAR,
        app_id_suffix="10001",
    )
    # Group 2: nstc / 114 (different renewal_year, same sub_type)
    await _make_renewal_app(
        db,
        user=s2,
        scholarship_type=test_scholarship,
        sub_type="nstc",
        renewal_year=CURRENT_ACADEMIC_YEAR,
        app_id_suffix="10002",
    )
    # Group 3: moe_1w / 113 (different sub_type)
    await _make_renewal_app(
        db,
        user=s3,
        scholarship_type=test_scholarship,
        sub_type="moe_1w",
        renewal_year=PRIOR_ACADEMIC_YEAR,
        app_id_suffix="10003",
    )

    resp = await admin_client.get(
        "/api/v1/renewals/distribution-result",
        params={
            "scholarship_type_id": test_scholarship.id,
            "academic_year": CURRENT_ACADEMIC_YEAR,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    data = body["data"]

    groups = data["groups"]
    assert len(groups) == 3, f"expected 3 groups, got {len(groups)}: {groups}"

    # Build lookup by (sub_type, renewal_year) to assert membership cleanly.
    by_key = {(g["sub_type"], g["renewal_year"]): g for g in groups}
    assert ("nstc", PRIOR_ACADEMIC_YEAR) in by_key
    assert ("nstc", CURRENT_ACADEMIC_YEAR) in by_key
    assert ("moe_1w", PRIOR_ACADEMIC_YEAR) in by_key

    # Each group contains exactly one application here.
    for g in groups:
        assert len(g["applications"]) == 1
        a = g["applications"][0]
        assert a["student_name"] is not None
        assert a["has_challenge"] is False

    assert data["summary"]["approved"] == 3
    assert data["summary"]["rejected"] == 0
    assert data["rejected"] == []


@pytest.mark.asyncio
async def test_returns_empty_when_no_renewals(
    db: AsyncSession,
    admin_client: AsyncClient,
    test_scholarship: ScholarshipType,
):
    """No renewals for the requested (type, year) → empty groups + rejected, zero summary."""
    resp = await admin_client.get(
        "/api/v1/renewals/distribution-result",
        params={
            "scholarship_type_id": test_scholarship.id,
            "academic_year": CURRENT_ACADEMIC_YEAR,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["groups"] == []
    assert data["rejected"] == []
    assert data["summary"] == {"approved": 0, "rejected": 0}


@pytest.mark.asyncio
async def test_marks_has_challenge_for_renewals_with_challenge_applications(
    db: AsyncSession,
    admin_client: AsyncClient,
    test_scholarship: ScholarshipType,
):
    """A renewal with a downstream challenge application should have has_challenge=True."""
    stu_challenged = await _make_student(db, nycu_id="stu_ch", name="Challenged Renewal")
    stu_calm = await _make_student(db, nycu_id="stu_calm", name="Quiet Renewal")

    # Renewal A — will be challenged
    renewal_a = await _make_renewal_app(
        db,
        user=stu_challenged,
        scholarship_type=test_scholarship,
        sub_type="nstc",
        renewal_year=PRIOR_ACADEMIC_YEAR,
        app_id_suffix="20001",
    )
    # Renewal B — left alone
    renewal_b = await _make_renewal_app(
        db,
        user=stu_calm,
        scholarship_type=test_scholarship,
        sub_type="nstc",
        renewal_year=PRIOR_ACADEMIC_YEAR,
        app_id_suffix="20002",
    )
    # Challenge application targeting renewal_a (different sub_type)
    await _make_challenge_app(
        db,
        user=stu_challenged,
        scholarship_type=test_scholarship,
        target_sub_type="moe_1w",
        challenges_application_id=renewal_a.id,
        app_id_suffix="29001",
    )

    resp = await admin_client.get(
        "/api/v1/renewals/distribution-result",
        params={
            "scholarship_type_id": test_scholarship.id,
            "academic_year": CURRENT_ACADEMIC_YEAR,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    # Only one group expected — same sub_type & renewal_year for both renewals.
    assert len(data["groups"]) == 1
    apps = data["groups"][0]["applications"]
    by_id = {a["id"]: a for a in apps}
    assert by_id[renewal_a.id]["has_challenge"] is True
    assert by_id[renewal_b.id]["has_challenge"] is False


@pytest.mark.asyncio
async def test_separates_rejected_renewals_from_approved(
    db: AsyncSession,
    admin_client: AsyncClient,
    test_scholarship: ScholarshipType,
):
    """Rejected renewals must appear in `rejected`, not in `groups`."""
    stu_ok = await _make_student(db, nycu_id="stu_ok", name="Approved Renewal")
    stu_rej = await _make_student(db, nycu_id="stu_rej", name="Rejected Renewal")

    await _make_renewal_app(
        db,
        user=stu_ok,
        scholarship_type=test_scholarship,
        sub_type="nstc",
        renewal_year=PRIOR_ACADEMIC_YEAR,
        app_id_suffix="30001",
    )
    rejected_app = await _make_renewal_app(
        db,
        user=stu_rej,
        scholarship_type=test_scholarship,
        sub_type="nstc",
        renewal_year=PRIOR_ACADEMIC_YEAR,
        status=ApplicationStatus.rejected,
        app_id_suffix="30002",
    )

    resp = await admin_client.get(
        "/api/v1/renewals/distribution-result",
        params={
            "scholarship_type_id": test_scholarship.id,
            "academic_year": CURRENT_ACADEMIC_YEAR,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    # Approved goes into a group
    assert len(data["groups"]) == 1
    assert len(data["groups"][0]["applications"]) == 1
    assert data["groups"][0]["applications"][0]["student_name"] == "Approved Renewal"

    # Rejected goes into the rejected list
    assert len(data["rejected"]) == 1
    assert data["rejected"][0]["id"] == rejected_app.id
    assert data["rejected"][0]["student_name"] == "Rejected Renewal"

    assert data["summary"] == {"approved": 1, "rejected": 1}


# Keep an imported sentinel reference (datetime) for forward use; silence linters.
_ = datetime.now(timezone.utc)
