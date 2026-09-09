"""A configuration owns all 36 months of its cohort.

續領只開放給該配置的得獎者：a 114 awardee's renewals for 115 and 116 are
「114 續領生」. They keep consuming the 114 slot (allocation_config_id =
phd_114, as application_service.create_renewal sets it) and are paid in the
115 / 116 periods — so their rosters hang under phd_114 (period_label "115",
allocation_year 114, the 114 計畫編號) and the item is marked 114續領, never
under phd_115.

The per-period path (generate_roster → _get_eligible_applications) selects by
"who consumes this configuration's slots in the paying year": renewals need
no CollegeRankingItem, 新申請 must be allocated in that year's executed
ranking, and a 115 新申請 補發 onto a 114 slot belongs to phd_114's list too.
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


def _application(db_sync, user, scholarship, config, *, app_id, std_code, alloc_config, is_renewal, academic_year=115):
    application = Application(
        user_id=user.id,
        app_id=app_id,
        scholarship_type_id=scholarship.id,
        scholarship_configuration_id=config.id,
        allocation_config_id=alloc_config.id,
        academic_year=academic_year,
        semester=None,
        status=ApplicationStatus.approved,
        review_stage=ReviewStage.quota_distributed,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        scholarship_subtype_list=["nstc"],
        sub_scholarship_type="nstc",
        is_renewal=is_renewal,
        renewal_year=alloc_config.academic_year if is_renewal else None,
        student_data={"std_stdcode": std_code, "std_pid": f"A{std_code}", "std_cname": f"學生{std_code}"},
        submitted_form_data={"fields": {"postal_account": {"value": "0001234567"}}},
        amount=40000,
    )
    db_sync.add(application)
    db_sync.flush()
    return application


def _allocate(db_sync, ranking, application, config):
    db_sync.add(
        CollegeRankingItem(
            ranking_id=ranking.id,
            application_id=application.id,
            rank_position=1,
            is_allocated=True,
            allocated_sub_type="nstc",
            allocation_config_id=config.id,
            status="allocated",
        )
    )


def _setup(db_sync):
    """phd_115 + phd_114. In the 115 paying year: a 115 新申請 on a 115 slot, a
    114 續領生 (114 awardee renewing, still on the 114 slot) and a 115 新申請
    補發 onto a freed 114 slot."""
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
    borrower = _application(
        db_sync,
        _user(db_sync, "period_borrow"),
        scholarship,
        current,
        app_id="APP-PERIOD-BORROW",
        std_code="115B",
        alloc_config=prior,
        is_renewal=False,
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
    _allocate(db_sync, ranking, new_app, current)
    _allocate(db_sync, ranking, borrower, prior)
    db_sync.commit()
    return admin, scholarship, current, prior, new_app, renewal, borrower


def test_distribution_rosters_hang_under_the_slot_owning_config(db_sync):
    admin, scholarship, current, prior, new_app, renewal, borrower = _setup(db_sync)

    result = RosterService(db_sync).generate_rosters_from_distribution(
        scholarship_type_id=scholarship.id,
        academic_year=115,
        semester="yearly",
        created_by_user_id=admin.id,
        student_verification_enabled=False,
    )

    by_owner = {r.scholarship_configuration_id: r for r in result.created}
    assert set(by_owner) == {current.id, prior.id}

    # phd_114's 115 roster: the 114 續領生 + the 補發 borrower, on the 114 計畫編號.
    roster_114 = by_owner[prior.id]
    assert roster_114.period_label == "115"
    assert roster_114.academic_year == 115
    assert roster_114.allocation_config_id == prior.id
    assert roster_114.allocation_year == 114
    assert roster_114.project_number == "114R000001"
    assert roster_114.roster_code == "ROSTER-115-nstc-PERIOD-114"
    identities = {item.application_id: item.application_identity for item in roster_114.items}
    assert identities == {renewal.id: "114續領", borrower.id: "115新申請"}
    assert all(item.allocation_year == 114 for item in roster_114.items)

    # phd_115's 115 roster: only the 新申請 on its own slot.
    roster_115 = by_owner[current.id]
    assert roster_115.period_label == "115"
    assert roster_115.allocation_year == 115
    assert [item.application_identity for item in roster_115.items] == ["115新申請"]


def test_per_period_eligibility_selects_by_consumed_slot(db_sync):
    _admin, _scholarship, current, prior, new_app, renewal, borrower = _setup(db_sync)
    service = RosterService(db_sync)

    on_114 = service._get_eligible_applications(
        scholarship_configuration_id=prior.id, period_label="115", academic_year=115
    )
    on_115 = service._get_eligible_applications(
        scholarship_configuration_id=current.id, period_label="115", academic_year=115
    )

    # Renewal first (ordered by is_renewal desc), then the allocated borrower.
    assert [a.id for a in on_114] == [renewal.id, borrower.id]
    assert [a.id for a in on_115] == [new_app.id]


def test_per_period_eligibility_excludes_unallocated_new_applications(db_sync):
    _admin, scholarship, current, _prior, new_app, _renewal, _borrower = _setup(db_sync)
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
        scholarship_configuration_id=current.id, period_label="115", academic_year=115
    )
    ids = {a.id for a in eligible}
    assert ids == {new_app.id}
    assert waitlisted.id not in ids


def test_renewal_year_without_executed_ranking_still_lists_renewals(db_sync):
    """Second-year period on phd_114 before the 116 distribution ran: no ranking
    for 116 exists, which used to raise; now only the renewals are eligible."""
    _admin, scholarship, _current, prior, _new_app, _renewal, _borrower = _setup(db_sync)
    second_renewal = _application(
        db_sync,
        _user(db_sync, "period_renew2"),
        scholarship,
        prior,
        app_id="APP-PERIOD-RENEW2",
        std_code="116R",
        alloc_config=prior,
        is_renewal=True,
        academic_year=116,
    )
    db_sync.commit()

    eligible = RosterService(db_sync)._get_eligible_applications(
        scholarship_configuration_id=prior.id, period_label="116-09", academic_year=116
    )
    assert [a.id for a in eligible] == [second_renewal.id]


def test_period_with_nobody_to_roster_leaves_no_failed_roster_row(db_sync):
    """phd_115's 116-09 before the 116 distribution and before any 115 awardee
    renewed: the service must refuse up front (ValueError → 400 at the endpoint)
    instead of creating a roster row that is then flipped to FAILED."""
    import pytest

    from app.core.exceptions import RosterGenerationError
    from app.models.payment_roster import PaymentRoster, RosterCycle, RosterTriggerType

    admin, _scholarship, current, _prior, _new_app, _renewal, _borrower = _setup(db_sync)
    before = db_sync.query(PaymentRoster).count()

    # generate_roster wraps the cause in RosterGenerationError; the endpoint
    # re-dispatches ValueError causes as 400 with the curated message.
    with pytest.raises(RosterGenerationError) as ei:
        RosterService(db_sync).generate_roster(
            scholarship_configuration_id=current.id,
            period_label="116-09",
            roster_cycle=RosterCycle.MONTHLY,
            academic_year=116,
            created_by_user_id=admin.id,
            trigger_type=RosterTriggerType.MANUAL,
            student_verification_enabled=False,
        )
    assert isinstance(ei.value.__cause__, ValueError)
    assert "找不到已執行分發的排名，也沒有已核准的續領" in str(ei.value.__cause__)
    assert ei.value.roster_id is None  # no roster row was created, nothing to mark FAILED
    db_sync.rollback()
    assert db_sync.query(PaymentRoster).count() == before


def test_monthly_roster_items_snapshot_the_slot_year_not_the_paying_year(db_sync):
    """phd_114's 115-09 monthly roster: no ranking item and no roster-level
    allocation snapshot, so the item must fall back to the application's own
    slot config — 114 續領生 shows 114年 國科會 on the 114 計畫, not 115."""
    from app.models.payment_roster import RosterCycle, RosterTriggerType

    admin, _scholarship, _current, prior, _new_app, renewal, borrower = _setup(db_sync)

    roster = RosterService(db_sync).generate_roster(
        scholarship_configuration_id=prior.id,
        period_label="115-09",
        roster_cycle=RosterCycle.MONTHLY,
        academic_year=115,
        created_by_user_id=admin.id,
        trigger_type=RosterTriggerType.MANUAL,
        student_verification_enabled=False,
    )
    db_sync.flush()

    by_app = {item.application_id: item for item in roster.items}
    assert set(by_app) == {renewal.id, borrower.id}
    assert by_app[renewal.id].application_identity == "114續領"
    assert by_app[borrower.id].application_identity == "115新申請"
    assert all(item.allocation_config_id == prior.id for item in by_app.values())
    assert all(item.allocation_year == 114 for item in by_app.values())
    assert all(item.allocated_sub_type == "nstc" for item in by_app.values())
