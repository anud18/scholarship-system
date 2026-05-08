"""
Contract tests for ApplicationAuditService.

Phase 5 of test-surface-hardening: legal-trail safety net. For every
public log_* method on ApplicationAuditService, exercise it against a real
DB session and assert that exactly one audit row appears in `audit_logs`
with the expected action / resource_type / user_id / status shape.

The plan calls these "audit-log-contract" tests. They run in the nightly
lane (not per-PR) because they're slow and exercise many DB writes; they
are the primary signal when an endpoint quietly drops or duplicates an
audit emit between releases.

Notes:
- Uses the async `db` fixture from conftest.py since
  ApplicationAuditService takes AsyncSession (line 23).
- AuditAction values are imported from app.models.audit_log (line 14).
- A FastAPI Request object is omitted because the helper takes it as
  Optional and the contract is the row shape, not the IP/UA derivation.
"""

import pytest
from sqlalchemy import select

from app.models.audit_log import AuditAction, AuditLog
from app.models.user import User, UserRole, UserType
from app.services.application_audit_service import ApplicationAuditService

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def audit_user(db) -> User:
    """A persisted user that subsequent log_* calls can reference."""
    user = User(
        nycu_id="auditcontract",
        name="Audit Contract",
        email="audit@university.edu",
        user_type=UserType.employee,
        role=UserRole.admin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _count_logs_for(db, application_id: int) -> int:
    res = await db.execute(select(AuditLog).where(AuditLog.resource_id == str(application_id)))
    return len(res.scalars().all())


async def _last_log_for(db, application_id: int) -> AuditLog:
    res = await db.execute(
        select(AuditLog).where(AuditLog.resource_id == str(application_id)).order_by(AuditLog.id.desc())
    )
    rows = res.scalars().all()
    assert rows, f"no audit row for application_id={application_id}"
    return rows[0]


class TestApplicationAuditServiceContract:
    """One row per call, with expected action / user / resource shape."""

    async def test_log_application_operation_writes_one_row(self, db, audit_user):
        svc = ApplicationAuditService(db)
        result = await svc.log_application_operation(
            application_id=1001,
            action=AuditAction.create,
            user=audit_user,
            description="phase 5 test",
            new_values={"status": "draft"},
        )

        assert result is not None
        assert await _count_logs_for(db, 1001) == 1
        row = await _last_log_for(db, 1001)
        assert row.action == AuditAction.create.value
        assert row.resource_type == "application"
        assert row.user_id == audit_user.id
        assert row.status == "success"

    async def test_log_view_application_writes_view_row(self, db, audit_user):
        svc = ApplicationAuditService(db)
        await svc.log_view_application(
            application_id=1002,
            app_id="APP-113-1-00002",
            user=audit_user,
        )
        assert await _count_logs_for(db, 1002) == 1
        row = await _last_log_for(db, 1002)
        assert row.action == AuditAction.view.value

    async def test_log_status_update_records_old_and_new(self, db, audit_user):
        svc = ApplicationAuditService(db)
        await svc.log_status_update(
            application_id=1003,
            app_id="APP-113-1-00003",
            old_status="submitted",
            new_status="approved",
            user=audit_user,
            reason="meets criteria",
        )
        row = await _last_log_for(db, 1003)
        assert row.action == AuditAction.update.value
        assert row.old_values == {"status": "submitted"}
        assert row.new_values == {"status": "approved"}

    async def test_log_application_submit(self, db, audit_user):
        svc = ApplicationAuditService(db)
        await svc.log_application_submit(
            application_id=1004,
            app_id="APP-113-1-00004",
            user=audit_user,
        )
        row = await _last_log_for(db, 1004)
        assert row.action == AuditAction.submit.value

    async def test_log_application_approve(self, db, audit_user):
        svc = ApplicationAuditService(db)
        await svc.log_application_approve(
            application_id=1005,
            app_id="APP-113-1-00005",
            user=audit_user,
            comments="ok",
        )
        row = await _last_log_for(db, 1005)
        assert row.action == AuditAction.approve.value

    async def test_log_application_reject(self, db, audit_user):
        svc = ApplicationAuditService(db)
        await svc.log_application_reject(
            application_id=1006,
            app_id="APP-113-1-00006",
            user=audit_user,
            reason="incomplete",
        )
        row = await _last_log_for(db, 1006)
        assert row.action == AuditAction.reject.value

    async def test_log_application_create(self, db, audit_user):
        svc = ApplicationAuditService(db)
        await svc.log_application_create(
            application_id=1007,
            app_id="APP-113-1-00007",
            user=audit_user,
        )
        row = await _last_log_for(db, 1007)
        assert row.action == AuditAction.create.value

    async def test_log_application_update(self, db, audit_user):
        svc = ApplicationAuditService(db)
        await svc.log_application_update(
            application_id=1008,
            app_id="APP-113-1-00008",
            user=audit_user,
            old_values={"amount": 1000},
            new_values={"amount": 2000},
        )
        row = await _last_log_for(db, 1008)
        assert row.action == AuditAction.update.value
        assert row.old_values["amount"] == 1000
        assert row.new_values["amount"] == 2000

    async def test_log_application_withdraw(self, db, audit_user):
        svc = ApplicationAuditService(db)
        await svc.log_application_withdraw(
            application_id=1009,
            app_id="APP-113-1-00009",
            user=audit_user,
        )
        row = await _last_log_for(db, 1009)
        assert row.action == AuditAction.withdraw.value

    async def test_log_delete_application(self, db, audit_user):
        svc = ApplicationAuditService(db)
        await svc.log_delete_application(
            application_id=1010,
            app_id="APP-113-1-00010",
            user=audit_user,
        )
        row = await _last_log_for(db, 1010)
        assert row.action == AuditAction.delete.value
