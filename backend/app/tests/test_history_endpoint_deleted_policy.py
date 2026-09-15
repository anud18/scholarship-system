"""G12/G13 (#974/#975): history-endpoint deleted-records policy + revocation fields.

Policy pinned here (documented in the endpoint docstring):
  - GET /admin/applications/history INCLUDES soft-deleted applications —
    history is the retention surface — and flags them (is_deleted +
    deleted_at/deletion_reason) so the UI can badge them.
  - The response also carries the revocation context the DB already stores
    (revoked_at/revoke_reason/...), which the old schema silently dropped.
  - Admin hard-delete gate (supersedes G30 #992): the endpoint refuses once
    the row has entered 分發階段 (review_stage >= quota_distribution), even
    while status is still 'submitted'; review-stage rows remain deletable.

Auth pattern follows test_admin_student_history_endpoint.py.
"""

from datetime import datetime, timezone

import pytest
import pytest_asyncio

from app.models.application import Application
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def admin_db_user(db):
    user = User(
        nycu_id="g12admin",
        name="G12 Admin",
        email="g12admin@nycu.edu.tw",
        user_type=UserType.employee,
        role=UserRole.admin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def authed_admin_client(client, admin_db_user):
    from app.core.security import require_admin
    from app.main import app

    async def override_require_admin():
        return admin_db_user

    app.dependency_overrides[require_admin] = override_require_admin
    yield client
    del app.dependency_overrides[require_admin]


@pytest_asyncio.fixture
async def history_fixture(db, admin_db_user):
    student = User(
        nycu_id="g12stu001",
        name="G12 學生",
        email="g12stu@nycu.edu.tw",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(student)
    await db.flush()

    stype = ScholarshipType(code="g12_test", name="G12 Test Scholarship")
    db.add(stype)
    await db.flush()
    cfg = ScholarshipConfiguration(
        config_code="G12-CFG",
        config_name="G12 Config",
        is_active=True,
        scholarship_type_id=stype.id,
        academic_year=114,
        amount=5000,
    )
    db.add(cfg)
    await db.flush()

    def make_app(suffix: str, **extra) -> Application:
        app_row = Application(
            app_id=f"APP-G12-{suffix}",
            user_id=student.id,
            scholarship_type_id=stype.id,
            scholarship_configuration_id=cfg.id,
            academic_year=114,
            sub_type_selection_mode="single",
            status=extra.pop("status", "approved"),
        )
        for k, v in extra.items():
            setattr(app_row, k, v)
        db.add(app_row)
        return app_row

    live = make_app("LIVE")
    deleted = make_app(
        "DEAD",
        status="deleted",
        deleted_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
        deleted_by_id=admin_db_user.id,
        deletion_reason="重複申請",
    )
    revoked = make_app(
        "RVK",
        status="cancelled",
        quota_allocation_status="revoked",
        revoked_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        revoked_by=admin_db_user.id,
        revoke_reason="違反要點",
    )
    submitted_in_review = make_app("REVIEW", status="submitted", review_stage="professor_reviewed", academic_year=113)
    submitted_distributed = make_app("GUARD", status="submitted", review_stage="quota_distributed", academic_year=112)
    await db.commit()
    for row in (live, deleted, revoked, submitted_in_review, submitted_distributed):
        await db.refresh(row)
    return {
        "live": live,
        "deleted": deleted,
        "revoked": revoked,
        "in_review": submitted_in_review,
        "guard": submitted_distributed,
    }


def _items(payload):
    return {item["app_id"]: item for item in payload["data"]["items"]}


async def test_history_includes_soft_deleted_with_flags(authed_admin_client, history_fixture):
    response = await authed_admin_client.get("/api/v1/admin/applications/history?size=100&academic_year=114")
    assert response.status_code == 200
    items = _items(response.json())

    assert "APP-G12-DEAD" in items, "soft-deleted applications must remain visible in history (G12 policy)"
    dead = items["APP-G12-DEAD"]
    assert dead["is_deleted"] is True
    assert dead["deleted_at"] is not None
    assert dead["deletion_reason"] == "重複申請"

    live = items["APP-G12-LIVE"]
    assert live["is_deleted"] is False
    assert live["deleted_at"] is None


async def test_history_surfaces_revocation_context(authed_admin_client, history_fixture):
    response = await authed_admin_client.get("/api/v1/admin/applications/history?size=100&academic_year=114")
    assert response.status_code == 200
    items = _items(response.json())

    rvk = items["APP-G12-RVK"]
    assert rvk["revoked_at"] is not None
    assert rvk["revoke_reason"] == "違反要點"
    assert rvk["revoked_by"] is not None


async def test_admin_delete_refuses_when_distribution_stage_reached(authed_admin_client, history_fixture):
    """status=submitted but review_stage=quota_distributed → 400, row survives."""
    guard_app = history_fixture["guard"]
    response = await authed_admin_client.request(
        "DELETE",
        f"/api/v1/admin/applications/{guard_app.id}",
        json={"reason": "should be refused"},
    )
    assert response.status_code == 400
    assert "分發階段" in response.text


async def test_admin_delete_allows_review_stage_rows(authed_admin_client, history_fixture):
    """status=submitted + review_stage=professor_reviewed is still pre-distribution → deletable."""
    review_app = history_fixture["in_review"]
    response = await authed_admin_client.request(
        "DELETE",
        f"/api/v1/admin/applications/{review_app.id}",
        json={"reason": "review-stage cleanup"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["id"] == review_app.id
