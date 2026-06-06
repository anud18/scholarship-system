"""
Idempotency + TOCTOU/concurrency tests for RosterService.generate_roster.

Issue #124 §3 — even with the Redis SET-NX-EX mutex around
POST /api/v1/payment-rosters/generate, two callers can still race:

  1. Sequential idempotency: a second `generate_roster(...)` call for the
     same (scholarship_configuration_id, period_label) must not silently
     create a duplicate row — it must surface as
     `RosterAlreadyExistsError` (wrapped as `RosterGenerationError` by the
     service-layer outer try/except at roster_service.py:413-417, then
     unwrapped to 409 by the endpoint).
  2. TOCTOU: the in-process `check_roster_exists` precheck is *not* the
     authority — the authoritative guard is the functional unique index
     `uq_roster_scholarship_period_alloc` added by the
     `add_roster_sub_type_001` migration. If two workers both pass the
     precheck and one inserts first, the second must observe the DB-level
     `IntegrityError` and translate it into the same domain exception.

Why this file *simulates* TOCTOU instead of running real threads:
- The test DB is SQLite, which can't model the Postgres functional unique
  index from the migration (the index lives only in the migration; the
  model's `__table_args__ = ()` so SQLAlchemy never replays it on
  Base.metadata.create_all). We patch `check_roster_exists` to return None
  while pre-creating the conflicting row, then assert the resulting
  exception. asyncio.gather-style real concurrency is fragile in test
  environments and not actually load-bearing for this contract.

HTTP-layer tests cover only the **422 missing body** path because:
- The `_generate_payment_roster_inner` body does real DB work (eligible-
  application filtering, audit emits, Excel export), Redis lock acquisition
  (`with_lock_sync`), and `commit()` on a sync session that conftest.py
  doesn't override cleanly. Standing up the full mock surface to verify
  409 at the HTTP layer reproduces what the service-layer tests already
  prove. Per the issue spec, leaving the happy-path / 409 endpoint tests
  to the service layer is explicitly permitted.
"""

