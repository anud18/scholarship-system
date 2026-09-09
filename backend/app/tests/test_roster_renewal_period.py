"""續領跟新申請一樣每期造冊，期間往後延伸。

A 115 renewal of a 114 award keeps consuming the 114 slot
(allocation_config_id = phd_114, application_service.create_renewal), but it is
paid in the 115 period. The roster it lands in must therefore carry
period_label "115" (with allocation_year 114 recording the consumed slot) and
its item must be marked 115續領 — not sit in a "114" roster that matches no
115 schedule period.

The per-period path (generate_roster → _get_eligible_applications) must also
pick renewals up: they never hold a CollegeRankingItem, and a self-renewal's
scholarship_configuration_id points at the prior year's config.
"""

from app.models.application import Application, ApplicationStatus
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.enums import QuotaManagementMode, ReviewStage
from app.models.scholarship import (
    ScholarshipConfiguration,
    ScholarshipType,
    SubTypeSelectionMode,
)
from app.models.user import User, UserRole, UserType
from app.services.roster_service import RosterService


def _user(db_sync, nycu_id, *, role=UserRole.student, user_type=UserType.student):
    user = User(
        nycu_id=nycu_id,
        email=f"{nycu_id}@nycu.edu.tw",
        name=f"User {nycu_id}",
        role=role,
        user_type=user_type,
    )
    db_sync.add(user)
    db_sync.flush()
    return user


def _config(db_sync, scholarship, *, academic_year, code, project_number):
    config = ScholarshipConfiguration(
        scholarship_type_id=scholarship.id,
        config_code=code,
        config_name=code,
        academic_year=academic_year,
        semester=None,
        amount=40000,
        has_quota_limit=False,
        quota_management_mode=QuotaManagementMode.matrix_based,
        project_numbers={"nstc": project_number},
    )
    db_sync.add(config)
    db_sync.flush()
    return config


def _application(db_sync, user, scholarship, config, *, app_id, std_code, alloc_config, is_renewal):
    application = Application(
        user_id=user.id,
        app_id=app_id,
        scholarship_type_id=scholarship.id,
        scholarship_configuration_id=config.id,
        allocation_config_id=alloc_config.id,
        academic_year=115,
        semester=None,
        status=ApplicationStatus.approved,
        review_stage=ReviewStage.quota_distributed,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        scholarship_subtype_list=["nstc"],
        sub_scholarship_type="nstc",
        is_renewal=is_renewal,
        renewal_year=114 if is_renewal else None,
        student_data={"std_stdcode": std_code, "std_pid": f"A{std_code}", "std_cname": f"學生{std_code}"},
        submitted_form_data={"fields": {"postal_account": {"value": "0001234567"}}},
        amount=40000,
    )
    db_sync.add(application)
    db_sync.flush()
    return application


def _setup(db_sync):
    """115 config + prior 114 config; one 115 新申請 allocated on the 115 slot
    and one 115 續領 of a 114 award (consumes the 114 slot, config FK = 114)."""
    admin = _user(db_sync, "period_admin", role=UserRole.admin, user_type=UserType.employee)
    scholarship = ScholarshipType(
        code="period_phd",
        name="PhD",
        description="x",
        sub_type_list=["nstc"],
        sub_type_selection_mode=SubTypeSelectionMode.single,
    )
    db_sync.add(scholarship)
    db_sync.flush()
    current = _config(db_sync, scholarship, academic_year=115, code="PERIOD-115", project_number="115R000001")
    prior = _config(db_sync, scholarship, academic_year=114, code="PERIOD-114", project_number="114R000001")

    new_app = _application(
        db_sync,
        _user(db_sync, "period_new"),
        scholarship,
        current,
        app_id="APP-PERIOD-NEW",
        std_code="115N",
        alloc_config=current,
        is_renewal=False,
    )
    renewal = _application(
        db_sync,
        _user(db_sync, "period_renew"),
        scholarship,
        prior,
        app_id="APP-PERIOD-RENEW",
        std_code="115R",
        alloc_config=prior,
        is_renewal=True,
    )

    ranking = CollegeRanking(
        scholarship_type_id=scholarship.id,
        sub_type_code="nstc",
        academic_year=115,
        semester="yearly",
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
            application_id=new_app.id,
            rank_position=1,
            is_allocated=True,
            allocated_sub_type="nstc",
            allocation_config_id=current.id,
            status="allocated",
        )
    )
    db_sync.commit()
    return admin, scholarship, current, prior, new_app, renewal


def test_renewal_roster_uses_requesting_year_as_period(db_sync):
    admin, scholarship, current, prior, new_app, renewal = _setup(db_sync)

    result = RosterService(db_sync).generate_rosters_from_distribution(
        scholarship_type_id=scholarship.id,
        academic_year=115,
        semester="yearly",
        created_by_user_id=admin.id,
        student_verification_enabled=False,
    )

    by_config = {r.allocation_config_id: r for r in result.created}
    assert set(by_config) == {current.id, prior.id}

    renewal_roster = by_config[prior.id]
    # 期間 = 發放年度（115-09~116-08），名額仍記錄消耗 114 年度的 slot / 計畫編號。
    assert renewal_roster.period_label == "115"
    assert renewal_roster.academic_year == 115
    assert renewal_roster.allocation_year == 114
    assert renewal_roster.project_number == "114R000001"
    assert renewal_roster.sub_type == "nstc"
    assert renewal_roster.scholarship_configuration_id == current.id

    (item,) = renewal_roster.items
    assert item.application_id == renewal.id
    assert item.application_identity == "115續領"
    assert item.allocated_sub_type == "nstc"
    assert item.allocation_year == 114

    new_roster = by_config[current.id]
    assert new_roster.period_label == "115"
    assert new_roster.allocation_year == 115
    (new_item,) = new_roster.items
    assert new_item.application_identity == "115新申請"


def test_per_period_eligibility_includes_renewals_in_matrix_mode(db_sync):
    _admin, _scholarship, current, _prior, new_app, renewal = _setup(db_sync)

    eligible = RosterService(db_sync)._get_eligible_applications(
        scholarship_configuration_id=current.id,
        period_label="115",
        academic_year=115,
    )

    # Renewal first (ordered by is_renewal desc), then the allocated 新申請 —
    # the renewal is found by type + year even though its config FK is phd_114.
    assert [a.id for a in eligible] == [renewal.id, new_app.id]


def test_per_period_eligibility_excludes_unallocated_new_applications(db_sync):
    admin, scholarship, current, _prior, new_app, renewal = _setup(db_sync)
    waitlisted = _application(
        db_sync,
        _user(db_sync, "period_wait"),
        scholarship,
        current,
        app_id="APP-PERIOD-WAIT",
        std_code="115W",
        alloc_config=current,
        is_renewal=False,
    )
    db_sync.commit()

    eligible = RosterService(db_sync)._get_eligible_applications(
        scholarship_configuration_id=current.id,
        period_label="115",
        academic_year=115,
    )

    ids = {a.id for a in eligible}
    assert ids == {renewal.id, new_app.id}
    assert waitlisted.id not in ids
