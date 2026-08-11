"""Pin the contract of 重新生成造冊 (RosterRegenerationService.regenerate_roster).

The feature exists so an admin can rebuild a roster's 名單 at ANY time — it must
NOT require 人員有異動 the way 比對分發名單 (reconcile) does. What it must and must
not do:

  * rebuild every item from the CURRENT distribution + config (fresh amount,
    project_number, sub_type, 學生資料), even when membership is unchanged;
  * carry approved 續領 students, which never own a CollegeRankingItem and are
    therefore invisible to the distribution diff;
  * PRESERVE the admin's manual exclusions (學生繳回 / 學生放棄 / 鎖定後移除…).
    Resurrecting them would silently inflate the student's cumulative
    received_months, which feeds the PhD 36-month cap;
  * preserve human bank-verification review state, which a rebuild cannot
    re-derive;
  * refuse a LOCKED roster.
"""

from unittest.mock import patch

import pytest

from app.core.exceptions import RosterLockedError, RosterNotFoundError
from app.models.application import Application, ApplicationStatus
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.payment_roster import (
    MANUAL_REMOVAL_PREFIX_RECONCILE,
    PaymentRoster,
    PaymentRosterItem,
    RosterCycle,
    RosterStatus,
    StudentVerificationStatus,
)
from app.models.scholarship import (
    ScholarshipConfiguration,
    ScholarshipType,
    SubTypeSelectionMode,
)
from app.models.user import User, UserRole, UserType
from app.services.roster_regeneration_service import RosterRegenerationService
from app.services.roster_service import RosterService

EXPORT_TARGET = "app.services.excel_export_service.ExcelExportService"


