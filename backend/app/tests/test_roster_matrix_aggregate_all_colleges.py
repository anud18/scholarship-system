"""
Regression + contract tests: matrix-mode roster generation must include ALL
colleges' allocated students, not just the latest-finalized ranking.

Root cause was RosterService._get_eligible_applications: matrix mode with no
ranking_id picked ONE ranking via .order_by(finalized_at.desc()).first(), so a
multi-college distribution (one CollegeRanking per college) produced a roster
covering only the last-finalized college.

Assertions are on observable I/O (PaymentRoster.total_applications,
PaymentRosterItem rows) per the leaf-node-containment philosophy in
test_roster_service_generation.py. A yearly (semester=None) matrix config is
used so the period-based semester filter is skipped, isolating the
multi-college ranking aggregation under test.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from app.core.exceptions import RosterGenerationError
from app.models.application import Application
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.enums import QuotaManagementMode
from app.models.payment_roster import PaymentRosterItem, RosterCycle, RosterTriggerType
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType, SubTypeSelectionMode
from app.models.user import User, UserRole, UserType
from app.services.roster_service import RosterService

pytestmark = pytest.mark.integration

YEAR = 114
PERIOD = "114"  # yearly period label → no semester filter


@pytest.fixture
def patch_dependencies():
    """Patch RosterService collaborators so tests stay in-process (mirrors
    test_roster_service_generation.py). verify_student is never called because
    student_verification_enabled=False, but RosterService.__init__ constructs
    StudentVerificationService, and audit_service is invoked during generation."""
    with (
        patch("app.services.roster_service.StudentVerificationService") as svs,
        patch("app.services.roster_service.audit_service"),
    ):
        svs.return_value.verify_student.return_value = {"status": "verified", "verified": True, "data": {}}
        yield


def _admin(db_sync) -> User:
    u = User(
        nycu_id="matrix_admin",
        email="matrix_admin@nycu.edu.tw",
        name="Matrix Admin",
        role=UserRole.admin,
        user_type=UserType.employee,
    )
    db_sync.add(u)
    db_sync.commit()
    db_sync.refresh(u)
    return u


def _scholarship(db_sync) -> ScholarshipType:
    s = ScholarshipType(code="matrix_sch", name="Matrix Scholarship", description="x")
    db_sync.add(s)
    db_sync.commit()
    db_sync.refresh(s)
    return s


def _matrix_config(db_sync, scholarship) -> ScholarshipConfiguration:
    # semester=None ⇒ yearly ⇒ period-based semester filter skipped.
    c = ScholarshipConfiguration(
        scholarship_type_id=scholarship.id,
        config_code="MX-114-1",
        config_name="Matrix Config",
        academic_year=YEAR,
        semester=None,
        quota_management_mode=QuotaManagementMode.matrix_based,
        has_quota_limit=False,
        amount=50000,
    )
    db_sync.add(c)
    db_sync.commit()
    db_sync.refresh(c)
    return c


def _approved_app(db_sync, user, scholarship, config, *, std_code, sub_type) -> Application:
    a = Application(
        user_id=user.id,
        app_id=f"APP-{std_code}",
        scholarship_type_id=scholarship.id,
        scholarship_configuration_id=config.id,
        academic_year=YEAR,
        semester=None,
        status="approved",
        sub_type_selection_mode=SubTypeSelectionMode.single,
        scholarship_subtype_list=[],
        sub_scholarship_type=sub_type,
        student_data={"std_stdcode": std_code, "std_pid": f"A{std_code}", "std_cname": f"學生{std_code}"},
        submitted_form_data={"fields": {"postal_account": {"value": "0001234567"}}},
        agree_terms=True,
        amount=Decimal("50000"),
    )
    db_sync.add(a)
    db_sync.commit()
    db_sync.refresh(a)
    return a


def _ranking(db_sync, scholarship, college_code, *, finalized=True, executed=True) -> CollegeRanking:
    r = CollegeRanking(
        scholarship_type_id=scholarship.id,
        college_code=college_code,
        sub_type_code="default",
        academic_year=YEAR,
        semester=None,
        ranking_name=f"R-{college_code}",
        is_finalized=finalized,
        ranking_status="finalized" if finalized else "draft",
        distribution_executed=executed,
    )
    db_sync.add(r)
    db_sync.commit()
    db_sync.refresh(r)
    return r


def _alloc_item(db_sync, ranking, application, *, sub_type, allocated=True):
    it = CollegeRankingItem(
        ranking_id=ranking.id,
        application_id=application.id,
        rank_position=1,
        is_allocated=allocated,
        allocated_sub_type=sub_type if allocated else None,
        allocation_config_id=None,
        status="allocated" if allocated else "ranked",
    )
    db_sync.add(it)
    db_sync.commit()
    return it


def _generate(db_sync, config, admin, *, ranking_id=None, period=PERIOD):
    return RosterService(db_sync).generate_roster(
        scholarship_configuration_id=config.id,
        period_label=period,
        roster_cycle=RosterCycle.YEARLY,
        academic_year=YEAR,
        created_by_user_id=admin.id,
        trigger_type=RosterTriggerType.MANUAL,
        student_verification_enabled=False,
        ranking_id=ranking_id,
    )


def _item_numbers(db_sync, roster):
    rows = db_sync.query(PaymentRosterItem).filter(PaymentRosterItem.roster_id == roster.id).all()
    return rows


def test_no_ranking_id_aggregates_all_colleges(db_sync, patch_dependencies):
    admin = _admin(db_sync)
    sch = _scholarship(db_sync)
    cfg = _matrix_config(db_sync, sch)
    rA = _ranking(db_sync, sch, "A")
    rB = _ranking(db_sync, sch, "B")
    a1 = _approved_app(db_sync, admin, sch, cfg, std_code="A001", sub_type="nstc")
    a2 = _approved_app(db_sync, admin, sch, cfg, std_code="A002", sub_type="nstc")
    b1 = _approved_app(db_sync, admin, sch, cfg, std_code="B001", sub_type="nstc")
    _alloc_item(db_sync, rA, a1, sub_type="nstc")
    _alloc_item(db_sync, rA, a2, sub_type="nstc")
    _alloc_item(db_sync, rB, b1, sub_type="nstc")

    roster = _generate(db_sync, cfg, admin)

    assert roster.total_applications == 3
    nums = {i.student_number for i in _item_numbers(db_sync, roster)}
    assert nums == {"A001", "A002", "B001"}


def test_unallocated_students_excluded(db_sync, patch_dependencies):
    admin = _admin(db_sync)
    sch = _scholarship(db_sync)
    cfg = _matrix_config(db_sync, sch)
    rA = _ranking(db_sync, sch, "A")
    a1 = _approved_app(db_sync, admin, sch, cfg, std_code="A001", sub_type="nstc")
    a2 = _approved_app(db_sync, admin, sch, cfg, std_code="A002", sub_type="nstc")
    _alloc_item(db_sync, rA, a1, sub_type="nstc", allocated=True)
    _alloc_item(db_sync, rA, a2, sub_type="nstc", allocated=False)

    roster = _generate(db_sync, cfg, admin)

    assert roster.total_applications == 1
    nums = {i.student_number for i in _item_numbers(db_sync, roster)}
    assert nums == {"A001"}


def test_explicit_ranking_id_scopes_to_that_ranking(db_sync, patch_dependencies):
    admin = _admin(db_sync)
    sch = _scholarship(db_sync)
    cfg = _matrix_config(db_sync, sch)
    rA = _ranking(db_sync, sch, "A")
    rB = _ranking(db_sync, sch, "B")
    a1 = _approved_app(db_sync, admin, sch, cfg, std_code="A001", sub_type="nstc")
    b1 = _approved_app(db_sync, admin, sch, cfg, std_code="B001", sub_type="nstc")
    _alloc_item(db_sync, rA, a1, sub_type="nstc")
    _alloc_item(db_sync, rB, b1, sub_type="nstc")

    roster = _generate(db_sync, cfg, admin, ranking_id=rA.id)

    nums = {i.student_number for i in _item_numbers(db_sync, roster)}
    assert nums == {"A001"}


def test_single_ranking_unchanged(db_sync, patch_dependencies):
    admin = _admin(db_sync)
    sch = _scholarship(db_sync)
    cfg = _matrix_config(db_sync, sch)
    rA = _ranking(db_sync, sch, "A")
    a1 = _approved_app(db_sync, admin, sch, cfg, std_code="A001", sub_type="nstc")
    a2 = _approved_app(db_sync, admin, sch, cfg, std_code="A002", sub_type="nstc")
    _alloc_item(db_sync, rA, a1, sub_type="nstc")
    _alloc_item(db_sync, rA, a2, sub_type="nstc")

    roster = _generate(db_sync, cfg, admin)

    nums = {i.student_number for i in _item_numbers(db_sync, roster)}
    assert nums == {"A001", "A002"}


def test_aggregation_preserves_per_student_subtype(db_sync, patch_dependencies):
    admin = _admin(db_sync)
    sch = _scholarship(db_sync)
    cfg = _matrix_config(db_sync, sch)
    rA = _ranking(db_sync, sch, "A")
    rB = _ranking(db_sync, sch, "B")
    a1 = _approved_app(db_sync, admin, sch, cfg, std_code="A001", sub_type="nstc")
    b1 = _approved_app(db_sync, admin, sch, cfg, std_code="B001", sub_type="moe_1w")
    _alloc_item(db_sync, rA, a1, sub_type="nstc")
    _alloc_item(db_sync, rB, b1, sub_type="moe_1w")

    roster = _generate(db_sync, cfg, admin)

    by_num = {i.student_number: i for i in _item_numbers(db_sync, roster)}
    assert by_num["A001"].scholarship_subtype == "nstc"
    assert by_num["B001"].scholarship_subtype == "moe_1w"


def test_no_executed_ranking_raises(db_sync, patch_dependencies):
    admin = _admin(db_sync)
    sch = _scholarship(db_sync)
    cfg = _matrix_config(db_sync, sch)
    # No rankings created at all.
    with pytest.raises(RosterGenerationError, match="找不到已執行分發的排名"):
        _generate(db_sync, cfg, admin)
