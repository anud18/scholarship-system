"""Pin: generate_rosters_from_distribution groups allocated ranking items by
(allocation_config_id, sub_type) and resolves the CONSUMED config per group —
a borrowed slot whose allocation_config_id points at a prior-year sibling
config produces a roster carrying that sibling's id/year, not the requesting
config's."""

from app.models.application import Application, ApplicationStatus
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.api.v1.endpoints.manual_distribution import _build_roster_generation_message
from app.models.payment_roster import PaymentRoster, RosterStatus
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
    result = svc.generate_rosters_from_distribution(
        scholarship_type_id=sch.id,
        academic_year=115,
        semester="first",
        created_by_user_id=admin.id,
        student_verification_enabled=False,
    )
    rosters = result.created
    assert result.skipped == []

    by_config = {r.allocation_config_id: r for r in rosters}
    assert set(by_config) == {own.id, prior.id}
    # Own-config roster: snapshot year = 115, project_number from own config.
    assert by_config[own.id].allocation_year == 115
    assert by_config[own.id].project_number == "115R000001"
    # Borrowed-slot roster: consumed = prior config → year 114, prior project_number.
    assert by_config[prior.id].allocation_year == 114
    assert by_config[prior.id].project_number == "114R000001"
    assert by_config[prior.id].scholarship_configuration_id == own.id


def test_regenerate_reports_existing_as_skipped_not_silent(db_sync):
    """Issue #1033: a second generate (force_regenerate=False) must report the
    pre-existing rosters as `skipped` instead of silently returning created=[],
    so the API can tell the admin nothing was rebuilt."""
    admin = _admin(db_sync)
    sch = ScholarshipType(code="skip_sch", name="Skip", description="x")
    db_sync.add(sch)
    db_sync.flush()
    own = _config(db_sync, sch, academic_year=115, code="SKIP-115", project_numbers={"nstc": "115R000001"})

    ua = _student(db_sync, "skip_a")
    app_a = _application(db_sync, ua, sch, own, app_id="APP-SKIP-A", std_code="115A", alloc_config_id=own.id)

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
    db_sync.add(
        CollegeRankingItem(
            ranking_id=ranking.id,
            application_id=app_a.id,
            rank_position=1,
            is_allocated=True,
            allocated_sub_type="nstc",
            allocation_config_id=own.id,
            status="allocated",
        )
    )
    db_sync.flush()
    db_sync.commit()

    svc = RosterService(db_sync)
    kwargs = dict(
        scholarship_type_id=sch.id,
        academic_year=115,
        semester="first",
        created_by_user_id=admin.id,
        student_verification_enabled=False,
    )

    first = svc.generate_rosters_from_distribution(**kwargs)
    assert len(first.created) == 1
    assert first.skipped == []

    # Second run without force: the roster already exists → reported as skipped,
    # nothing created (the silent "produced 0" success this fixes).
    second = svc.generate_rosters_from_distribution(**kwargs)
    assert second.created == []
    assert len(second.skipped) == 1
    assert second.skipped[0].id == first.created[0].id

    # With force: the existing roster is rebuilt (created), not skipped.
    forced = svc.generate_rosters_from_distribution(**kwargs, force_regenerate=True)
    assert len(forced.created) == 1
    assert forced.skipped == []
    assert forced.created[0].id == first.created[0].id


def test_force_regenerate_on_locked_roster_is_reported_not_500(db_sync):
    """Issue #1033: force_regenerate on a LOCKED roster must be reported as
    `locked` (so the API can say so), not raise and abort the whole batch."""
    admin = _admin(db_sync)
    sch = ScholarshipType(code="lock_sch", name="Lock", description="x")
    db_sync.add(sch)
    db_sync.flush()
    own = _config(db_sync, sch, academic_year=115, code="LOCK-115", project_numbers={"nstc": "115R000001"})

    ua = _student(db_sync, "lock_a")
    app_a = _application(db_sync, ua, sch, own, app_id="APP-LOCK-A", std_code="115A", alloc_config_id=own.id)

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
    db_sync.add(
        CollegeRankingItem(
            ranking_id=ranking.id,
            application_id=app_a.id,
            rank_position=1,
            is_allocated=True,
            allocated_sub_type="nstc",
            allocation_config_id=own.id,
            status="allocated",
        )
    )
    db_sync.flush()
    db_sync.commit()

    svc = RosterService(db_sync)
    kwargs = dict(
        scholarship_type_id=sch.id,
        academic_year=115,
        semester="first",
        created_by_user_id=admin.id,
        student_verification_enabled=False,
    )

    first = svc.generate_rosters_from_distribution(**kwargs)
    assert len(first.created) == 1

    # Lock the roster, then force-regenerate: it must not raise.
    roster = first.created[0]
    roster.status = RosterStatus.LOCKED
    db_sync.commit()

    forced = svc.generate_rosters_from_distribution(**kwargs, force_regenerate=True)
    assert forced.created == []
    assert forced.skipped == []
    assert len(forced.locked) == 1
    assert forced.locked[0].id == roster.id


def test_build_roster_generation_message():
    """The admin-facing summary never hides skipped/locked rosters (issue #1033)."""
    assert _build_roster_generation_message(3, 0, 0) == "成功產生 3 個造冊"

    only_skipped = _build_roster_generation_message(0, 2, 0)
    assert "成功產生 0 個造冊" in only_skipped
    assert "2 個造冊已存在" in only_skipped
    assert "force_regenerate=true" in only_skipped

    locked = _build_roster_generation_message(1, 0, 1)
    assert "成功產生 1 個造冊" in locked
    assert "1 個造冊已鎖定" in locked

    both = _build_roster_generation_message(1, 2, 3)
    assert "2 個造冊已存在" in both
    assert "3 個造冊已鎖定" in both
