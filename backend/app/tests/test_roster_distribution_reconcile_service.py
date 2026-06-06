"""Pin: get_distribution_diff_for_roster computes the allocated-but-missing
(to_add) and in-roster-but-unallocated (to_remove) sets by mirroring
generate_rosters_from_distribution grouping; reconcile_roster applies a
validated, server-re-derived selection, recomputes totals, sets excel_stale,
and audits — on COMPLETED and LOCKED rosters."""

import pytest

from app.core.exceptions import RosterLockedError
from app.models.application import Application, ApplicationStatus
from app.models.audit_log import AuditLog
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.payment_roster import (
    PaymentRoster,
    PaymentRosterItem,
    RosterCycle,
    RosterStatus,
    RosterTriggerType,
)
from app.models.scholarship import (
    ScholarshipConfiguration,
    ScholarshipType,
    SubTypeSelectionMode,
)
from app.models.user import User, UserRole, UserType
from app.services.roster_service import RosterService


def _admin(db_sync, nycu_id="reconcile_admin"):
    u = User(
        nycu_id=nycu_id,
        email=f"{nycu_id}@nycu.edu.tw",
        name="Reconcile Admin",
        role=UserRole.admin,
        user_type=UserType.employee,
    )
    db_sync.add(u)
    db_sync.flush()
    return u


def _student(db_sync, nycu_id):
    u = User(
        nycu_id=nycu_id,
        email=f"{nycu_id}@nycu.edu.tw",
        name=f"Student {nycu_id}",
        role=UserRole.student,
        user_type=UserType.student,
    )
    db_sync.add(u)
    db_sync.flush()
    return u


def _scholarship(db_sync, code="reconcile_sch"):
    s = ScholarshipType(code=code, name="Reconcile Scholarship", description="x")
    db_sync.add(s)
    db_sync.flush()
    return s


def _config(db_sync, scholarship, *, academic_year=114):
    c = ScholarshipConfiguration(
        scholarship_type_id=scholarship.id,
        config_code=f"RC-{academic_year}-1",
        config_name="Reconcile Config",
        academic_year=academic_year,
        semester="first",
        amount=50000,
        has_quota_limit=False,
    )
    db_sync.add(c)
    db_sync.flush()
    return c


def _application(db_sync, user, scholarship, config, *, app_id, std_code, sub_type="nstc"):
    a = Application(
        user_id=user.id,
        app_id=app_id,
        scholarship_type_id=scholarship.id,
        scholarship_configuration_id=config.id,
        academic_year=114,
        semester="first",
        status=ApplicationStatus.approved,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        scholarship_subtype_list=[],
        sub_scholarship_type=sub_type,
        student_data={
            "std_stdcode": std_code,
            "std_pid": f"A{std_code}",
            "std_cname": f"學生{std_code}",
            "trm_depname": "教育博",
            "trm_academyname": "人社院",
        },
        submitted_form_data={"fields": {"postal_account": {"value": "0001234567"}}},
        amount=50000,
    )
    db_sync.add(a)
    db_sync.flush()
    return a


def _ranking(db_sync, scholarship, *, sub_type="nstc"):
    r = CollegeRanking(
        scholarship_type_id=scholarship.id,
        sub_type_code=sub_type,
        academic_year=114,
        semester="first",
        ranking_name="R",
        is_finalized=True,
        ranking_status="finalized",
        distribution_executed=True,
    )
    db_sync.add(r)
    db_sync.flush()
    return r


def _ranking_item(db_sync, ranking, application, *, rank, sub_type="nstc", alloc_year=114, allocated=True):
    it = CollegeRankingItem(
        ranking_id=ranking.id,
        application_id=application.id,
        rank_position=rank,
        is_allocated=allocated,
        allocated_sub_type=sub_type if allocated else None,
        allocation_year=alloc_year if allocated else None,
        status="allocated" if allocated else "ranked",
    )
    db_sync.add(it)
    db_sync.flush()
    return it


def _roster(db_sync, config, admin, *, status=RosterStatus.LOCKED, sub_type="nstc", alloc_year=114, code="ROSTER-RC-1"):
    r = PaymentRoster(
        roster_code=code,
        scholarship_configuration_id=config.id,
        period_label="114",
        academic_year=114,
        roster_cycle=RosterCycle.YEARLY,
        sub_type=sub_type,
        allocation_year=alloc_year,
        status=status,
        trigger_type=RosterTriggerType.MANUAL,
        created_by=admin.id,
        student_verification_enabled=False,
    )
    db_sync.add(r)
    db_sync.flush()
    return r


def _roster_item(db_sync, roster, application, *, sub_type="nstc", alloc_year=114, amount=50000):
    it = PaymentRosterItem(
        roster_id=roster.id,
        application_id=application.id,
        student_id_number=(application.student_data or {}).get("std_pid", "X"),
        student_name=(application.student_data or {}).get("std_cname", "X"),
        scholarship_name="NSTC",
        scholarship_amount=amount,
        scholarship_subtype=sub_type,
        allocation_year=alloc_year,
        allocated_sub_type=sub_type,
        is_included=True,
    )
    db_sync.add(it)
    db_sync.flush()
    return it


@pytest.fixture
def diff_scenario(db_sync):
    """One nstc-114 roster holding student A; distribution has A (already in
    roster) + B (allocated, missing → to_add). A third item C sits in the
    roster but is NOT allocated → to_remove."""
    admin = _admin(db_sync)
    sch = _scholarship(db_sync)
    config = _config(db_sync, sch)
    ua = _student(db_sync, "rc_a")
    ub = _student(db_sync, "rc_b")
    uc = _student(db_sync, "rc_c")
    app_a = _application(db_sync, ua, sch, config, app_id="APP-RC-A", std_code="111A")
    app_b = _application(db_sync, ub, sch, config, app_id="APP-RC-B", std_code="111B")
    app_c = _application(db_sync, uc, sch, config, app_id="APP-RC-C", std_code="111C")
    ranking = _ranking(db_sync, sch)
    _ranking_item(db_sync, ranking, app_a, rank=1)  # allocated, in roster
    _ranking_item(db_sync, ranking, app_b, rank=2)  # allocated, missing → to_add
    _ranking_item(db_sync, ranking, app_c, rank=3, allocated=False)  # not allocated
    roster = _roster(db_sync, config, admin)
    _roster_item(db_sync, roster, app_a)  # matches distribution
    item_c = _roster_item(db_sync, roster, app_c)  # orphan → to_remove
    db_sync.commit()
    return {
        "admin": admin,
        "config": config,
        "roster": roster,
        "app_a": app_a.id,
        "app_b": app_b.id,
        "app_c": app_c.id,
        "item_c": item_c.id,
    }


def test_distribution_diff_lists_missing_and_orphan(db_sync, diff_scenario):
    svc = RosterService(db_sync)
    diff = svc.get_distribution_diff_for_roster(diff_scenario["roster"].id)

    add_ids = {e.application_id for e in diff["to_add"]}
    remove_item_ids = {e.item_id for e in diff["to_remove"]}

    assert add_ids == {diff_scenario["app_b"]}
    assert remove_item_ids == {diff_scenario["item_c"]}

    remove_app_ids = {e.application_id for e in diff["to_remove"]}
    assert diff_scenario["app_a"] not in add_ids
    assert diff_scenario["app_a"] not in remove_app_ids
    # to_add carries display fields from student_data
    entry = next(e for e in diff["to_add"] if e.application_id == diff_scenario["app_b"])
    assert entry.student_id == "111B"
    assert entry.department_name == "教育博"
    assert entry.allocated_sub_type == "nstc"
    assert entry.allocation_year == 114
