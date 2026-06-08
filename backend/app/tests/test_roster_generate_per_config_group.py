"""Pin: generate_rosters_from_distribution groups allocated ranking items by
(allocation_config_id, sub_type) and resolves the CONSUMED config per group —
a borrowed slot whose allocation_config_id points at a prior-year sibling
config produces a roster carrying that sibling's id/year, not the requesting
config's."""

from app.models.application import Application, ApplicationStatus
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.payment_roster import PaymentRoster
from app.models.scholarship import (
    ScholarshipConfiguration,
    ScholarshipType,
    SubTypeSelectionMode,
)
from app.models.user import User, UserRole, UserType
from app.services.roster_service import RosterService


def _admin(db_sync):
    u = User(
        nycu_id="gen_admin",
        email="gen_admin@nycu.edu.tw",
        name="Gen Admin",
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


def _config(db_sync, scholarship, *, academic_year, code, project_numbers=None):
    c = ScholarshipConfiguration(
        scholarship_type_id=scholarship.id,
        config_code=code,
        config_name=code,
        academic_year=academic_year,
        semester="first",
        amount=50000,
        has_quota_limit=False,
        project_numbers=project_numbers,
    )
    db_sync.add(c)
    db_sync.flush()
    return c


def _application(db_sync, user, scholarship, config, *, app_id, std_code, alloc_config_id):
    a = Application(
        user_id=user.id,
        app_id=app_id,
        scholarship_type_id=scholarship.id,
        scholarship_configuration_id=config.id,
        academic_year=115,
        semester="first",
        status=ApplicationStatus.approved,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        scholarship_subtype_list=[],
        sub_scholarship_type="nstc",
        allocation_config_id=alloc_config_id,
        student_data={
            "std_stdcode": std_code,
            "std_pid": f"A{std_code}",
            "std_cname": f"學生{std_code}",
        },
        submitted_form_data={"fields": {"postal_account": {"value": "0001234567"}}},
        amount=50000,
    )
    db_sync.add(a)
    db_sync.flush()
    return a


def test_generate_groups_by_allocation_config(db_sync):
    admin = _admin(db_sync)
    sch = ScholarshipType(code="gen_sch", name="Gen", description="x")
    db_sync.add(sch)
    db_sync.flush()
    own = _config(db_sync, sch, academic_year=115, code="GEN-115", project_numbers={"nstc": "115R000001"})
    prior = _config(db_sync, sch, academic_year=114, code="GEN-114", project_numbers={"nstc": "114R000001"})

    ua = _student(db_sync, "gen_a")
    ub = _student(db_sync, "gen_b")
    app_a = _application(db_sync, ua, sch, own, app_id="APP-GEN-A", std_code="115A", alloc_config_id=own.id)
    app_b = _application(db_sync, ub, sch, own, app_id="APP-GEN-B", std_code="115B", alloc_config_id=prior.id)

    ranking = CollegeRanking(
        scholarship_type_id=sch.id,
        sub_type_code="nstc",
        academic_year=115,
        semester="first",
        ranking_name="R",
        is_finalized=True,
        ranking_status="finalized",
        distribution_executed=True,
    )
    db_sync.add(ranking)
    db_sync.flush()
    for app, cfg in ((app_a, own), (app_b, prior)):
        db_sync.add(
            CollegeRankingItem(
                ranking_id=ranking.id,
                application_id=app.id,
                rank_position=1,
                is_allocated=True,
                allocated_sub_type="nstc",
                allocation_config_id=cfg.id,
                status="allocated",
            )
        )
    db_sync.flush()
    db_sync.commit()

    svc = RosterService(db_sync)
    rosters = svc.generate_rosters_from_distribution(
        scholarship_type_id=sch.id,
        academic_year=115,
        semester="first",
        created_by_user_id=admin.id,
        student_verification_enabled=False,
    )

    by_config = {r.allocation_config_id: r for r in rosters}
    assert set(by_config) == {own.id, prior.id}
    # Own-config roster: snapshot year = 115, project_number from own config.
    assert by_config[own.id].allocation_year == 115
    assert by_config[own.id].project_number == "115R000001"
    # Borrowed-slot roster: consumed = prior config → year 114, prior project_number.
    assert by_config[prior.id].allocation_year == 114
    assert by_config[prior.id].project_number == "114R000001"
    assert by_config[prior.id].scholarship_configuration_id == own.id
