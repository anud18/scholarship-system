"""Pin: the restore_allocation flow and its quota-slot bookkeeping.

These cover behaviours the revoke/suspend service tests do not:

- restore_allocation flips a revoked/suspended application back to
  approved/allocated and clears the revoke/suspend metadata + writes an audit
  log; restoring a non-terminal application raises.
- cancel (revoke/suspend) frees the quota slot by flipping the linked
  CollegeRankingItem to is_allocated=False (while preserving allocated_sub_type
  / allocation_year), and restore re-affirms it (is_allocated=True).
- finalize never resurrects an already revoked/suspended application back to
  approved/allocated.

The conftest provides `db` as the async session (AsyncSession).
"""

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.application import Application, ApplicationStatus
from app.models.audit_log import AuditLog
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.services.manual_distribution_service import ManualDistributionService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def admin_db_user(db):
    from app.models.user import User, UserRole, UserType

    u = User(
        nycu_id="admin_restore_test",
        email="admin_restore@nycu.edu.tw",
        name="Admin Restore",
        role=UserRole.admin,
        user_type=UserType.employee,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def allocated_application(db, admin_db_user):
    """An application in the post-finalize 'allocated' state."""
    from app.models.scholarship import SubTypeSelectionMode
    from app.models.enums import ReviewStage

    app = Application(
        user_id=admin_db_user.id,
        app_id="APP-TEST-RESTORE-001",
        scholarship_type_id=1,
        academic_year=114,
        semester="first",
        status=ApplicationStatus.approved,
        review_stage=ReviewStage.student_draft,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        sub_scholarship_type="nstc",
        quota_allocation_status="allocated",
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


@pytest_asyncio.fixture
async def finalized_ranking(db, admin_db_user):
    """A finalized CollegeRanking for (scholarship_type_id=1, 114, first)."""
    r = CollegeRanking(
        scholarship_type_id=1,
        sub_type_code="nstc",
        academic_year=114,
        semester="first",
        ranking_name="Test Ranking",
        is_finalized=True,
        ranking_status="finalized",
        created_by=admin_db_user.id,
    )
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return r


@pytest_asyncio.fixture
async def allocated_item(db, finalized_ranking, allocated_application):
    """A ranking item that holds an allocated quota slot for the application."""
    item = CollegeRankingItem(
        ranking_id=finalized_ranking.id,
        application_id=allocated_application.id,
        rank_position=1,
        is_allocated=True,
        allocated_sub_type="nstc",
        allocation_year=114,
        status="allocated",
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


# ---------------------------------------------------------------------------
# restore_allocation: status + metadata
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restore_flips_status_and_clears_metadata(db, allocated_application, admin_db_user):
    svc = ManualDistributionService(db)
    await svc.revoke_allocation(
        application_id=allocated_application.id,
        admin_user_id=admin_db_user.id,
        reason="violated terms",
    )
    await db.commit()

    result = await svc.restore_allocation(
        application_id=allocated_application.id,
        admin_user_id=admin_db_user.id,
    )
    await db.commit()
    await db.refresh(allocated_application)

    assert allocated_application.status == ApplicationStatus.approved
    assert allocated_application.quota_allocation_status == "allocated"
    assert allocated_application.revoke_reason is None
    assert allocated_application.revoked_by is None
    assert allocated_application.revoked_at is None
    assert allocated_application.suspend_reason is None
    assert result["restored_from"] == "revoked"

    # An audit log row records the restore transition.
    logs = (
        (
            await db.execute(
                select(AuditLog).where(
                    AuditLog.action == "application.restore",
                    AuditLog.resource_id == str(allocated_application.id),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(logs) == 1


@pytest.mark.asyncio
async def test_restore_non_terminal_raises(db, allocated_application, admin_db_user):
    """Restoring an application that was never revoked/suspended is a conflict."""
    svc = ManualDistributionService(db)
    with pytest.raises(ValueError, match="not revoked/suspended"):
        await svc.restore_allocation(
            application_id=allocated_application.id,
            admin_user_id=admin_db_user.id,
        )


@pytest.mark.asyncio
async def test_restore_after_suspend_clears_suspend_metadata(db, allocated_application, admin_db_user):
    svc = ManualDistributionService(db)
    await svc.suspend_allocation(
        application_id=allocated_application.id,
        admin_user_id=admin_db_user.id,
        reason="休學：已辦理休學",
    )
    await db.commit()

    result = await svc.restore_allocation(
        application_id=allocated_application.id,
        admin_user_id=admin_db_user.id,
    )
    await db.commit()
    await db.refresh(allocated_application)

    assert allocated_application.quota_allocation_status == "allocated"
    assert allocated_application.suspend_reason is None
    assert allocated_application.suspended_by is None
    assert allocated_application.suspended_at is None
    assert result["restored_from"] == "suspended"


# ---------------------------------------------------------------------------
# Quota-slot bookkeeping on the ranking item
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_frees_quota_slot_and_restore_reaffirms(db, allocated_application, allocated_item, admin_db_user):
    svc = ManualDistributionService(db)

    # Revoke frees the slot but keeps the sub_type/year for a clean restore.
    await svc.revoke_allocation(
        application_id=allocated_application.id,
        admin_user_id=admin_db_user.id,
        reason="x",
    )
    await db.commit()
    await db.refresh(allocated_item)
    assert allocated_item.is_allocated is False
    assert allocated_item.allocated_sub_type == "nstc"
    assert allocated_item.allocation_year == 114

    # Restore re-consumes the same slot.
    await svc.restore_allocation(
        application_id=allocated_application.id,
        admin_user_id=admin_db_user.id,
    )
    await db.commit()
    await db.refresh(allocated_item)
    assert allocated_item.is_allocated is True
    assert allocated_item.allocated_sub_type == "nstc"


# ---------------------------------------------------------------------------
# finalize must not resurrect a revoked/suspended application
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_finalize_skips_revoked_application(
    db, allocated_application, allocated_item, finalized_ranking, admin_db_user
):
    svc = ManualDistributionService(db)
    await svc.revoke_allocation(
        application_id=allocated_application.id,
        admin_user_id=admin_db_user.id,
        reason="x",
    )
    await db.commit()

    # Re-running finalize over the finalized ranking must leave the revoked
    # application untouched (not flipped back to approved/allocated, nor stomped
    # to rejected).
    await svc.finalize(scholarship_type_id=1, academic_year=114, semester="first")
    await db.commit()
    await db.refresh(allocated_application)

    assert allocated_application.status == ApplicationStatus.cancelled
    assert allocated_application.quota_allocation_status == "revoked"
