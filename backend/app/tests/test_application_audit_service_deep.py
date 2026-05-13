"""
Deep async-DB tests for `ApplicationAuditService.log_application_operation`.

The audit trail is regulatory-adjacent — silent failures here mean lost
evidence in compliance reviews. We pin the persistence path: every call
writes an AuditLog row with the expected fields, and the request-derived
fields (ip_address, user_agent, etc.) are NULL when no request is passed.

Contract pinned (5 cases):
- Minimal happy path: action, resource_type='application', resource_id,
  user_id persist.
- description + old_values + new_values + meta_data round-trip.
- No request ⇒ ip_address / user_agent / request_method / request_url
  all NULL.
- status='failed' + error_message persists.
- The action enum value (string) is what's stored, not the enum object.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditAction, AuditLog
from app.models.user import User, UserRole, UserType
from app.services.application_audit_service import ApplicationAuditService


async def _seed_user(db: AsyncSession, *, nycu_id: str, role: UserRole = UserRole.admin) -> User:
    u = User(
        nycu_id=nycu_id,
        name=f"User {nycu_id}",
        email=f"{nycu_id}@u.edu",
        user_type=UserType.employee if role != UserRole.student else UserType.student,
        role=role,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest.mark.asyncio
async def test_minimal_happy_path_persists_required_fields(db: AsyncSession):
    admin = await _seed_user(db, nycu_id="audit_minimal")
    service = ApplicationAuditService(db)

    log = await service.log_application_operation(
        application_id=42,
        action=AuditAction.approve,
        user=admin,
    )

    assert log is not None
    fetched = (await db.execute(select(AuditLog).where(AuditLog.id == log.id))).scalar_one()
    assert fetched.user_id == admin.id
    # The action enum's .value (a string) is what gets stored.
    assert fetched.action == AuditAction.approve.value
    assert fetched.resource_type == "application"
    assert fetched.resource_id == "42"


@pytest.mark.asyncio
async def test_description_and_value_diffs_round_trip(db: AsyncSession):
    admin = await _seed_user(db, nycu_id="audit_diffs")
    service = ApplicationAuditService(db)

    log = await service.log_application_operation(
        application_id=7,
        action=AuditAction.update,
        user=admin,
        description="Status update by admin",
        old_values={"status": "submitted"},
        new_values={"status": "approved"},
        meta_data={"source": "dashboard"},
    )

    fetched = (await db.execute(select(AuditLog).where(AuditLog.id == log.id))).scalar_one()
    assert fetched.description == "Status update by admin"
    assert fetched.old_values == {"status": "submitted"}
    assert fetched.new_values == {"status": "approved"}
    assert fetched.meta_data == {"source": "dashboard"}


@pytest.mark.asyncio
async def test_no_request_means_request_fields_are_null(db: AsyncSession):
    """When the optional Request param is omitted, all request-derived
    fields (ip_address, user_agent, request_method, request_url) are NULL."""
    admin = await _seed_user(db, nycu_id="audit_no_request")
    service = ApplicationAuditService(db)

    log = await service.log_application_operation(
        application_id=1,
        action=AuditAction.approve,
        user=admin,
        request=None,
    )

    fetched = (await db.execute(select(AuditLog).where(AuditLog.id == log.id))).scalar_one()
    assert fetched.ip_address is None
    assert fetched.user_agent is None
    assert fetched.request_method is None
    assert fetched.request_url is None


@pytest.mark.asyncio
async def test_failed_status_with_error_message_persists(db: AsyncSession):
    """Audit logs track failures, not just successes. Pin the negative-path persistence."""
    admin = await _seed_user(db, nycu_id="audit_failed")
    service = ApplicationAuditService(db)

    log = await service.log_application_operation(
        application_id=99,
        action=AuditAction.reject,
        user=admin,
        status="failed",
        error_message="ValidationError: status transition not allowed",
    )

    fetched = (await db.execute(select(AuditLog).where(AuditLog.id == log.id))).scalar_one()
    assert fetched.status == "failed"
    assert fetched.error_message == "ValidationError: status transition not allowed"


@pytest.mark.asyncio
async def test_multiple_audits_for_same_application_are_distinct_rows(db: AsyncSession):
    """Each call creates a new row — no overwriting of prior audit history."""
    admin = await _seed_user(db, nycu_id="audit_multi")
    service = ApplicationAuditService(db)

    log1 = await service.log_application_operation(
        application_id=15,
        action=AuditAction.submit,
        user=admin,
        description="first",
    )
    log2 = await service.log_application_operation(
        application_id=15,
        action=AuditAction.approve,
        user=admin,
        description="second",
    )
    log3 = await service.log_application_operation(
        application_id=15,
        action=AuditAction.update,
        user=admin,
        description="third",
    )

    rows = (await db.execute(select(AuditLog).where(AuditLog.resource_id == "15"))).scalars().all()
    assert len(rows) == 3
    descriptions = {r.description for r in rows}
    assert descriptions == {"first", "second", "third"}
