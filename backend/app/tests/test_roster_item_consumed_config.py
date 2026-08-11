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


def test_roster_item_year_falls_back_to_ranking_item_config(db_sync):
    """Regression (user report): on the generic/monthly generation path the
    roster has NO allocation_config_id/allocation_year snapshot, but the
    ranking item that supplied allocated_sub_type records which year's quota
    was consumed (allocation_config_id). Without reading it, a student
    distributed against the 113 quota was stamped NULL and the Excel/查看名單
    fallback mislabeled them as the roster's own year (114年 國科會)."""
    from app.models.college_review import CollegeRanking, CollegeRankingItem

    admin = User(
        nycu_id="ci_admin2",
        email="ci_admin2@nycu.edu.tw",
        name="CI2",
        role=UserRole.admin,
        user_type=UserType.employee,
    )
    db_sync.add(admin)
    db_sync.flush()

    sch = ScholarshipType(code="ci_sch2", name="CI Scholarship 2", description="x")
    db_sync.add(sch)
    db_sync.flush()
    current = _config(db_sync, sch, academic_year=114, code="CI2-114", amount=40000)
    prior = _config(db_sync, sch, academic_year=113, code="CI2-113", amount=40000)

    user = _student(db_sync, "ci_b")
    app = Application(
        user_id=user.id,
        app_id="APP-CI-B",
        scholarship_type_id=sch.id,
        scholarship_configuration_id=current.id,
        academic_year=114,
        semester="first",
        status=ApplicationStatus.approved,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        scholarship_subtype_list=[],
        sub_scholarship_type="nstc",
        student_data={"std_stdcode": "114B", "std_pid": "A114B", "std_cname": "乙"},
        submitted_form_data={"fields": {"postal_account": {"value": "0007654321"}}},
        amount=40000,
    )
    db_sync.add(app)
    db_sync.flush()

    ranking = CollegeRanking(
        scholarship_type_id=sch.id,
        sub_type_code="default",
        academic_year=114,
        ranking_name="CI2 Ranking",
        ranking_status="finalized",
        is_finalized=True,
    )
    db_sync.add(ranking)
    db_sync.flush()
    # 學生被分發到 113 年度配額：排名項記錄消耗配置 = prior (113)
    db_sync.add(
        CollegeRankingItem(
            ranking_id=ranking.id,
            application_id=app.id,
            rank_position=1,
            status="ranked",
            is_allocated=True,
            allocated_sub_type="nstc",
            allocation_config_id=prior.id,
        )
    )
    db_sync.flush()

    # 一般/月結造冊：roster 層級沒有 allocation 快照
    roster = PaymentRoster(
        roster_code="ROSTER-CI-2",
        scholarship_configuration_id=current.id,
        period_label="114-05",
        academic_year=114,
        roster_cycle=RosterCycle.MONTHLY,
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

    # 年度/消耗配置快照取自排名項，不是 NULL、也不是造冊年度
    assert item.allocation_year == 113
    assert item.allocation_config_id == prior.id
    assert item.allocated_sub_type == "nstc"


def test_roster_item_roster_snapshot_wins_over_ranking_item(db_sync):
    """分發矩陣路徑：roster 層級的消耗配置快照必須維持優先權（一冊一組），
    不被排名項覆蓋。"""
    from app.models.college_review import CollegeRanking, CollegeRankingItem

    admin = User(
        nycu_id="ci_admin3",
        email="ci_admin3@nycu.edu.tw",
        name="CI3",
        role=UserRole.admin,
        user_type=UserType.employee,
    )
    db_sync.add(admin)
    db_sync.flush()

    sch = ScholarshipType(code="ci_sch3", name="CI Scholarship 3", description="x")
    db_sync.add(sch)
    db_sync.flush()
    current = _config(db_sync, sch, academic_year=114, code="CI3-114", amount=40000)
    prior = _config(db_sync, sch, academic_year=113, code="CI3-113", amount=40000)

    user = _student(db_sync, "ci_c")
    app = Application(
        user_id=user.id,
        app_id="APP-CI-C",
        scholarship_type_id=sch.id,
        scholarship_configuration_id=current.id,
        academic_year=114,
        semester="first",
        status=ApplicationStatus.approved,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        scholarship_subtype_list=[],
        sub_scholarship_type="nstc",
        student_data={"std_stdcode": "114C", "std_pid": "A114C", "std_cname": "丙"},
        submitted_form_data={"fields": {"postal_account": {"value": "0001112223"}}},
        amount=40000,
    )
    db_sync.add(app)
    db_sync.flush()

    ranking = CollegeRanking(
        scholarship_type_id=sch.id,
        sub_type_code="default",
        academic_year=114,
        ranking_name="CI3 Ranking",
        ranking_status="finalized",
        is_finalized=True,
    )
    db_sync.add(ranking)
    db_sync.flush()
    db_sync.add(
        CollegeRankingItem(
            ranking_id=ranking.id,
            application_id=app.id,
            rank_position=1,
            status="ranked",
            is_allocated=True,
            allocated_sub_type="nstc",
            allocation_config_id=prior.id,
        )
    )
    db_sync.flush()

    roster = PaymentRoster(
        roster_code="ROSTER-CI-3",
        scholarship_configuration_id=current.id,
        allocation_config_id=current.id,  # roster-level snapshot (matrix path)
        allocation_year=114,
        sub_type="nstc",
        period_label="114",
        academic_year=114,
        roster_cycle=RosterCycle.YEARLY,
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

    assert item.allocation_year == 114
    assert item.allocation_config_id == current.id
