"""Pin: the restore_allocation flow and its quota-slot bookkeeping.

These cover behaviours the revoke/suspend service tests do not:

- restore_allocation flips a revoked/suspended application back to
  approved/allocated and clears the revoke/suspend metadata + writes an audit
  log; restoring a non-terminal application raises.
- cancel (revoke/suspend) frees the quota slot by flipping the linked
  CollegeRankingItem to is_allocated=False (while preserving allocated_sub_type
  / allocation_config_id), and restore re-affirms it (is_allocated=True).
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
    from app.models.scholarship import ScholarshipConfiguration

    cfg = ScholarshipConfiguration(
        scholarship_type_id=1,
        config_code="RESTORE-114",
        config_name="Restore 114",
        academic_year=114,
        semester="first",
        amount=50000,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)

    item = CollegeRankingItem(
        ranking_id=finalized_ranking.id,
        application_id=allocated_application.id,
        rank_position=1,
        is_allocated=True,
        allocated_sub_type="nstc",
        allocation_config_id=cfg.id,
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

    # G18 (#980): the service no longer writes the legacy ad-hoc audit row —
    # the endpoint emits AuditAction.restore via ApplicationAuditService
    # (wiring pinned by test_audit_wiring_invariants.py). The service instead
    # returns the context the endpoint logs, including the original
    # cancellation reason it just cleared from the application row.
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
    assert logs == []
    assert result["app_id"] == allocated_application.app_id
    assert result["restored_reason"] is not None


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
    assert allocated_item.allocation_config_id is not None

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


# ---------------------------------------------------------------------------
# restore_allocation: quota oversubscription guard (#1081 finding I)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_restore_blocked_when_slot_already_reallocated(db, admin_db_user):
    """#1081 finding I: revoke frees a quota slot; if that slot is then handed to
    another student, restoring the original must NOT double-book it. allocate()/
    finalize() gate on _assert_round_not_oversubscribed; restore_allocation now
    does too."""
    from app.models.scholarship import ScholarshipConfiguration, SubTypeSelectionMode
    from app.models.enums import ReviewStage
    from app.models.user import User, UserRole, UserType

    # Single-slot nstc pool.
    cfg = ScholarshipConfiguration(
        scholarship_type_id=1,
        config_code="OVERSUB-114",
        config_name="Oversub 114",
        academic_year=114,
        semester="first",
        amount=50000,
        quotas={"nstc": 1},
    )
    db.add(cfg)

    ranking = CollegeRanking(
        scholarship_type_id=1,
        sub_type_code="nstc",
        academic_year=114,
        semester="first",
        ranking_name="Oversub Ranking",
        is_finalized=True,
        ranking_status="finalized",
        created_by=admin_db_user.id,
    )
    db.add(ranking)

    other_student = User(
        nycu_id="oversub_stu_b",
        email="oversub_b@nycu.edu.tw",
        name="Oversub B",
        role=UserRole.student,
        user_type=UserType.student,
    )
    db.add(other_student)
    await db.commit()
    await db.refresh(cfg)
    await db.refresh(ranking)
    await db.refresh(other_student)

    def _app(app_id, user_id, alloc_status):
        return Application(
            user_id=user_id,
            app_id=app_id,
            scholarship_type_id=1,
            academic_year=114,
            semester="first",
            status=ApplicationStatus.cancelled if alloc_status != "allocated" else ApplicationStatus.approved,
            review_stage=ReviewStage.student_draft,
            sub_type_selection_mode=SubTypeSelectionMode.single,
            sub_scholarship_type="nstc",
            is_renewal=False,
            quota_allocation_status=alloc_status,
            revoke_reason="freed" if alloc_status == "revoked" else None,
        )

    # A: revoked (its slot was freed). B: currently holds the only slot.
    app_a = _app("APP-OVERSUB-A", admin_db_user.id, "revoked")
    app_b = _app("APP-OVERSUB-B", other_student.id, "allocated")
    db.add_all([app_a, app_b])
    await db.commit()
    await db.refresh(app_a)
    await db.refresh(app_b)

    item_a = CollegeRankingItem(
        ranking_id=ranking.id,
        application_id=app_a.id,
        rank_position=1,
        is_allocated=False,  # freed at revoke time
        allocated_sub_type="nstc",
        allocation_config_id=cfg.id,
        status="allocated",
    )
    item_b = CollegeRankingItem(
        ranking_id=ranking.id,
        application_id=app_b.id,
        rank_position=2,
        is_allocated=True,  # took the freed slot
        allocated_sub_type="nstc",
        allocation_config_id=cfg.id,
        status="allocated",
    )
    db.add_all([item_a, item_b])
    await db.commit()

    svc = ManualDistributionService(db)
    # pool=1, B already consumes it → restoring A would make it 2/1.
    with pytest.raises(ValueError, match="配額超額|超過總配額"):
        await svc.restore_allocation(app_a.id, admin_db_user.id)
