"""
Cumulative received_months tests built on the shared conftest fixtures.

This file complements `test_received_months_service.py` (which uses an
isolated SQLite engine over the roster tables only) by exercising
`received_months_service` against real `User`, `ScholarshipType`, and
`ScholarshipConfiguration` rows via the project-wide `db_sync` / `db`
fixtures. The integration depth catches schema drift that the
roster-only harness can miss (e.g. FK changes against
`scholarship_configurations.id` or `users.id`).

Covers issue #124 §5 — cumulative tracking of months received per
(student, scholarship_configuration). Only `PaymentRosterItem.is_included=True`
items count, and each roster contributes months keyed off its
`roster_cycle`: MONTHLY=1, SEMI_YEARLY=6, YEARLY=12.

Notes:
- The sync-session variant uses `db_sync` (Session); the async variant uses
  the conftest `db` fixture (AsyncSession). `asyncio_mode = auto` in
  pytest.ini means async test functions don't need an explicit marker.
- ScholarshipConfiguration rows are built directly via `db_sync.add/commit`
  because the existing `test_scholarship` fixture is async-only and mixing
  it with a sync session is unsafe.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models.enums import QuotaManagementMode, Semester
from app.models.payment_roster import (
    PaymentRoster,
    PaymentRosterItem,
    RosterCycle,
    RosterStatus,
    RosterTriggerType,
)
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.services.received_months_service import (
    calculate_received_months,
    calculate_received_months_bulk,
    calculate_received_months_bulk_async,
)

# Module-level: integration-style — real session, real models.
pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Sync builders (db_sync)
# ---------------------------------------------------------------------------


def _make_admin(db_sync, nycu_id: str = "rm_admin") -> User:
    user = User(
        nycu_id=nycu_id,
        name="Received Months Admin",
        email=f"{nycu_id}@university.edu",
        user_type=UserType.employee,
        role=UserRole.admin,
    )
    db_sync.add(user)
    db_sync.commit()
    db_sync.refresh(user)
    return user


def _make_scholarship(db_sync, code: str = "rm_scholarship") -> ScholarshipType:
    s = ScholarshipType(
        code=code,
        name="Received Months Test Scholarship",
        description="Issue #124 §5 fixture",
    )
    db_sync.add(s)
    db_sync.commit()
    db_sync.refresh(s)
    return s


def _make_config(
    db_sync,
    scholarship_type: ScholarshipType,
    *,
    config_code: str = "RM-113-1",
    academic_year: int = 113,
    semester: Semester = Semester.first,
) -> ScholarshipConfiguration:
    c = ScholarshipConfiguration(
        scholarship_type_id=scholarship_type.id,
        config_code=config_code,
        config_name="Received Months Config",
        academic_year=academic_year,
        semester=semester,
        quota_management_mode=QuotaManagementMode.simple,
        has_quota_limit=False,
        amount=50000,
    )
    db_sync.add(c)
    db_sync.commit()
    db_sync.refresh(c)
    return c


def _make_roster(
    db_sync,
    *,
    config: ScholarshipConfiguration,
    creator: User,
    roster_code: str,
    period_label: str,
    roster_cycle: RosterCycle,
    academic_year: int = 113,
) -> PaymentRoster:
    roster = PaymentRoster(
        scholarship_configuration_id=config.id,
        roster_code=roster_code,
        period_label=period_label,
        roster_cycle=roster_cycle,
        status=RosterStatus.COMPLETED,
        trigger_type=RosterTriggerType.MANUAL,
        academic_year=academic_year,
        created_by=creator.id,
        started_at=datetime.now(timezone.utc),
    )
    db_sync.add(roster)
    db_sync.commit()
    db_sync.refresh(roster)
    return roster


def _make_item(
    db_sync,
    *,
    roster: PaymentRoster,
    student_nycu_id: str,
    is_included: bool = True,
    application_id: int = 1,
    amount: Decimal = Decimal("10000"),
) -> PaymentRosterItem:
    item = PaymentRosterItem(
        roster_id=roster.id,
        application_id=application_id,
        student_id_number=student_nycu_id,
        student_name=f"Student {student_nycu_id}",
        scholarship_name="Received Months Test Scholarship",
        scholarship_amount=amount,
        is_included=is_included,
    )
    db_sync.add(item)
    db_sync.commit()
    db_sync.refresh(item)
    return item


# ---------------------------------------------------------------------------
# Single-student calculation (sync)
# ---------------------------------------------------------------------------


class TestCalculateReceivedMonthsSingle:
    """Cumulative tracking via calculate_received_months."""

    def test_zero_items_returns_zero(self, db_sync):
        """Case 1: student with no roster items returns 0."""
        admin = _make_admin(db_sync)
        scholarship = _make_scholarship(db_sync)
        config = _make_config(db_sync, scholarship)
        # Roster exists, but no items reference this student.
        _make_roster(
            db_sync,
            config=config,
            creator=admin,
            roster_code="ROSTER-113-2025-01-NSTC",
            period_label="2025-01",
            roster_cycle=RosterCycle.MONTHLY,
        )

        assert calculate_received_months(db_sync, "112550001", config.id) == 0

    def test_single_monthly_item_returns_one(self, db_sync):
        """Case 2: one MONTHLY roster, is_included=True returns 1."""
        admin = _make_admin(db_sync)
        scholarship = _make_scholarship(db_sync)
        config = _make_config(db_sync, scholarship)
        roster = _make_roster(
            db_sync,
            config=config,
            creator=admin,
            roster_code="ROSTER-113-2025-01-NSTC",
            period_label="2025-01",
            roster_cycle=RosterCycle.MONTHLY,
        )
        _make_item(db_sync, roster=roster, student_nycu_id="112550001")

        assert calculate_received_months(db_sync, "112550001", config.id) == 1

    def test_two_monthly_items_same_config_returns_two(self, db_sync):
        """Case 3: two separate MONTHLY rosters return 2."""
        admin = _make_admin(db_sync)
        scholarship = _make_scholarship(db_sync)
        config = _make_config(db_sync, scholarship)
        jan = _make_roster(
            db_sync,
            config=config,
            creator=admin,
            roster_code="ROSTER-113-2025-01-NSTC",
            period_label="2025-01",
            roster_cycle=RosterCycle.MONTHLY,
        )
        feb = _make_roster(
            db_sync,
            config=config,
            creator=admin,
            roster_code="ROSTER-113-2025-02-NSTC",
            period_label="2025-02",
            roster_cycle=RosterCycle.MONTHLY,
        )
        _make_item(db_sync, roster=jan, student_nycu_id="112550001", application_id=1)
        _make_item(db_sync, roster=feb, student_nycu_id="112550001", application_id=2)

        assert calculate_received_months(db_sync, "112550001", config.id) == 2

    def test_excluded_item_not_counted(self, db_sync):
        """Case 4: an item with is_included=False contributes 0."""
        admin = _make_admin(db_sync)
        scholarship = _make_scholarship(db_sync)
        config = _make_config(db_sync, scholarship)
        roster = _make_roster(
            db_sync,
            config=config,
            creator=admin,
            roster_code="ROSTER-113-2025-01-NSTC",
            period_label="2025-01",
            roster_cycle=RosterCycle.MONTHLY,
        )
        _make_item(db_sync, roster=roster, student_nycu_id="112550001", is_included=False)

        assert calculate_received_months(db_sync, "112550001", config.id) == 0

    def test_mixed_included_and_excluded_counts_only_included(self, db_sync):
        """Case 5: one included + one excluded returns 1 (not 2)."""
        admin = _make_admin(db_sync)
        scholarship = _make_scholarship(db_sync)
        config = _make_config(db_sync, scholarship)
        jan = _make_roster(
            db_sync,
            config=config,
            creator=admin,
            roster_code="ROSTER-113-2025-01-NSTC",
            period_label="2025-01",
            roster_cycle=RosterCycle.MONTHLY,
        )
        feb = _make_roster(
            db_sync,
            config=config,
            creator=admin,
            roster_code="ROSTER-113-2025-02-NSTC",
            period_label="2025-02",
            roster_cycle=RosterCycle.MONTHLY,
        )
        _make_item(db_sync, roster=jan, student_nycu_id="112550001", application_id=1, is_included=True)
        _make_item(db_sync, roster=feb, student_nycu_id="112550001", application_id=2, is_included=False)

        assert calculate_received_months(db_sync, "112550001", config.id) == 1

    def test_semi_yearly_cycle_returns_six(self, db_sync):
        """Case 6: one SEMI_YEARLY roster returns 6."""
        admin = _make_admin(db_sync)
        scholarship = _make_scholarship(db_sync)
        config = _make_config(db_sync, scholarship)
        roster = _make_roster(
            db_sync,
            config=config,
            creator=admin,
            roster_code="ROSTER-113-2025-H1-MOE",
            period_label="2025-H1",
            roster_cycle=RosterCycle.SEMI_YEARLY,
        )
        _make_item(db_sync, roster=roster, student_nycu_id="112550001")

        assert calculate_received_months(db_sync, "112550001", config.id) == 6

    def test_yearly_cycle_returns_twelve(self, db_sync):
        """Case 7: one YEARLY roster returns 12."""
        admin = _make_admin(db_sync)
        scholarship = _make_scholarship(db_sync)
        config = _make_config(db_sync, scholarship)
        roster = _make_roster(
            db_sync,
            config=config,
            creator=admin,
            roster_code="ROSTER-113-2025-MOE",
            period_label="2025",
            roster_cycle=RosterCycle.YEARLY,
        )
        _make_item(db_sync, roster=roster, student_nycu_id="112550001")

        assert calculate_received_months(db_sync, "112550001", config.id) == 12

    def test_mixed_cycles_sum_correctly(self, db_sync):
        """Case 8: one MONTHLY (1) + one SEMI_YEARLY (6) returns 7."""
        admin = _make_admin(db_sync)
        scholarship = _make_scholarship(db_sync)
        config = _make_config(db_sync, scholarship)
        monthly = _make_roster(
            db_sync,
            config=config,
            creator=admin,
            roster_code="ROSTER-113-2025-01-NSTC",
            period_label="2025-01",
            roster_cycle=RosterCycle.MONTHLY,
        )
        semi = _make_roster(
            db_sync,
            config=config,
            creator=admin,
            roster_code="ROSTER-113-2025-H1-MOE",
            period_label="2025-H1",
            roster_cycle=RosterCycle.SEMI_YEARLY,
        )
        _make_item(db_sync, roster=monthly, student_nycu_id="112550001", application_id=1)
        _make_item(db_sync, roster=semi, student_nycu_id="112550001", application_id=2)

        assert calculate_received_months(db_sync, "112550001", config.id) == 7

    def test_different_config_isolation(self, db_sync):
        """Case 9: item under config A is invisible when querying config B."""
        admin = _make_admin(db_sync)
        scholarship = _make_scholarship(db_sync)
        config_a = _make_config(db_sync, scholarship, config_code="RM-113-1-A")
        # Different semester to satisfy the uq_scholarship_config_type_year_semester
        # unique constraint (config_code is also unique but we vary semester too).
        config_b = _make_config(
            db_sync,
            scholarship,
            config_code="RM-113-2-B",
            semester=Semester.second,
        )
        roster = _make_roster(
            db_sync,
            config=config_a,
            creator=admin,
            roster_code="ROSTER-113-2025-01-A",
            period_label="2025-01",
            roster_cycle=RosterCycle.MONTHLY,
        )
        _make_item(db_sync, roster=roster, student_nycu_id="112550001")

        # Visible under A.
        assert calculate_received_months(db_sync, "112550001", config_a.id) == 1
        # Invisible under B.
        assert calculate_received_months(db_sync, "112550001", config_b.id) == 0


# ---------------------------------------------------------------------------
# Bulk calculation (sync)
# ---------------------------------------------------------------------------


class TestCalculateReceivedMonthsBulk:
    """Cumulative tracking via calculate_received_months_bulk."""

    def test_bulk_two_students_distinct_counts(self, db_sync):
        """Case 10: two students with different counts under the same config."""
        admin = _make_admin(db_sync)
        scholarship = _make_scholarship(db_sync)
        config = _make_config(db_sync, scholarship)

        # Student A: 1 MONTHLY + 1 SEMI_YEARLY = 7
        jan = _make_roster(
            db_sync,
            config=config,
            creator=admin,
            roster_code="ROSTER-113-2025-01-NSTC",
            period_label="2025-01",
            roster_cycle=RosterCycle.MONTHLY,
        )
        semi = _make_roster(
            db_sync,
            config=config,
            creator=admin,
            roster_code="ROSTER-113-2025-H1-MOE",
            period_label="2025-H1",
            roster_cycle=RosterCycle.SEMI_YEARLY,
        )
        _make_item(db_sync, roster=jan, student_nycu_id="112550001", application_id=1)
        _make_item(db_sync, roster=semi, student_nycu_id="112550001", application_id=2)

        # Student B: 1 MONTHLY only = 1
        _make_item(db_sync, roster=jan, student_nycu_id="112550002", application_id=3)

        result = calculate_received_months_bulk(db_sync, ["112550001", "112550002"], config.id)

        assert result == {"112550001": 7, "112550002": 1}

    def test_bulk_unknown_student_present_with_zero(self, db_sync):
        """
        Case 11: a student not in any roster appears in the result dict
        with value 0 (the service pre-seeds every requested id to 0; the
        key must be present, not absent — see received_months_service.py:97).
        """
        admin = _make_admin(db_sync)
        scholarship = _make_scholarship(db_sync)
        config = _make_config(db_sync, scholarship)
        roster = _make_roster(
            db_sync,
            config=config,
            creator=admin,
            roster_code="ROSTER-113-2025-01-NSTC",
            period_label="2025-01",
            roster_cycle=RosterCycle.MONTHLY,
        )
        _make_item(db_sync, roster=roster, student_nycu_id="112550001")

        result = calculate_received_months_bulk(db_sync, ["112550001", "999999999"], config.id)

        # Both contracts: present-as-key AND value == 0.
        assert "999999999" in result
        assert result["999999999"] == 0
        assert result["112550001"] == 1


# ---------------------------------------------------------------------------
# Async variant (db AsyncSession fixture)
# ---------------------------------------------------------------------------


class TestCalculateReceivedMonthsBulkAsync:
    """Async variant of the bulk function via AsyncSession."""

    async def test_async_single_monthly_returns_one(self, db):
        """
        Case 12: mirrors the sync single-MONTHLY case but through
        calculate_received_months_bulk_async + the async `db` fixture.
        """
        # Build the graph directly with the async session.
        admin = User(
            nycu_id="rm_admin_async",
            name="Async Admin",
            email="rm_admin_async@university.edu",
            user_type=UserType.employee,
            role=UserRole.admin,
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)

        scholarship = ScholarshipType(
            code="rm_async_scholarship",
            name="Async Test Scholarship",
            description="Issue #124 §5 async fixture",
        )
        db.add(scholarship)
        await db.commit()
        await db.refresh(scholarship)

        config = ScholarshipConfiguration(
            scholarship_type_id=scholarship.id,
            config_code="RM-ASYNC-113-1",
            config_name="Async Config",
            academic_year=113,
            semester=Semester.first,
            quota_management_mode=QuotaManagementMode.simple,
            has_quota_limit=False,
            amount=50000,
        )
        db.add(config)
        await db.commit()
        await db.refresh(config)

        roster = PaymentRoster(
            scholarship_configuration_id=config.id,
            roster_code="ROSTER-ASYNC-113-2025-01",
            period_label="2025-01",
            roster_cycle=RosterCycle.MONTHLY,
            status=RosterStatus.COMPLETED,
            trigger_type=RosterTriggerType.MANUAL,
            academic_year=113,
            created_by=admin.id,
            started_at=datetime.now(timezone.utc),
        )
        db.add(roster)
        await db.commit()
        await db.refresh(roster)

        item = PaymentRosterItem(
            roster_id=roster.id,
            application_id=1,
            student_id_number="112550001",
            student_name="Async Student",
            scholarship_name="Async Test Scholarship",
            scholarship_amount=Decimal("10000"),
            is_included=True,
        )
        db.add(item)
        await db.commit()

        result = await calculate_received_months_bulk_async(db, ["112550001"], config.id)

        assert result == {"112550001": 1}
