"""
Contract tests for RosterService.

Locks down the public surface of `app/services/roster_service.py` (1727 LOC,
zero behavioral coverage prior to Phase 3 of the test-surface-hardening plan).
Tests assert on **observable I/O only** — rows in `payment_rosters` /
`payment_roster_items`, return-value shape, audit-emit call counts — never
on private helpers. This is leaf-node containment: the AI can refactor
internals freely so long as the externally-observable contract holds.

Notes:
- RosterService takes a *sync* `Session` (see roster_service.py:36), so all
  tests use the `db_sync` fixture from conftest.py.
- StudentVerificationService is patched at module level so no SIS API calls
  are made.
- audit_service callables are patched to no-ops; their behavior is covered
  separately by Phase 5's audit-log contract job.
- ScholarshipConfiguration / Application rows are built directly via
  `db_sync` because the existing fixtures (test_user, test_scholarship,
  test_application) are *async*, and mixing await with a sync session
  creates ordering hazards.
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest

from app.core.exceptions import RosterAlreadyExistsError, RosterGenerationError, RosterLockedError
from app.models.application import Application
from app.models.enums import QuotaManagementMode, Semester
from app.models.scholarship import SubTypeSelectionMode
from app.models.payment_roster import (
    PaymentRoster,
    PaymentRosterItem,
    RosterCycle,
    RosterStatus,
    RosterTriggerType,
)
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.services.roster_service import RosterService

# Module-level marks: these are integration-style (real session, real models).
pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Test data builders
# ---------------------------------------------------------------------------


def _make_admin(db_sync, nycu_id: str = "rosteradmin") -> User:
    user = User(
        nycu_id=nycu_id,
        name="Roster Admin",
        email=f"{nycu_id}@university.edu",
        user_type=UserType.employee,
        role=UserRole.admin,
    )
    db_sync.add(user)
    db_sync.commit()
    db_sync.refresh(user)
    return user


def _make_scholarship(db_sync, code: str = "roster_test") -> ScholarshipType:
    s = ScholarshipType(
        code=code,
        name="Roster Contract Test",
        description="Phase 3 fixture",
    )
    db_sync.add(s)
    db_sync.commit()
    db_sync.refresh(s)
    return s


def _make_config(
    db_sync,
    scholarship_type: ScholarshipType,
    *,
    config_code: str = "RT-113-1",
    quota_mode: QuotaManagementMode = QuotaManagementMode.simple,
) -> ScholarshipConfiguration:
    c = ScholarshipConfiguration(
        scholarship_type_id=scholarship_type.id,
        config_code=config_code,
        config_name="Roster Contract Test Config",
        academic_year=113,
        semester=Semester.first,
        quota_management_mode=quota_mode,
        has_quota_limit=False,
        amount=50000,
    )
    db_sync.add(c)
    db_sync.commit()
    db_sync.refresh(c)
    return c


def _make_approved_application(
    db_sync,
    user: User,
    scholarship: ScholarshipType,
    config: ScholarshipConfiguration,
    *,
    app_id: str = "APP-113-1-00001",
    student_id: str = "112550001",
    national_id: str = "A123456789",
    student_name: str = "羅斯特同學",
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
        student_data={"std_stdcode": student_id, "std_pid": national_id, "std_cname": student_name},
        submitted_form_data={},
        agree_terms=True,
        amount=Decimal("50000"),
    )
    db_sync.add(a)
    db_sync.commit()
    db_sync.refresh(a)
    return a


# ---------------------------------------------------------------------------
# Fixtures: dependency mocks
# ---------------------------------------------------------------------------


@pytest.fixture
def patch_dependencies():
    """
    Patch RosterService's external collaborators so tests stay in-process:
    - StudentVerificationService is replaced with a Mock returning verified.
    - audit_service.log_* callables become no-ops; we still assert call counts.
    """
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


# ---------------------------------------------------------------------------
# Public surface contract
# ---------------------------------------------------------------------------


class TestRosterServiceGenerate:
    """generate_roster — happy path + idempotency + matrix-mode validation."""

    @pytest.mark.smoke
    def test_generate_roster_happy_path(self, db_sync, patch_dependencies):
        """
        CONTRACT: generating a roster for an active config with one approved
        application produces a PaymentRoster row, a PaymentRosterItem row,
        and a single roster_creation audit emit.
        """
        admin = _make_admin(db_sync)
        scholarship = _make_scholarship(db_sync)
        config = _make_config(db_sync, scholarship)
        _make_approved_application(db_sync, admin, scholarship, config)

        svc = RosterService(db_sync)
        roster = svc.generate_roster(
            scholarship_configuration_id=config.id,
            period_label="2024-01",
            roster_cycle=RosterCycle.MONTHLY,
            academic_year=113,
            created_by_user_id=admin.id,
            trigger_type=RosterTriggerType.MANUAL,
            student_verification_enabled=False,
        )

        assert roster.id is not None
        assert roster.scholarship_configuration_id == config.id
        assert roster.period_label == "2024-01"
        assert roster.academic_year == 113
        # generate_roster() intentionally does not commit or set COMPLETED —
        # the caller (API endpoint) is responsible for the final commit and
        # status flip. The service returns PROCESSING.
        assert roster.status == RosterStatus.PROCESSING
        assert roster.total_applications == 1

        items = db_sync.query(PaymentRosterItem).filter_by(roster_id=roster.id).all()
        assert len(items) == 1

        audit = patch_dependencies["audit"]
        assert audit.log_roster_creation.call_count == 1

    @pytest.mark.smoke
    def test_generate_roster_raises_on_duplicate_without_force(self, db_sync, patch_dependencies):
        """
        CONTRACT: regenerating the same (config_id, period_label) without
        force_regenerate=True raises RosterAlreadyExistsError. (Idempotency.)
        """
        admin = _make_admin(db_sync)
        scholarship = _make_scholarship(db_sync)
        config = _make_config(db_sync, scholarship)
        _make_approved_application(db_sync, admin, scholarship, config)

        svc = RosterService(db_sync)
        svc.generate_roster(
            scholarship_configuration_id=config.id,
            period_label="2024-01",
            roster_cycle=RosterCycle.MONTHLY,
            academic_year=113,
            created_by_user_id=admin.id,
            trigger_type=RosterTriggerType.MANUAL,
            student_verification_enabled=False,
        )

        # generate_roster() wraps all internal exceptions (including
        # RosterAlreadyExistsError) in RosterGenerationError before surfacing.
        with pytest.raises(RosterGenerationError):
            svc.generate_roster(
                scholarship_configuration_id=config.id,
                period_label="2024-01",
                roster_cycle=RosterCycle.MONTHLY,
                academic_year=113,
                created_by_user_id=admin.id,
                trigger_type=RosterTriggerType.MANUAL,
                student_verification_enabled=False,
            )

    def test_generate_roster_force_regenerate_clears_old_items(self, db_sync, patch_dependencies):
        """
        CONTRACT: force_regenerate=True on an existing roster wipes the prior
        PaymentRosterItem rows (roster_service.py:152) and re-runs against
        current applications.
        """
        admin = _make_admin(db_sync)
        scholarship = _make_scholarship(db_sync)
        config = _make_config(db_sync, scholarship)
        app = _make_approved_application(db_sync, admin, scholarship, config)

        svc = RosterService(db_sync)
        first = svc.generate_roster(
            scholarship_configuration_id=config.id,
            period_label="2024-01",
            roster_cycle=RosterCycle.MONTHLY,
            academic_year=113,
            created_by_user_id=admin.id,
            trigger_type=RosterTriggerType.MANUAL,
            student_verification_enabled=False,
        )
        first_id = first.id

        # Withdraw the application; the regenerated roster must not include it.
        app.status = "withdrawn"
        db_sync.commit()

        regenerated = svc.generate_roster(
            scholarship_configuration_id=config.id,
            period_label="2024-01",
            roster_cycle=RosterCycle.MONTHLY,
            academic_year=113,
            created_by_user_id=admin.id,
            trigger_type=RosterTriggerType.MANUAL,
            student_verification_enabled=False,
            force_regenerate=True,
        )

        assert regenerated.id == first_id
        items = db_sync.query(PaymentRosterItem).filter_by(roster_id=first_id).all()
        assert items == []

    def test_generate_roster_locked_blocks_regeneration(self, db_sync, patch_dependencies):
        """
        CONTRACT: regenerating a locked roster raises RosterLockedError even
        with force_regenerate=True (roster_service.py:90).
        """
        admin = _make_admin(db_sync)
        scholarship = _make_scholarship(db_sync)
        config = _make_config(db_sync, scholarship)
        _make_approved_application(db_sync, admin, scholarship, config)

        svc = RosterService(db_sync)
        roster = svc.generate_roster(
            scholarship_configuration_id=config.id,
            period_label="2024-01",
            roster_cycle=RosterCycle.MONTHLY,
            academic_year=113,
            created_by_user_id=admin.id,
            trigger_type=RosterTriggerType.MANUAL,
            student_verification_enabled=False,
        )
        svc.lock_roster(roster.id, locked_by_user_id=admin.id)

        with pytest.raises(RosterLockedError):
            svc.generate_roster(
                scholarship_configuration_id=config.id,
                period_label="2024-01",
                roster_cycle=RosterCycle.MONTHLY,
                academic_year=113,
                created_by_user_id=admin.id,
                trigger_type=RosterTriggerType.MANUAL,
                student_verification_enabled=False,
                force_regenerate=True,
            )

    def test_generate_roster_matrix_mode_with_unexecuted_ranking_raises(self, db_sync, patch_dependencies):
        """
        CONTRACT: under matrix_based quota mode, supplying a ranking_id whose
        distribution has not been executed raises ValueError
        (roster_service.py:113).
        """
        from app.models.college_review import CollegeRanking

        admin = _make_admin(db_sync)
        scholarship = _make_scholarship(db_sync)
        config = _make_config(
            db_sync,
            scholarship,
            config_code="RT-MATRIX-113-1",
            quota_mode=QuotaManagementMode.matrix_based,
        )
        ranking = CollegeRanking(
            scholarship_configuration_id=config.id,
            academic_year=113,
            semester=Semester.first,
            distribution_executed=False,
        )
        db_sync.add(ranking)
        db_sync.commit()
        db_sync.refresh(ranking)

        svc = RosterService(db_sync)
        with pytest.raises(ValueError, match="尚未執行分發"):
            svc.generate_roster(
                scholarship_configuration_id=config.id,
                period_label="2024-01",
                roster_cycle=RosterCycle.MONTHLY,
                academic_year=113,
                created_by_user_id=admin.id,
                trigger_type=RosterTriggerType.MANUAL,
                student_verification_enabled=False,
                ranking_id=ranking.id,
            )


class TestRosterServiceLifecycle:
    """lock_roster / unlock_roster — observable state + audit emit."""

    @pytest.mark.smoke
    def test_lock_roster_flips_state_and_emits_audit(self, db_sync, patch_dependencies):
        admin = _make_admin(db_sync)
        scholarship = _make_scholarship(db_sync)
        config = _make_config(db_sync, scholarship)
        _make_approved_application(db_sync, admin, scholarship, config)

        svc = RosterService(db_sync)
        roster = svc.generate_roster(
            scholarship_configuration_id=config.id,
            period_label="2024-02",
            roster_cycle=RosterCycle.MONTHLY,
            academic_year=113,
            created_by_user_id=admin.id,
            trigger_type=RosterTriggerType.MANUAL,
            student_verification_enabled=False,
        )

        patch_dependencies["audit"].reset_mock()
        locked = svc.lock_roster(roster.id, locked_by_user_id=admin.id)

        assert locked.is_locked
        assert locked.locked_at is not None
        assert locked.locked_by == admin.id
        assert patch_dependencies["audit"].log_roster_lock.call_count == 1

    def test_unlock_roster_inverts_lock_state(self, db_sync, patch_dependencies):
        admin = _make_admin(db_sync)
        scholarship = _make_scholarship(db_sync)
        config = _make_config(db_sync, scholarship)
        _make_approved_application(db_sync, admin, scholarship, config)

        svc = RosterService(db_sync)
        roster = svc.generate_roster(
            scholarship_configuration_id=config.id,
            period_label="2024-03",
            roster_cycle=RosterCycle.MONTHLY,
            academic_year=113,
            created_by_user_id=admin.id,
            trigger_type=RosterTriggerType.MANUAL,
            student_verification_enabled=False,
        )
        svc.lock_roster(roster.id, locked_by_user_id=admin.id)

        unlocked = svc.unlock_roster(roster.id, unlocked_by_user_id=admin.id)

        assert not unlocked.is_locked
        assert unlocked.locked_at is None
        assert unlocked.locked_by is None
        assert unlocked.status == RosterStatus.COMPLETED


class TestRosterServiceLookup:
    """get_roster_by_* — pure read paths used widely by API endpoints."""

    def test_get_roster_by_period(self, db_sync, patch_dependencies):
        admin = _make_admin(db_sync)
        scholarship = _make_scholarship(db_sync)
        config = _make_config(db_sync, scholarship)
        _make_approved_application(db_sync, admin, scholarship, config)

        svc = RosterService(db_sync)
        created = svc.generate_roster(
            scholarship_configuration_id=config.id,
            period_label="2024-04",
            roster_cycle=RosterCycle.MONTHLY,
            academic_year=113,
            created_by_user_id=admin.id,
            trigger_type=RosterTriggerType.MANUAL,
            student_verification_enabled=False,
        )

        assert svc.get_roster_by_id(created.id).id == created.id
        assert svc.get_roster_by_code(created.roster_code).id == created.id
        assert svc.get_roster_by_period(config.id, "2024-04").id == created.id
        assert svc.get_roster_by_period(config.id, "nonexistent") is None
