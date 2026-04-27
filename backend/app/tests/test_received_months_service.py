"""
Tests for received_months_service — shared received-months calculation.

Counts months a student has received under a scholarship_configuration,
summing across RosterCycle (MONTHLY=1, SEMI_YEARLY=6, YEARLY=12) and
across all sub_types (nstc, moe_1w, moe_2w combined).

Self-contained: uses its own SQLite engine, not the shared conftest fixtures,
because the shared conftest imports app.db.session which fails to load under
SQLite (pool_size incompatible).
"""

import os
import sys
import types
from datetime import datetime, timezone
from typing import Generator

os.environ["TESTING"] = "true"
os.environ["PYTEST_CURRENT_TEST"] = "true"

# Force SQLite-compatible types by overriding settings BEFORE any model import
from app.core.config import settings  # noqa: E402

settings.database_url = "sqlite+aiosqlite:///:memory:"
settings.database_url_sync = "sqlite:///:memory:"

# Stub app.db.session before any downstream module imports it. The real
# session.py passes PostgreSQL-only pool kwargs to create_engine which fails
# under SQLite; stubbing lets pure-logic services (like the one under test)
# load without engine construction.
if "app.db.session" not in sys.modules:
    stub = types.ModuleType("app.db.session")
    stub.AsyncSessionLocal = None
    stub.SessionLocal = None
    stub.async_engine = None
    stub.sync_engine = None
    sys.modules["app.db.session"] = stub

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db.base_class import Base  # noqa: E402
from app.models.payment_roster import (  # noqa: E402
    PaymentRoster,
    PaymentRosterItem,
    RosterCycle,
    RosterTriggerType,
)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    """Fresh in-memory SQLite DB per test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Only create the tables we need; other app tables use PostgreSQL-specific
    # types (e.g. JSONB) that SQLite can't render.
    tables = [PaymentRoster.__table__, PaymentRosterItem.__table__]
    Base.metadata.create_all(bind=engine, tables=tables)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine, tables=tables)
        engine.dispose()


def _make_roster(
    db: Session,
    *,
    roster_code: str,
    scholarship_config_id: int,
    academic_year: int,
    period_label: str,
    roster_cycle: RosterCycle,
    sub_type: str | None = None,
) -> PaymentRoster:
    roster = PaymentRoster(
        roster_code=roster_code,
        scholarship_configuration_id=scholarship_config_id,
        academic_year=academic_year,
        period_label=period_label,
        roster_cycle=roster_cycle,
        sub_type=sub_type,
        trigger_type=RosterTriggerType.MANUAL,
        created_by=1,
        started_at=datetime.now(timezone.utc),
    )
    db.add(roster)
    db.flush()
    return roster


def _make_item(
    db: Session,
    *,
    roster_id: int,
    student_nycu_id: str,
    is_included: bool = True,
    application_id: int = 1,
) -> PaymentRosterItem:
    item = PaymentRosterItem(
        roster_id=roster_id,
        application_id=application_id,
        student_id_number=student_nycu_id,
        student_name="Test Student",
        scholarship_name="Test Scholarship",
        scholarship_amount=10000,
        is_included=is_included,
    )
    db.add(item)
    db.flush()
    return item


class TestCalculateReceivedMonths:
    """Test calculate_received_months for a single student."""

    def test_returns_zero_when_no_rosters(self, db):
        from app.services.received_months_service import calculate_received_months

        assert calculate_received_months(db, "S001", scholarship_config_id=1) == 0

    def test_monthly_roster_counts_as_one_month(self, db):
        from app.services.received_months_service import calculate_received_months

        roster = _make_roster(
            db,
            roster_code="R1",
            scholarship_config_id=1,
            academic_year=113,
            period_label="2024-09",
            roster_cycle=RosterCycle.MONTHLY,
        )
        _make_item(db, roster_id=roster.id, student_nycu_id="S001")

        assert calculate_received_months(db, "S001", scholarship_config_id=1) == 1

    def test_semi_yearly_roster_counts_as_six_months(self, db):
        from app.services.received_months_service import calculate_received_months

        roster = _make_roster(
            db,
            roster_code="R1",
            scholarship_config_id=1,
            academic_year=113,
            period_label="2024-H1",
            roster_cycle=RosterCycle.SEMI_YEARLY,
        )
        _make_item(db, roster_id=roster.id, student_nycu_id="S001")

        assert calculate_received_months(db, "S001", scholarship_config_id=1) == 6

    def test_yearly_roster_counts_as_twelve_months(self, db):
        from app.services.received_months_service import calculate_received_months

        roster = _make_roster(
            db,
            roster_code="R1",
            scholarship_config_id=1,
            academic_year=113,
            period_label="2024",
            roster_cycle=RosterCycle.YEARLY,
        )
        _make_item(db, roster_id=roster.id, student_nycu_id="S001")

        assert calculate_received_months(db, "S001", scholarship_config_id=1) == 12

    def test_combines_across_sub_types(self, db):
        """nstc (6 months) + moe_1w (6 months) = 12 months for same student."""
        from app.services.received_months_service import calculate_received_months

        r1 = _make_roster(
            db,
            roster_code="R1",
            scholarship_config_id=1,
            academic_year=113,
            period_label="2024-H1",
            roster_cycle=RosterCycle.SEMI_YEARLY,
            sub_type="nstc",
        )
        r2 = _make_roster(
            db,
            roster_code="R2",
            scholarship_config_id=1,
            academic_year=113,
            period_label="2024-H2",
            roster_cycle=RosterCycle.SEMI_YEARLY,
            sub_type="moe_1w",
        )
        _make_item(db, roster_id=r1.id, student_nycu_id="S001")
        _make_item(db, roster_id=r2.id, student_nycu_id="S001")

        assert calculate_received_months(db, "S001", scholarship_config_id=1) == 12

    def test_excludes_is_included_false(self, db):
        from app.services.received_months_service import calculate_received_months

        roster = _make_roster(
            db,
            roster_code="R1",
            scholarship_config_id=1,
            academic_year=113,
            period_label="2024-09",
            roster_cycle=RosterCycle.MONTHLY,
        )
        _make_item(db, roster_id=roster.id, student_nycu_id="S001", is_included=False)

        assert calculate_received_months(db, "S001", scholarship_config_id=1) == 0

    def test_excludes_other_scholarship_configs(self, db):
        """Only counts rosters matching the given scholarship_config_id."""
        from app.services.received_months_service import calculate_received_months

        r1 = _make_roster(
            db,
            roster_code="R1",
            scholarship_config_id=1,
            academic_year=113,
            period_label="2024-09",
            roster_cycle=RosterCycle.MONTHLY,
        )
        r2 = _make_roster(
            db,
            roster_code="R2",
            scholarship_config_id=99,
            academic_year=113,
            period_label="2024-09",
            roster_cycle=RosterCycle.MONTHLY,
        )
        _make_item(db, roster_id=r1.id, student_nycu_id="S001")
        _make_item(db, roster_id=r2.id, student_nycu_id="S001")

        assert calculate_received_months(db, "S001", scholarship_config_id=1) == 1

    def test_isolates_per_student(self, db):
        from app.services.received_months_service import calculate_received_months

        roster = _make_roster(
            db,
            roster_code="R1",
            scholarship_config_id=1,
            academic_year=113,
            period_label="2024-09",
            roster_cycle=RosterCycle.MONTHLY,
        )
        _make_item(db, roster_id=roster.id, student_nycu_id="S001", application_id=1)
        _make_item(db, roster_id=roster.id, student_nycu_id="S002", application_id=2)

        assert calculate_received_months(db, "S001", scholarship_config_id=1) == 1
        assert calculate_received_months(db, "S002", scholarship_config_id=1) == 1
        assert calculate_received_months(db, "S999", scholarship_config_id=1) == 0


class TestCalculateReceivedMonthsBulk:
    """Test bulk version used by manual distribution to avoid N+1."""

    def test_returns_dict_keyed_by_student_id(self, db):
        from app.services.received_months_service import calculate_received_months_bulk

        roster = _make_roster(
            db,
            roster_code="R1",
            scholarship_config_id=1,
            academic_year=113,
            period_label="2024-09",
            roster_cycle=RosterCycle.MONTHLY,
        )
        _make_item(db, roster_id=roster.id, student_nycu_id="S001", application_id=1)
        _make_item(db, roster_id=roster.id, student_nycu_id="S002", application_id=2)

        result = calculate_received_months_bulk(
            db, ["S001", "S002", "S999"], scholarship_config_id=1
        )
        assert result == {"S001": 1, "S002": 1, "S999": 0}

    def test_empty_list_returns_empty_dict(self, db):
        from app.services.received_months_service import calculate_received_months_bulk

        assert calculate_received_months_bulk(db, [], scholarship_config_id=1) == {}

    def test_bulk_matches_single_for_each_student(self, db):
        """Bulk result must equal summing each student individually."""
        from app.services.received_months_service import (
            calculate_received_months,
            calculate_received_months_bulk,
        )

        r1 = _make_roster(
            db,
            roster_code="R1",
            scholarship_config_id=1,
            academic_year=113,
            period_label="2024-H1",
            roster_cycle=RosterCycle.SEMI_YEARLY,
            sub_type="nstc",
        )
        r2 = _make_roster(
            db,
            roster_code="R2",
            scholarship_config_id=1,
            academic_year=113,
            period_label="2024",
            roster_cycle=RosterCycle.YEARLY,
            sub_type="moe_1w",
        )
        _make_item(db, roster_id=r1.id, student_nycu_id="S001", application_id=1)
        _make_item(db, roster_id=r2.id, student_nycu_id="S001", application_id=1)
        _make_item(db, roster_id=r1.id, student_nycu_id="S002", application_id=2)

        bulk = calculate_received_months_bulk(db, ["S001", "S002"], scholarship_config_id=1)
        assert bulk["S001"] == calculate_received_months(db, "S001", scholarship_config_id=1)
        assert bulk["S002"] == calculate_received_months(db, "S002", scholarship_config_id=1)
        assert bulk["S001"] == 18  # 6 + 12
        assert bulk["S002"] == 6
