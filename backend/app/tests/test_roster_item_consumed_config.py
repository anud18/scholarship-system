"""Pin: a roster item built for a borrowed slot draws scholarship_amount and the
allocation_year display snapshot from the CONSUMED config (resolved via
roster.allocation_config_id), while scholarship_name follows the requesting
config's scholarship type (cross-type decision §8). item.allocation_config_id
is written from the roster."""

from app.models.application import Application, ApplicationStatus
from app.models.payment_roster import (
    PaymentRoster,
    RosterCycle,
    RosterStatus,
    RosterTriggerType,
    StudentVerificationStatus,
)
from app.models.scholarship import (
    ScholarshipConfiguration,
    ScholarshipType,
    SubTypeSelectionMode,
)
from app.models.user import User, UserRole, UserType
from app.services.roster_service import RosterService


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


def _config(db_sync, sch, *, academic_year, code, amount):
    c = ScholarshipConfiguration(
        scholarship_type_id=sch.id,
        config_code=code,
        config_name=code,
        academic_year=academic_year,
        semester="first",
        amount=amount,
        has_quota_limit=False,
    )
    db_sync.add(c)
    db_sync.flush()
    return c


def test_roster_item_amount_year_from_consumed_config(db_sync):
    admin = User(
        nycu_id="ci_admin",
        email="ci_admin@nycu.edu.tw",
        name="CI",
        role=UserRole.admin,
        user_type=UserType.employee,
    )
    db_sync.add(admin)
    db_sync.flush()

    sch = ScholarshipType(code="ci_sch", name="CI Scholarship", description="x")
    db_sync.add(sch)
    db_sync.flush()
    requesting = _config(db_sync, sch, academic_year=115, code="CI-115", amount=60000)
    consumed = _config(db_sync, sch, academic_year=114, code="CI-114", amount=50000)

    user = _student(db_sync, "ci_a")
    app = Application(
        user_id=user.id,
        app_id="APP-CI-A",
        scholarship_type_id=sch.id,
        scholarship_configuration_id=requesting.id,
        academic_year=115,
        semester="first",
        status=ApplicationStatus.approved,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        scholarship_subtype_list=[],
        sub_scholarship_type="nstc",
        allocation_config_id=consumed.id,
        student_data={"std_stdcode": "115A", "std_pid": "A115A", "std_cname": "甲"},
        submitted_form_data={"fields": {"postal_account": {"value": "0001234567"}}},
        amount=None,  # no per-application override → fall back to consumed config amount
    )
    db_sync.add(app)
    db_sync.flush()

    roster = PaymentRoster(
        roster_code="ROSTER-CI-1",
        scholarship_configuration_id=requesting.id,
        allocation_config_id=consumed.id,
        period_label="114",
        academic_year=115,
        roster_cycle=RosterCycle.YEARLY,
        sub_type="nstc",
        allocation_year=114,
        status=RosterStatus.PROCESSING,
        trigger_type=RosterTriggerType.MANUAL,
        created_by=admin.id,
        student_verification_enabled=False,
    )
    db_sync.add(roster)
    db_sync.flush()
    db_sync.commit()

    svc = RosterService(db_sync)
    item = svc._create_roster_item(roster, app, None, StudentVerificationStatus.VERIFIED, {"is_eligible": True})
    db_sync.flush()

    # amount fallback comes from the CONSUMED config (50000), not requesting (60000)
    assert int(item.scholarship_amount) == 50000
    # allocation_year snapshot = consumed config academic year
    assert item.allocation_year == 114
    # allocation_config_id copied from the roster
    assert item.allocation_config_id == consumed.id
    # scholarship_name follows the REQUESTING config's scholarship type name
    assert item.scholarship_name == "CI Scholarship"