def _admin(db_sync):
    u = User(
        nycu_id="regen_admin",
        email="regen_admin@nycu.edu.tw",
        name="Regen Admin",
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


def _config(db_sync, scholarship, *, academic_year=115, code="REGEN-115", project_numbers=None, amount=50000):
    c = ScholarshipConfiguration(
        scholarship_type_id=scholarship.id,
        config_code=code,
        config_name=code,
        academic_year=academic_year,
        semester="first",
        amount=amount,
        has_quota_limit=False,
        project_numbers=project_numbers,
    )
    db_sync.add(c)
    db_sync.flush()
    return c


def _application(db_sync, user, scholarship, config, *, app_id, std_code, amount=50000, is_renewal=False):
    a = Application(
        user_id=user.id,
        app_id=app_id,
        scholarship_type_id=scholarship.id,
        scholarship_configuration_id=config.id,
        academic_year=config.academic_year,
        semester="first",
        status=ApplicationStatus.approved,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        scholarship_subtype_list=[],
        sub_scholarship_type="nstc",
        allocation_config_id=config.id,
        is_renewal=is_renewal,
        student_data={
            "std_stdcode": std_code,
            "std_pid": f"A{std_code}",
            "std_cname": f"學生{std_code}",
        },
        submitted_form_data={"fields": {"postal_account": {"value": "0001234567"}}},
        amount=amount,
    )
    db_sync.add(a)
    db_sync.flush()
    return a


def _ranking(db_sync, scholarship, *, academic_year=115):
    r = CollegeRanking(
        scholarship_type_id=scholarship.id,
        sub_type_code="nstc",
        academic_year=academic_year,
        semester="first",
        ranking_name="R",
        is_finalized=True,
        ranking_status="finalized",
        distribution_executed=True,
    )
    db_sync.add(r)
    db_sync.flush()
    return r


def _allocate(db_sync, ranking, application, config, *, rank_position=1):
    item = CollegeRankingItem(
        ranking_id=ranking.id,
        application_id=application.id,
        rank_position=rank_position,
        is_allocated=True,
        allocated_sub_type="nstc",
        allocation_config_id=config.id,
        status="allocated",
    )
    db_sync.add(item)
    db_sync.flush()
    return item


def _generate(db_sync, scholarship, admin):
    """Produce the initial roster through the real batch path."""
    result = RosterService(db_sync).generate_rosters_from_distribution(
        scholarship_type_id=scholarship.id,
        academic_year=115,
        semester="first",
        created_by_user_id=admin.id,
        student_verification_enabled=False,
    )
    assert len(result.created) == 1
    return result.created[0]


def _items(db_sync, roster_id):
    return db_sync.query(PaymentRosterItem).filter(PaymentRosterItem.roster_id == roster_id).all()


def test_regenerate_without_membership_change_refreshes_config_snapshots(db_sync):
    """The core ask: regeneration must work with NO 人員異動 and pick up config
    edits (計畫編號 / 金額) that were invisible to the already-generated roster."""
    admin = _admin(db_sync)
    sch = ScholarshipType(code="regen_sch", name="Regen", description="x")
    db_sync.add(sch)
    db_sync.flush()
    cfg = _config(db_sync, sch, project_numbers=None)
    student = _student(db_sync, "regen_a")
    app = _application(db_sync, student, sch, cfg, app_id="APP-REGEN-A", std_code="115A")
    ranking = _ranking(db_sync, sch)
    _allocate(db_sync, ranking, app, cfg)
    db_sync.commit()

    roster = _generate(db_sync, sch, admin)
    assert roster.project_number is None
    roster_id = roster.id

    # Admin fills in 計畫編號 and corrects the amount AFTER 生成造冊 — today the
    # only way those reach the roster is a rebuild.
    cfg.project_numbers = {"nstc": "115R000123"}
    app.amount = 60000
    db_sync.commit()

    with patch(EXPORT_TARGET):
        result = RosterRegenerationService(db_sync).regenerate_roster(roster_id=roster_id, admin_user_id=admin.id)

    assert result.rebuilt_items == 1
    assert result.failed_items == 0
    assert result.preserved_exclusions == 0
    assert result.roster.project_number == "115R000123"
    assert result.roster.status == RosterStatus.COMPLETED
    assert result.roster.qualified_count == 1

    items = _items(db_sync, roster_id)
    assert len(items) == 1
    assert int(items[0].scholarship_amount) == 60000


def test_regenerate_picks_up_newly_allocated_student(db_sync):
    admin = _admin(db_sync)
    sch = ScholarshipType(code="regen_add", name="RegenAdd", description="x")
    db_sync.add(sch)
    db_sync.flush()
    cfg = _config(db_sync, sch, code="REGENADD-115")
    ranking = _ranking(db_sync, sch)

    first_student = _student(db_sync, "add_a")
    first_app = _application(db_sync, first_student, sch, cfg, app_id="APP-ADD-A", std_code="115A")
    _allocate(db_sync, ranking, first_app, cfg)
    db_sync.commit()

    roster = _generate(db_sync, sch, admin)
    roster_id = roster.id

    late_student = _student(db_sync, "add_b")
    late_app = _application(db_sync, late_student, sch, cfg, app_id="APP-ADD-B", std_code="115B")
    _allocate(db_sync, ranking, late_app, cfg, rank_position=2)
    db_sync.commit()

    with patch(EXPORT_TARGET):
        result = RosterRegenerationService(db_sync).regenerate_roster(roster_id=roster_id, admin_user_id=admin.id)

    assert result.rebuilt_items == 2
    assert {i.student_number for i in _items(db_sync, roster_id)} == {"115A", "115B"}


def test_regenerate_preserves_manual_exclusion(db_sync):
    """A student the admin excluded (學生繳回) must NOT come back included —
    that would inflate their cumulative received_months."""
    admin = _admin(db_sync)
    sch = ScholarshipType(code="regen_excl", name="RegenExcl", description="x")
    db_sync.add(sch)
    db_sync.flush()
    cfg = _config(db_sync, sch, code="REGENEXCL-115")
    ranking = _ranking(db_sync, sch)

    kept = _application(db_sync, _student(db_sync, "ex_a"), sch, cfg, app_id="APP-EX-A", std_code="115A")
    returned = _application(db_sync, _student(db_sync, "ex_b"), sch, cfg, app_id="APP-EX-B", std_code="115B")
    _allocate(db_sync, ranking, kept, cfg)
    _allocate(db_sync, ranking, returned, cfg, rank_position=2)
    db_sync.commit()

    roster = _generate(db_sync, sch, admin)
    roster_id = roster.id
    assert roster.qualified_count == 2

    # Admin excludes one student the way POST /{roster_id}/items/{id}/exclude does.
    excluded_item = next(i for i in _items(db_sync, roster_id) if i.application_id == returned.id)
    excluded_item.is_included = False
    excluded_item.exclusion_reason = "學生繳回: 已退款"
    db_sync.commit()

    with patch(EXPORT_TARGET):
        result = RosterRegenerationService(db_sync).regenerate_roster(roster_id=roster_id, admin_user_id=admin.id)

    assert result.rebuilt_items == 2
    assert result.preserved_exclusions == 1

    by_app = {i.application_id: i for i in _items(db_sync, roster_id)}
    assert by_app[kept.id].is_included is True
    assert by_app[returned.id].is_included is False
    assert by_app[returned.id].exclusion_reason == "學生繳回: 已退款"
    # 人數/金額 must reflect the preserved exclusion, not the raw rebuild.
    assert result.roster.qualified_count == 1
    assert int(result.roster.total_amount) == 50000


def test_batch_force_regenerate_also_preserves_manual_exclusion(db_sync):
    """The batch 重新生成造冊 button (手動分發 panel) goes through
    generate_rosters_from_distribution(force_regenerate=True), NOT through
    RosterRegenerationService — so preservation must live in the shared base or
    that button silently resurrects every 排除 while its dialog promises it won't."""
    admin = _admin(db_sync)
    sch = ScholarshipType(code="batch_excl", name="BatchExcl", description="x")
    db_sync.add(sch)
    db_sync.flush()
    cfg = _config(db_sync, sch, code="BATCHEXCL-115")
    ranking = _ranking(db_sync, sch)

    kept = _application(db_sync, _student(db_sync, "bx_a"), sch, cfg, app_id="APP-BX-A", std_code="115A")
    returned = _application(db_sync, _student(db_sync, "bx_b"), sch, cfg, app_id="APP-BX-B", std_code="115B")
    _allocate(db_sync, ranking, kept, cfg)
    _allocate(db_sync, ranking, returned, cfg, rank_position=2)
    db_sync.commit()

    roster = _generate(db_sync, sch, admin)
    roster_id = roster.id

    excluded_item = next(i for i in _items(db_sync, roster_id) if i.application_id == returned.id)
    excluded_item.is_included = False
    excluded_item.exclusion_reason = "學生放棄"
    excluded_item.bank_manual_review_notes = "人工核對無誤"
    db_sync.commit()

    forced = RosterService(db_sync).generate_rosters_from_distribution(
        scholarship_type_id=sch.id,
        academic_year=115,
        semester="first",
        created_by_user_id=admin.id,
        student_verification_enabled=False,
        force_regenerate=True,
    )
    assert len(forced.created) == 1

    by_app = {i.application_id: i for i in _items(db_sync, roster_id)}
    assert by_app[returned.id].is_included is False
    assert by_app[returned.id].exclusion_reason == "學生放棄"
    assert by_app[returned.id].bank_manual_review_notes == "人工核對無誤"
    assert by_app[kept.id].is_included is True
    # 人數/金額 must reflect the preserved exclusion.
    assert forced.created[0].qualified_count == 1
    # A successful rebuild + re-export leaves no stale-Excel hint behind.
    assert forced.created[0].excel_stale is False


def test_regenerate_reinstates_a_reconcile_removed_student_who_is_allocated_again(db_sync):
    """比對分發移除 records「不在分發名單」— a derived fact, not a verdict about the
    student. Once the student is allocated again the reason is false, so the
    rebuild must re-include them rather than freeze them out."""
    admin = _admin(db_sync)
    sch = ScholarshipType(code="regen_rec", name="RegenRec", description="x")
    db_sync.add(sch)
    db_sync.flush()
    cfg = _config(db_sync, sch, code="REGENREC-115")
    ranking = _ranking(db_sync, sch)
    app = _application(db_sync, _student(db_sync, "rc_a"), sch, cfg, app_id="APP-RC-A", std_code="115A")
    _allocate(db_sync, ranking, app, cfg)
    db_sync.commit()

    roster = _generate(db_sync, sch, admin)
    roster_id = roster.id

    item = _items(db_sync, roster_id)[0]
    item.is_included = False
    item.exclusion_reason = f"{MANUAL_REMOVAL_PREFIX_RECONCILE}：不在分發名單"
    db_sync.commit()

    with patch(EXPORT_TARGET):
        result = RosterRegenerationService(db_sync).regenerate_roster(roster_id=roster_id, admin_user_id=admin.id)

    assert result.preserved_exclusions == 0
    rebuilt = _items(db_sync, roster_id)[0]
    assert rebuilt.is_included is True
    assert rebuilt.exclusion_reason is None


def test_regenerate_reports_newly_excluded_students(db_sync):
    """A student who was included but fails today's verdicts must be counted and
    reported — silently dropping them would also silently undo an admin 回復."""
    admin = _admin(db_sync)
    sch = ScholarshipType(code="regen_new", name="RegenNew", description="x")
    db_sync.add(sch)
    db_sync.flush()
    cfg = _config(db_sync, sch, code="REGENNEW-115")
    ranking = _ranking(db_sync, sch)
    app = _application(db_sync, _student(db_sync, "nx_a"), sch, cfg, app_id="APP-NX-A", std_code="115A")
    _allocate(db_sync, ranking, app, cfg)
    db_sync.commit()

    roster = _generate(db_sync, sch, admin)
    roster_id = roster.id
    assert _items(db_sync, roster_id)[0].is_included is True

    # Re-verify against SIS, which now reports the student as graduated.
    with patch(EXPORT_TARGET), patch("app.services.roster_service.StudentVerificationService") as svs:
        svs.return_value.verify_student.return_value = {
            "status": StudentVerificationStatus.GRADUATED,
            "message": "已畢業",
        }
        result = RosterRegenerationService(db_sync).regenerate_roster(
            roster_id=roster_id, admin_user_id=admin.id, student_verification_enabled=True
        )

    assert result.newly_excluded == 1
    assert result.preserved_exclusions == 0
    assert _items(db_sync, roster_id)[0].is_included is False


def test_regenerate_does_not_preserve_automatic_exclusions(db_sync):
    """Only HUMAN decisions survive. A rule/學籍 exclusion is a derived verdict and
    must be recomputed — otherwise a student who has since become eligible could
    never be re-included by a rebuild."""
    admin = _admin(db_sync)
    sch = ScholarshipType(code="regen_auto", name="RegenAuto", description="x")
    db_sync.add(sch)
    db_sync.flush()
    cfg = _config(db_sync, sch, code="REGENAUTO-115")
    ranking = _ranking(db_sync, sch)
    app = _application(db_sync, _student(db_sync, "auto_a"), sch, cfg, app_id="APP-AUTO-A", std_code="115A")
    _allocate(db_sync, ranking, app, cfg)
    db_sync.commit()

    roster = _generate(db_sync, sch, admin)
    roster_id = roster.id

    item = _items(db_sync, roster_id)[0]
    item.is_included = False
    item.exclusion_reason = "學籍驗證未通過：已畢業"
    db_sync.commit()

    with patch(EXPORT_TARGET):
        result = RosterRegenerationService(db_sync).regenerate_roster(roster_id=roster_id, admin_user_id=admin.id)

    assert result.preserved_exclusions == 0
    rebuilt = _items(db_sync, roster_id)[0]
    assert rebuilt.is_included is True
    assert rebuilt.exclusion_reason is None


def test_regenerate_preserves_bank_review_state(db_sync):
    """Human bank-account review verdicts are not re-derivable by a rebuild."""
    admin = _admin(db_sync)
    sch = ScholarshipType(code="regen_bank", name="RegenBank", description="x")
    db_sync.add(sch)
    db_sync.flush()
    cfg = _config(db_sync, sch, code="REGENBANK-115")
    ranking = _ranking(db_sync, sch)
    app = _application(db_sync, _student(db_sync, "bank_a"), sch, cfg, app_id="APP-BANK-A", std_code="115A")
    _allocate(db_sync, ranking, app, cfg)
    db_sync.commit()

    roster = _generate(db_sync, sch, admin)
    roster_id = roster.id

    item = _items(db_sync, roster_id)[0]
    item.bank_account_number_status = "verified"
    item.bank_manual_review_notes = "人工核對無誤"
    db_sync.commit()

    with patch(EXPORT_TARGET):
        RosterRegenerationService(db_sync).regenerate_roster(roster_id=roster_id, admin_user_id=admin.id)

    rebuilt = _items(db_sync, roster_id)[0]
    assert rebuilt.bank_account_number_status == "verified"
    assert rebuilt.bank_manual_review_notes == "人工核對無誤"


def test_regenerate_keeps_approved_renewals(db_sync):
    """續領 students never own a CollegeRankingItem, so a distribution-only
    rebuild would silently drop them from the roster."""
    admin = _admin(db_sync)
    sch = ScholarshipType(code="regen_renew", name="RegenRenew", description="x")
    db_sync.add(sch)
    db_sync.flush()
    cfg = _config(db_sync, sch, code="REGENRENEW-115")
    ranking = _ranking(db_sync, sch)

    new_app = _application(db_sync, _student(db_sync, "rn_a"), sch, cfg, app_id="APP-RN-A", std_code="115A")
    _allocate(db_sync, ranking, new_app, cfg)
    renewal = _application(
        db_sync, _student(db_sync, "rn_b"), sch, cfg, app_id="APP-RN-B", std_code="115B", is_renewal=True
    )
    db_sync.commit()

    roster = _generate(db_sync, sch, admin)
    roster_id = roster.id
    assert {i.application_id for i in _items(db_sync, roster_id)} == {new_app.id, renewal.id}

    with patch(EXPORT_TARGET):
        result = RosterRegenerationService(db_sync).regenerate_roster(roster_id=roster_id, admin_user_id=admin.id)

    assert result.rebuilt_items == 2
    assert {i.application_id for i in _items(db_sync, roster_id)} == {new_app.id, renewal.id}


def test_regenerate_clears_excel_stale_on_successful_export(db_sync):
    admin = _admin(db_sync)
    sch = ScholarshipType(code="regen_xls", name="RegenXls", description="x")
    db_sync.add(sch)
    db_sync.flush()
    cfg = _config(db_sync, sch, code="REGENXLS-115")
    ranking = _ranking(db_sync, sch)
    app = _application(db_sync, _student(db_sync, "xls_a"), sch, cfg, app_id="APP-XLS-A", std_code="115A")
    _allocate(db_sync, ranking, app, cfg)
    db_sync.commit()

    roster = _generate(db_sync, sch, admin)
    roster_id = roster.id
    roster.excel_stale = True
    db_sync.commit()

    with patch(EXPORT_TARGET):
        result = RosterRegenerationService(db_sync).regenerate_roster(roster_id=roster_id, admin_user_id=admin.id)

    assert result.excel_exported is True
    assert result.roster.excel_stale is False


def test_regenerate_marks_excel_stale_when_export_fails(db_sync):
    """A failed re-export must not be swallowed as a clean roster: the file on
    MinIO no longer matches the items, so the 需重新匯出 hint has to stay on."""
    admin = _admin(db_sync)
    sch = ScholarshipType(code="regen_xfail", name="RegenXFail", description="x")
    db_sync.add(sch)
    db_sync.flush()
    cfg = _config(db_sync, sch, code="REGENXFAIL-115")
    ranking = _ranking(db_sync, sch)
    app = _application(db_sync, _student(db_sync, "xf_a"), sch, cfg, app_id="APP-XF-A", std_code="115A")
    _allocate(db_sync, ranking, app, cfg)
    db_sync.commit()

    roster = _generate(db_sync, sch, admin)
    roster_id = roster.id

    with patch(EXPORT_TARGET) as export_cls:
        export_cls.return_value.export_roster_to_excel.side_effect = RuntimeError("minio down")
        result = RosterRegenerationService(db_sync).regenerate_roster(roster_id=roster_id, admin_user_id=admin.id)

    # The rebuild itself still succeeded — only the file is out of date.
    assert result.excel_exported is False
    assert result.roster.status == RosterStatus.COMPLETED
    assert result.roster.excel_stale is True


def test_regenerate_refuses_locked_roster(db_sync):
    admin = _admin(db_sync)
    sch = ScholarshipType(code="regen_lock", name="RegenLock", description="x")
    db_sync.add(sch)
    db_sync.flush()
    cfg = _config(db_sync, sch, code="REGENLOCK-115")
    ranking = _ranking(db_sync, sch)
    app = _application(db_sync, _student(db_sync, "lk_a"), sch, cfg, app_id="APP-LK-A", std_code="115A")
    _allocate(db_sync, ranking, app, cfg)
    db_sync.commit()

    roster = _generate(db_sync, sch, admin)
    roster.status = RosterStatus.LOCKED
    db_sync.commit()

    with pytest.raises(RosterLockedError) as exc:
        RosterRegenerationService(db_sync).regenerate_roster(roster_id=roster.id, admin_user_id=admin.id)
    assert "已鎖定" in str(exc.value)
    # Items must survive an refused regenerate untouched.
    assert len(_items(db_sync, roster.id)) == 1


def test_regenerate_unknown_roster_raises_not_found(db_sync):
    admin = _admin(db_sync)
    with pytest.raises(RosterNotFoundError):
        RosterRegenerationService(db_sync).regenerate_roster(roster_id=999999, admin_user_id=admin.id)


def test_regenerate_refuses_when_distribution_is_empty(db_sync):
    """Never silently blank a roster: if the distribution no longer holds anyone
    for this group, say so and leave the existing items alone."""
    admin = _admin(db_sync)
    sch = ScholarshipType(code="regen_empty", name="RegenEmpty", description="x")
    db_sync.add(sch)
    db_sync.flush()
    cfg = _config(db_sync, sch, code="REGENEMPTY-115")
    ranking = _ranking(db_sync, sch)
    app = _application(db_sync, _student(db_sync, "em_a"), sch, cfg, app_id="APP-EM-A", std_code="115A")
    ranking_item = _allocate(db_sync, ranking, app, cfg)
    db_sync.commit()

    roster = _generate(db_sync, sch, admin)
    roster_id = roster.id

    ranking_item.is_allocated = False
    db_sync.commit()

    with pytest.raises(ValueError) as exc:
        RosterRegenerationService(db_sync).regenerate_roster(roster_id=roster_id, admin_user_id=admin.id)
    assert "沒有可造冊的資料" in str(exc.value)
    assert len(_items(db_sync, roster_id)) == 1
    assert db_sync.get(PaymentRoster, roster_id).status == RosterStatus.COMPLETED


def test_regenerate_refuses_when_every_member_is_no_longer_approved(db_sync):
    """The emptiness guard must run against the APPROVED set, not the raw
    distribution ids — an allocated-but-no-longer-approved application would
    otherwise blank the roster, mark it COMPLETED and export an empty Excel."""
    admin = _admin(db_sync)
    sch = ScholarshipType(code="regen_unappr", name="RegenUnappr", description="x")
    db_sync.add(sch)
    db_sync.flush()
    cfg = _config(db_sync, sch, code="REGENUNAPPR-115")
    ranking = _ranking(db_sync, sch)
    app = _application(db_sync, _student(db_sync, "ua_a"), sch, cfg, app_id="APP-UA-A", std_code="115A")
    _allocate(db_sync, ranking, app, cfg)
    db_sync.commit()

    roster = _generate(db_sync, sch, admin)
    roster_id = roster.id

    # Application reverted (回發) without the ranking item being de-allocated.
    app.status = ApplicationStatus.under_review
    db_sync.commit()

    with pytest.raises(ValueError) as exc:
        RosterRegenerationService(db_sync).regenerate_roster(roster_id=roster_id, admin_user_id=admin.id)
    assert "沒有可造冊的資料" in str(exc.value)
    assert len(_items(db_sync, roster_id)) == 1
    assert db_sync.get(PaymentRoster, roster_id).status == RosterStatus.COMPLETED


def test_regenerate_reports_students_dropped_from_the_distribution(db_sync):
    """A student who left the 名單 entirely is in neither rebuilt_items nor
    failed_items, so without its own counter they would vanish in silence."""
    admin = _admin(db_sync)
    sch = ScholarshipType(code="regen_drop", name="RegenDrop", description="x")
    db_sync.add(sch)
    db_sync.flush()
    cfg = _config(db_sync, sch, code="REGENDROP-115")
    ranking = _ranking(db_sync, sch)
    kept = _application(db_sync, _student(db_sync, "dp_a"), sch, cfg, app_id="APP-DP-A", std_code="115A")
    leaving = _application(db_sync, _student(db_sync, "dp_b"), sch, cfg, app_id="APP-DP-B", std_code="115B")
    _allocate(db_sync, ranking, kept, cfg)
    leaving_item = _allocate(db_sync, ranking, leaving, cfg, rank_position=2)
    db_sync.commit()

    roster = _generate(db_sync, sch, admin)
    roster_id = roster.id
    assert len(_items(db_sync, roster_id)) == 2

    leaving_item.is_allocated = False
    db_sync.commit()

    with patch(EXPORT_TARGET):
        result = RosterRegenerationService(db_sync).regenerate_roster(roster_id=roster_id, admin_user_id=admin.id)

    assert result.rebuilt_items == 1
    assert result.dropped_members == 1
    assert {i.application_id for i in _items(db_sync, roster_id)} == {kept.id}


def test_totals_always_match_the_item_rows(db_sync):
    """total_applications must equal count(items): folding a `failed` count into
    the item-derived totals makes the roster's 人數 jump back on the next
    reconcile/排除, which recomputes purely from the rows."""
    admin = _admin(db_sync)
    sch = ScholarshipType(code="regen_tot", name="RegenTot", description="x")
    db_sync.add(sch)
    db_sync.flush()
    cfg = _config(db_sync, sch, code="REGENTOT-115")
    ranking = _ranking(db_sync, sch)
    good = _application(db_sync, _student(db_sync, "tt_a"), sch, cfg, app_id="APP-TT-A", std_code="115A")
    broken = _application(db_sync, _student(db_sync, "tt_b"), sch, cfg, app_id="APP-TT-B", std_code="115B")
    _allocate(db_sync, ranking, good, cfg)
    _allocate(db_sync, ranking, broken, cfg, rank_position=2)
    db_sync.commit()

    roster = _generate(db_sync, sch, admin)
    roster_id = roster.id

    # Corrupt one snapshot so _verify_and_create_item raises for that row.
    broken.student_data = {"std_stdcode": None, "std_cname": None}
    db_sync.commit()

    with patch(EXPORT_TARGET):
        result = RosterRegenerationService(db_sync).regenerate_roster(roster_id=roster_id, admin_user_id=admin.id)

    assert result.failed_items == 1
    assert result.rebuilt_items == 1
    rebuilt_roster = db_sync.get(PaymentRoster, roster_id)
    assert rebuilt_roster.total_applications == len(_items(db_sync, roster_id))
    assert rebuilt_roster.disqualified_count == (rebuilt_roster.total_applications - rebuilt_roster.qualified_count)


def test_whole_period_force_regenerate_preserves_manual_exclusion(db_sync):
    """generate_roster(force_regenerate=True) — the 立即產生/重新產生 path — wipes
    items too, so it must honour the same preservation invariant."""
    admin = _admin(db_sync)
    sch = ScholarshipType(code="wp_excl", name="WholePeriodExcl", description="x")
    db_sync.add(sch)
    db_sync.flush()
    cfg = _config(db_sync, sch, code="WPEXCL-115")
    app = _application(db_sync, _student(db_sync, "wp_a"), sch, cfg, app_id="APP-WP-A", std_code="115A")
    db_sync.commit()

    svc = RosterService(db_sync)
    kwargs = dict(
        scholarship_configuration_id=cfg.id,
        period_label="115",
        roster_cycle=RosterCycle.YEARLY,
        academic_year=115,
        created_by_user_id=admin.id,
        student_verification_enabled=False,
    )
    roster = svc.generate_roster(**kwargs)
    roster_id = roster.id
    assert len(_items(db_sync, roster_id)) == 1

    item = _items(db_sync, roster_id)[0]
    item.is_included = False
    item.exclusion_reason = "學生繳回: 已退款"
    item.bank_account_holder_status = "verified"
    db_sync.commit()

    svc.generate_roster(**kwargs, force_regenerate=True)

    rebuilt = _items(db_sync, roster_id)[0]
    assert rebuilt.application_id == app.id
    assert rebuilt.is_included is False
    assert rebuilt.exclusion_reason == "學生繳回: 已退款"
    assert rebuilt.bank_account_holder_status == "verified"