from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import RosterAlreadyExistsError, RosterGenerationError
from app.models.application import Application
from app.models.enums import QuotaManagementMode, Semester
from app.models.payment_roster import (
    PaymentRoster,
    PaymentRosterItem,
    RosterCycle,
    RosterStatus,
    RosterTriggerType,
)
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType, SubTypeSelectionMode
from app.models.user import User, UserRole, UserType
from app.services.roster_service import RosterService

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Builder helpers (mirrors test_roster_service_generation.py — kept local so
# this file stays self-contained and refactors there don't ripple here).
# ---------------------------------------------------------------------------


def _make_admin(db_sync, nycu_id: str = "rosterconcurrencyadmin") -> User:
    user = User(
        nycu_id=nycu_id,
        name="Concurrency Admin",
        email=f"{nycu_id}@university.edu",
        user_type=UserType.employee,
        role=UserRole.admin,
    )
    db_sync.add(user)
    db_sync.commit()
    db_sync.refresh(user)
    return user


def _make_scholarship(db_sync, code: str = "roster_concurrency_test") -> ScholarshipType:
    s = ScholarshipType(
        code=code,
        name="Roster Concurrency Test",
        description="Issue #124 §3 fixture",
    )
    db_sync.add(s)
    db_sync.commit()
    db_sync.refresh(s)
    return s


def _make_config(
    db_sync,
    scholarship_type: ScholarshipType,
    *,
    config_code: str = "RC-113-1",
    academic_year: int = 113,
    semester: Semester = Semester.first,
    quota_mode: QuotaManagementMode = QuotaManagementMode.simple,
) -> ScholarshipConfiguration:
    c = ScholarshipConfiguration(
        scholarship_type_id=scholarship_type.id,
        config_code=config_code,
        config_name=f"Roster Concurrency Config {config_code}",
        academic_year=academic_year,
        semester=semester,
        quota_management_mode=quota_mode,
        has_quota_limit=False,
        amount=50000,
    )
    db_sync.add(c)
    db_sync.commit()
    db_sync.refresh(c)
    return c


def _make_application(
    db_sync,
    user: User,
    scholarship: ScholarshipType,
    config: ScholarshipConfiguration,
    *,
    app_id: str = "APP-113-1-00001",
    student_id: str = "112550001",
    student_name: str = "羅斯特同學",
    national_id: str = "A123456789",
) -> Application:
    a = Application(
        user_id=user.id,
        scholarship_type_id=scholarship.id,
        scholarship_configuration_id=config.id,
        scholarship_subtype_list=[],
        sub_type_selection_mode=SubTypeSelectionMode.single,
        status="approved",
        app_id=app_id,
        academic_year=113,
        semester="first",
        student_data={"std_stdcode": student_id, "std_cname": student_name, "std_pid": national_id},
        submitted_form_data={},
        agree_terms=True,
        amount=Decimal("50000"),
    )
    db_sync.add(a)
    db_sync.commit()
    db_sync.refresh(a)
    return a


# ---------------------------------------------------------------------------
# Fixtures: dependency mocks (same pattern as test_roster_service_generation)
# ---------------------------------------------------------------------------


@pytest.fixture
def patch_dependencies():
    """Replace SIS verification + audit emits with no-ops."""
    with (
        patch("app.services.roster_service.StudentVerificationService") as svs,
        patch("app.services.roster_service.audit_service") as audit,
    ):
        svs.return_value.verify_student.return_value = {
            "status": "verified",
            "verified": True,
            "data": {},
        }
        yield {"student_verification": svs, "audit": audit}


# ===========================================================================
# Class 1: TestSequentialDuplicate
#
# The "double-click" scenario: the same caller (or two callers post-Redis-
# lock-release) invokes generate_roster twice. The service must reject the
# second call without producing a duplicate row.
# ===========================================================================


class TestSequentialDuplicate:
    """Sequential idempotency — `check_roster_exists` precheck path."""

    def test_generate_twice_same_period_raises_already_exists(self, db_sync, patch_dependencies):
        """
        CONTRACT: a second `generate_roster` for the same
        (scholarship_configuration_id, period_label) raises
        `RosterGenerationError` (which wraps the inner
        `RosterAlreadyExistsError`).

        Why we assert on `RosterGenerationError` and inspect `__cause__`:
        roster_service.py:413-417 wraps every internal raise inside an outer
        try/except — see also the matching assertion in
        test_roster_service_generation.py:227-238. The inner cause must be
        `RosterAlreadyExistsError` so the endpoint can still translate to
        409 (payment_rosters.py:156-160). If a future refactor swallows the
        cause, this test fails and the 409 mapping silently breaks.
        """
        admin = _make_admin(db_sync)
        scholarship = _make_scholarship(db_sync)
        config = _make_config(db_sync, scholarship)
        _make_application(db_sync, admin, scholarship, config)

        svc = RosterService(db_sync)

        # First call: must succeed.
        first = svc.generate_roster(
            scholarship_configuration_id=config.id,
            period_label="2025-01",
            roster_cycle=RosterCycle.MONTHLY,
            academic_year=113,
            created_by_user_id=admin.id,
            trigger_type=RosterTriggerType.MANUAL,
            student_verification_enabled=False,
        )
        assert first.id is not None
        db_sync.commit()

        # Second call: must raise, with the inner cause preserved so the
        # API layer can map it to 409.
        with pytest.raises(RosterGenerationError) as exc_info:
            svc.generate_roster(
                scholarship_configuration_id=config.id,
                period_label="2025-01",
                roster_cycle=RosterCycle.MONTHLY,
                academic_year=113,
                created_by_user_id=admin.id,
                trigger_type=RosterTriggerType.MANUAL,
                student_verification_enabled=False,
            )
        assert isinstance(exc_info.value.__cause__, RosterAlreadyExistsError), (
            "RosterGenerationError must preserve RosterAlreadyExistsError as "
            "__cause__ so payment_rosters.py:156 can re-translate to 409. "
            f"Got cause: {type(exc_info.value.__cause__).__name__}"
        )

        # Invariant: still exactly one roster row.
        rosters = (
            db_sync.query(PaymentRoster).filter_by(scholarship_configuration_id=config.id, period_label="2025-01").all()
        )
        assert len(rosters) == 1

    def test_generate_twice_force_regenerate_succeeds(self, db_sync, patch_dependencies):
        """
        CONTRACT: `force_regenerate=True` on the second call updates the
        existing roster (same id) instead of raising. Items from the
        previous run are wiped (roster_service.py:152-156).
        """
        admin = _make_admin(db_sync)
        scholarship = _make_scholarship(db_sync)
        config = _make_config(db_sync, scholarship)
        _make_application(db_sync, admin, scholarship, config)

        svc = RosterService(db_sync)
        first = svc.generate_roster(
            scholarship_configuration_id=config.id,
            period_label="2025-01",
            roster_cycle=RosterCycle.MONTHLY,
            academic_year=113,
            created_by_user_id=admin.id,
            trigger_type=RosterTriggerType.MANUAL,
            student_verification_enabled=False,
        )
        first_id = first.id
        db_sync.commit()

        regenerated = svc.generate_roster(
            scholarship_configuration_id=config.id,
            period_label="2025-01",
            roster_cycle=RosterCycle.MONTHLY,
            academic_year=113,
            created_by_user_id=admin.id,
            trigger_type=RosterTriggerType.MANUAL,
            student_verification_enabled=False,
            force_regenerate=True,
        )

        # Same row reused, not a second insert.
        assert regenerated.id == first_id
        rosters = (
            db_sync.query(PaymentRoster).filter_by(scholarship_configuration_id=config.id, period_label="2025-01").all()
        )
        assert len(rosters) == 1

    def test_generate_different_periods_both_succeed(self, db_sync, patch_dependencies):
        """
        CONTRACT: idempotency key is (config_id, period_label) — different
        period_labels for the same config are independent rosters. Without
        this, you couldn't generate Jan and Feb monthly rosters in the same
        academic year.
        """
        admin = _make_admin(db_sync)
        scholarship = _make_scholarship(db_sync)
        config = _make_config(db_sync, scholarship)
        _make_application(db_sync, admin, scholarship, config)

        svc = RosterService(db_sync)
        r1 = svc.generate_roster(
            scholarship_configuration_id=config.id,
            period_label="2025-01",
            roster_cycle=RosterCycle.MONTHLY,
            academic_year=113,
            created_by_user_id=admin.id,
            trigger_type=RosterTriggerType.MANUAL,
            student_verification_enabled=False,
        )
        db_sync.commit()
        r2 = svc.generate_roster(
            scholarship_configuration_id=config.id,
            period_label="2025-02",
            roster_cycle=RosterCycle.MONTHLY,
            academic_year=113,
            created_by_user_id=admin.id,
            trigger_type=RosterTriggerType.MANUAL,
            student_verification_enabled=False,
        )
        db_sync.commit()

        assert r1.id != r2.id
        rosters = db_sync.query(PaymentRoster).filter_by(scholarship_configuration_id=config.id).all()
        assert len(rosters) == 2
        assert {r.period_label for r in rosters} == {"2025-01", "2025-02"}

    def test_generate_different_configs_both_succeed(self, db_sync, patch_dependencies):
        """
        CONTRACT: idempotency key includes config_id — same period_label
        across two distinct configs (e.g. two scholarships running parallel
        monthly cycles) must both succeed.
        """
        admin = _make_admin(db_sync)
        scholarship = _make_scholarship(db_sync)
        # Vary academic_year so the (scholarship_type_id, academic_year,
        # semester) uniqueness on ScholarshipConfiguration doesn't trip.
        config_a = _make_config(db_sync, scholarship, config_code="RC-113-1-A", academic_year=113)
        config_b = _make_config(db_sync, scholarship, config_code="RC-114-1-B", academic_year=114)
        _make_application(db_sync, admin, scholarship, config_a, app_id="APP-113-1-00001")

        svc = RosterService(db_sync)
        r1 = svc.generate_roster(
            scholarship_configuration_id=config_a.id,
            period_label="2025-01",
            roster_cycle=RosterCycle.MONTHLY,
            academic_year=113,
            created_by_user_id=admin.id,
            trigger_type=RosterTriggerType.MANUAL,
            student_verification_enabled=False,
        )
        db_sync.commit()
        r2 = svc.generate_roster(
            scholarship_configuration_id=config_b.id,
            period_label="2025-01",
            roster_cycle=RosterCycle.MONTHLY,
            academic_year=114,
            created_by_user_id=admin.id,
            trigger_type=RosterTriggerType.MANUAL,
            student_verification_enabled=False,
        )
        db_sync.commit()

        assert r1.id != r2.id
        assert r1.scholarship_configuration_id != r2.scholarship_configuration_id
        rosters = db_sync.query(PaymentRoster).filter_by(period_label="2025-01").all()
        assert len(rosters) == 2


# ===========================================================================
# Class 2: TestTOCTOUSimulation
#
# Simulates the race where two callers both pass `check_roster_exists` (the
# precheck returns None because the other worker hasn't committed yet) and
# the second INSERT collides with the DB's unique index. Real concurrent
# threads aren't used because the test DB is SQLite (no Postgres functional
# index) and asyncio.gather is fragile in tests — patching the precheck and
# raising IntegrityError on flush models the exact path the production code
# must survive.
# ===========================================================================


class TestTOCTOUSimulation:
    """Simulate the precheck-passes-but-INSERT-collides race."""

    def test_integrity_error_raises_roster_generation_error(self, db_sync, patch_dependencies):
        """
        CONTRACT: when `check_roster_exists` reports no conflict but the
        subsequent INSERT fails with `IntegrityError` (the migration's
        `uq_roster_scholarship_period_alloc` unique index firing), the
        service surfaces a `RosterGenerationError` (the outer try/except at
        roster_service.py:413-417). The DB invariant — only one roster per
        (config_id, period_label) — must hold after the failed attempt.

        We pre-create the conflicting row directly, then patch
        `check_roster_exists` to lie about it. The service still attempts
        the INSERT; we patch `db_sync.flush` to raise IntegrityError on the
        first call to model the unique-index trigger.
        """
        admin = _make_admin(db_sync)
        scholarship = _make_scholarship(db_sync)
        config = _make_config(db_sync, scholarship)
        _make_application(db_sync, admin, scholarship, config)

        # Pre-create the row that "another worker" would have inserted.
        # This is the row that should survive at the end of the test.
        existing = PaymentRoster(
            roster_code="ROSTER-113-2025-01-RC-113-1",
            scholarship_configuration_id=config.id,
            period_label="2025-01",
            academic_year=113,
            roster_cycle=RosterCycle.MONTHLY,
            status=RosterStatus.COMPLETED,
            trigger_type=RosterTriggerType.MANUAL,
            created_by=admin.id,
        )
        db_sync.add(existing)
        db_sync.commit()
        existing_id = existing.id

        svc = RosterService(db_sync)

        # Simulate the lying precheck: pretend no existing row found.
        # SQLite has no unique index (migration-only), so we also need to
        # make flush() raise IntegrityError to model the index trip that
        # would happen on Postgres.
        original_flush = db_sync.flush
        flush_calls = {"count": 0}

        def raise_on_first_flush(*args, **kwargs):
            flush_calls["count"] += 1
            if flush_calls["count"] == 1:
                raise IntegrityError(
                    statement="INSERT INTO payment_rosters ...",
                    params={},
                    orig=Exception(
                        "duplicate key value violates unique constraint " '"uq_roster_scholarship_period_alloc"'
                    ),
                )
            return original_flush(*args, **kwargs)

        with patch.object(svc, "check_roster_exists", return_value=None):
            with patch.object(db_sync, "flush", side_effect=raise_on_first_flush):
                with pytest.raises(RosterGenerationError) as exc_info:
                    svc.generate_roster(
                        scholarship_configuration_id=config.id,
                        period_label="2025-01",
                        roster_cycle=RosterCycle.MONTHLY,
                        academic_year=113,
                        created_by_user_id=admin.id,
                        trigger_type=RosterTriggerType.MANUAL,
                        student_verification_enabled=False,
                    )

        # The wrapped cause must be IntegrityError so callers (or future
        # endpoint logic) can distinguish DB-level collisions from other
        # generation failures.
        assert isinstance(exc_info.value.__cause__, IntegrityError), (
            "RosterGenerationError must preserve IntegrityError as __cause__ "
            "so the DB-level unique-index trip is observable. "
            f"Got cause: {type(exc_info.value.__cause__).__name__}"
        )

        # Rollback the failed transaction so the SELECT below sees committed
        # state (the IntegrityError leaves the session in an unusable state).
        db_sync.rollback()

        # The key invariant: only ONE roster exists for the contested
        # (config_id, period_label) tuple — the pre-existing one.
        rosters = (
            db_sync.query(PaymentRoster).filter_by(scholarship_configuration_id=config.id, period_label="2025-01").all()
        )
        assert len(rosters) == 1
        assert rosters[0].id == existing_id


# ===========================================================================
# Class 3: TestApiDuplicateReturns409
#
# Only the request-validation path (422) is covered here because the full
# happy path requires Redis + sync DB session juggling that conftest.py
# doesn't wire up. The 409-on-duplicate behavior is covered structurally by
# TestSequentialDuplicate above (which asserts the `__cause__` invariant the
# endpoint relies on at payment_rosters.py:156-160).
# ===========================================================================


def _make_mock_admin() -> Mock:
    u = Mock(spec=User)
    u.id = 1
    u.role = UserRole.admin
    u.email = "admin@nycu.edu.tw"
    u.name = "Mock Admin"
    u.has_role = lambda role: role == UserRole.admin
    u.is_admin = lambda: True
    u.is_super_admin = lambda: False
    return u


@pytest_asyncio.fixture
async def client_admin(db, client: AsyncClient):
    """
    AsyncClient with admin `get_current_user` override. The endpoint at
    payment_rosters.py:262 uses `get_current_user` (not
    `get_current_admin_user`) — role is enforced manually via
    `check_user_roles` on line 278.
    """
    from app.core.deps import get_current_user
    from app.core.deps import get_db as core_get_db
    from app.main import app

    mock_admin = _make_mock_admin()

    async def override_user():
        return mock_admin

    async def override_db():
        yield db

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[core_get_db] = override_db
    yield client
    app.dependency_overrides.clear()


class TestApiDuplicateReturns409:
    """HTTP-layer validation contract for POST /payment-rosters/generate."""

    @pytest.mark.asyncio
    async def test_generate_endpoint_missing_body_returns_422(self, client_admin):
        """
        CONTRACT: FastAPI's body validation rejects an empty POST body with
        422 *before* the endpoint code (and the Redis lock) runs. This
        guards against a regression where someone marks RosterCreateRequest
        fields Optional and accidentally allows a partial-body invocation
        that then crashes deep inside the service.

        Note: 422 fires before the auth dep too (FastAPI parses the body
        as the first dependency), so this test doesn't depend on
        the auth override behaving correctly.
        """
        resp = await client_admin.post("/api/v1/payment-rosters/generate")
        assert resp.status_code == 422
