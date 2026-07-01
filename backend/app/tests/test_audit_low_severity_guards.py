"""
Regression tests for three LOW/LOW-MEDIUM findings from the same security
audit (issue #1081):

Finding H: POST /college-review/rankings/{id}/import-excel was the one
ranking-mutation endpoint that omitted the #63 college-review deadline
guard every sibling (create/update-order/finalize/unfinalize) enforces.

Finding I: ManualDistributionService.restore_allocation didn't call
_assert_round_not_oversubscribed (unlike allocate/finalize), so a
revoke-then-reallocate-then-restore sequence could double-book a single
quota slot with no DB-level guard.

Finding K: RosterService.restore_item never re-checked
application.status == approved before re-including an item (unlike
reconcile_roster's add path), so an admin could restore an item whose
application was since withdrawn/rejected/revoked/suspended.
"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.exceptions import AuthorizationError
from app.models.application import Application, ApplicationStatus
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.scholarship import ScholarshipConfiguration, SubTypeSelectionMode
from app.models.user import User, UserRole, UserType
from app.services.college_review_service import CollegeReviewService
from app.services.manual_distribution_service import ManualDistributionService

# ---------------------------------------------------------------------------
# Finding H: ranking-import deadline guard
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def college_user(db):
    user = User(
        nycu_id="authz_college_deadline",
        name="College Deadline Tester",
        email="authz_college_deadline@university.edu",
        user_type=UserType.employee,
        role=UserRole.college,
        college_code="CS",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


class TestRankingImportDeadlineGuard:
    @pytest.mark.asyncio
    async def test_import_after_deadline_is_blocked_for_college_user(self, db, college_user):
        cfg = ScholarshipConfiguration(
            scholarship_type_id=1,
            config_code="DEADLINE-TEST-114",
            config_name="Deadline Test 114",
            academic_year=114,
            semester="first",
            amount=50000,
            college_review_end=datetime.now(timezone.utc) - timedelta(days=1),
        )
        db.add(cfg)
        ranking = CollegeRanking(
            scholarship_type_id=1,
            sub_type_code="nstc",
            academic_year=114,
            semester="first",
            college_code="CS",
        )
        db.add(ranking)
        await db.commit()
        await db.refresh(ranking)

        service = CollegeReviewService(db)
        with pytest.raises(AuthorizationError, match="已過排名截止時間"):
            await service.assert_ranking_within_deadline_by_ranking(ranking.id, college_user)

    @pytest.mark.asyncio
    async def test_import_before_deadline_is_allowed(self, db, college_user):
        cfg = ScholarshipConfiguration(
            scholarship_type_id=1,
            config_code="DEADLINE-TEST-115",
            config_name="Deadline Test 115",
            academic_year=115,
            semester="first",
            amount=50000,
            college_review_end=datetime.now(timezone.utc) + timedelta(days=1),
        )
        db.add(cfg)
        ranking = CollegeRanking(
            scholarship_type_id=1,
            sub_type_code="nstc",
            academic_year=115,
            semester="first",
            college_code="CS",
        )
        db.add(ranking)
        await db.commit()
        await db.refresh(ranking)

        service = CollegeReviewService(db)
        # Should not raise.
        await service.assert_ranking_within_deadline_by_ranking(ranking.id, college_user)


# ---------------------------------------------------------------------------
# Finding I: restore_allocation oversubscription guard
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def admin_user_low_sev(db):
    user = User(
        nycu_id="authz_admin_low_sev",
        name="Admin Low Sev",
        email="authz_admin_low_sev@university.edu",
        user_type=UserType.employee,
        role=UserRole.admin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


class TestRestoreAllocationOversubscriptionGuard:
    @pytest.mark.asyncio
    async def test_restore_into_already_full_quota_is_rejected(self, db, admin_user_low_sev):
        cfg = ScholarshipConfiguration(
            scholarship_type_id=1,
            config_code="OVERSUB-TEST-114",
            config_name="Oversubscription Test 114",
            academic_year=114,
            semester="first",
            amount=50000,
            quotas={"nstc": 1},
        )
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)

        # Two distinct students -- Application has a unique constraint on
        # (user_id, scholarship_type_id, academic_year, semester).
        student_a = User(
            nycu_id="authz_student_oversub_a",
            name="Student Oversub A",
            email="authz_student_oversub_a@university.edu",
            user_type=UserType.student,
            role=UserRole.student,
        )
        student_b = User(
            nycu_id="authz_student_oversub_b",
            name="Student Oversub B",
            email="authz_student_oversub_b@university.edu",
            user_type=UserType.student,
            role=UserRole.student,
        )
        db.add_all([student_a, student_b])
        await db.commit()
        await db.refresh(student_a)
        await db.refresh(student_b)

        # Application A: previously revoked (its ranking item was freed by
        # revoke, allocated_sub_type/allocation_config_id preserved).
        app_a = Application(
            user_id=student_a.id,
            app_id="APP-OVERSUB-A",
            scholarship_type_id=1,
            scholarship_configuration_id=cfg.id,
            academic_year=114,
            semester="first",
            status=ApplicationStatus.cancelled,
            sub_type_selection_mode=SubTypeSelectionMode.single,
            sub_scholarship_type="nstc",
            quota_allocation_status="revoked",
            is_renewal=False,
        )
        db.add(app_a)

        # Application B: currently allocated, occupying the only slot.
        app_b = Application(
            user_id=student_b.id,
            app_id="APP-OVERSUB-B",
            scholarship_type_id=1,
            scholarship_configuration_id=cfg.id,
            academic_year=114,
            semester="first",
            status=ApplicationStatus.approved,
            sub_type_selection_mode=SubTypeSelectionMode.single,
            sub_scholarship_type="nstc",
            quota_allocation_status="allocated",
            is_renewal=False,
        )
        db.add(app_b)
        await db.commit()
        await db.refresh(app_a)
        await db.refresh(app_b)

        ranking = CollegeRanking(scholarship_type_id=1, sub_type_code="nstc", academic_year=114, semester="first")
        db.add(ranking)
        await db.commit()
        await db.refresh(ranking)

        item_a = CollegeRankingItem(
            ranking_id=ranking.id,
            application_id=app_a.id,
            rank_position=1,
            is_allocated=False,  # freed by the earlier revoke
            allocated_sub_type="nstc",
            allocation_config_id=cfg.id,
        )
        item_b = CollegeRankingItem(
            ranking_id=ranking.id,
            application_id=app_b.id,
            rank_position=2,
            is_allocated=True,  # occupying the one available slot
            allocated_sub_type="nstc",
            allocation_config_id=cfg.id,
        )
        db.add_all([item_a, item_b])
        await db.commit()

        service = ManualDistributionService(db)
        with pytest.raises(ValueError, match="配額超額"):
            await service.restore_allocation(application_id=app_a.id, admin_user_id=admin_user_low_sev.id)


# ---------------------------------------------------------------------------
# Finding K: restore_item application-status re-check
# ---------------------------------------------------------------------------


class TestRosterRestoreItemStatusRecheck:
    def test_restore_item_rejects_non_approved_application(self, db_sync, admin_user_low_sev):
        # Note: RosterService uses the sync session (db_sync) -- a separate
        # in-memory SQLite DB from the async `db` fixture -- so every row here
        # (including the ScholarshipConfiguration) must be created via db_sync.
        from app.models.payment_roster import (
            PaymentRoster,
            PaymentRosterItem,
            RosterCycle,
            RosterStatus,
            RosterTriggerType,
        )
        from app.services.roster_service import RosterService

        cfg = ScholarshipConfiguration(
            scholarship_type_id=1,
            config_code="ROSTER-RESTORE-114",
            config_name="Roster Restore 114",
            academic_year=114,
            semester="first",
            amount=50000,
        )
        db_sync.add(cfg)
        db_sync.commit()
        db_sync.refresh(cfg)

        admin = User(
            nycu_id="authz_admin_roster_sync",
            name="Admin Roster Sync",
            email="authz_admin_roster_sync@university.edu",
            user_type=UserType.employee,
            role=UserRole.admin,
        )
        db_sync.add(admin)
        db_sync.commit()
        db_sync.refresh(admin)

        student = User(
            nycu_id="authz_student_roster_sync",
            name="Student Roster Sync",
            email="authz_student_roster_sync@university.edu",
            user_type=UserType.student,
            role=UserRole.student,
        )
        db_sync.add(student)
        db_sync.commit()
        db_sync.refresh(student)

        application = Application(
            user_id=student.id,
            app_id="APP-ROSTER-RESTORE",
            scholarship_type_id=1,
            academic_year=114,
            semester="first",
            # The application was withdrawn/rejected AFTER the item was
            # removed from the roster -- no longer approved.
            status=ApplicationStatus.rejected,
            sub_type_selection_mode=SubTypeSelectionMode.single,
            sub_scholarship_type="nstc",
        )
        db_sync.add(application)
        db_sync.commit()
        db_sync.refresh(application)

        roster = PaymentRoster(
            scholarship_configuration_id=cfg.id,
            academic_year=114,
            period_label="114-1",
            roster_cycle=RosterCycle.SEMI_YEARLY,
            trigger_type=RosterTriggerType.MANUAL,
            created_by=admin.id,
            roster_code="TEST-ROSTER-RESTORE",
            status=RosterStatus.LOCKED,
        )
        db_sync.add(roster)
        db_sync.commit()
        db_sync.refresh(roster)

        item = PaymentRosterItem(
            roster_id=roster.id,
            application_id=application.id,
            student_id_number="A123456789",
            student_number=student.nycu_id,
            student_name=student.name,
            scholarship_name="Test Scholarship",
            scholarship_amount=50000,
            is_included=False,  # previously removed
            exclusion_reason="manually removed",
        )
        db_sync.add(item)
        db_sync.commit()
        db_sync.refresh(item)

        service = RosterService(db_sync)
        with pytest.raises(ValueError, match="no longer approved"):
            service.restore_item(roster_id=roster.id, item_id=item.id, admin_user_id=admin.id)
