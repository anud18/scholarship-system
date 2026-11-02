from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.application import Application, ApplicationStatus
from app.models.application_field import ApplicationField
from app.models.audit_log import AuditLog
from app.models.payment_roster import (
    PaymentRoster,
    PaymentRosterItem,
    RosterCycle,
    RosterStatus,
    RosterTriggerType,
)
from app.models.roster_audit import RosterAuditAction, RosterAuditLog
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType, SubTypeSelectionMode
from app.models.user import User, UserRole, UserType
from app.services.excel_export_service import ExcelExportService
from app.services.staff_form_edit import RosterAccountAction, RosterAccountSync, RosterItemRef

URL = "/api/v1/applications/{id}/form-fields"
OLD_ACCOUNT = "11111111111111"
NEW_ACCOUNT = "00012345678901"
LEAKED_ACCOUNT = "99999999999999"
SAVED = "表單內容已更新"
SYNCED_ONE = "；已同步更新 1 份造冊的郵局帳號，請至造冊管理重新匯出 Excel"
RESET_BANK = {"bank_account_number_status": None, "bank_account_holder_status": None, "bank_verification_details": None}

REVIEWED_BANK = {
    "bank_account_number_status": "verified",
    "bank_account_holder_status": "verified",
    "bank_verification_details": {"manual_review": {"account_number": {"status": "verified"}}},
    "bank_manual_review_notes": "存摺已核對",
}


@pytest_asyncio.fixture
async def login():
    from app.core.security import get_current_user
    from app.main import app

    def _login(user: User) -> None:
        async def _override():
            return user

        app.dependency_overrides[get_current_user] = _override

    yield _login
    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def users(db):
    rows = {
        "admin": User(
            nycu_id="rs_admin",
            name="承辦人",
            email="rs_admin@test.edu",
            role=UserRole.admin,
            user_type=UserType.employee,
        ),
        "college": User(
            nycu_id="rs_eng",
            name="ENG",
            email="rs_eng@test.edu",
            role=UserRole.college,
            user_type=UserType.employee,
            college_code="ENG",
        ),
        "student": User(
            nycu_id="S880001",
            name="Student",
            email="rs_stu@test.edu",
            role=UserRole.student,
            user_type=UserType.student,
        ),
    }
    db.add_all(rows.values())
    await db.commit()
    for user in rows.values():
        await db.refresh(user)
    return rows


@pytest_asyncio.fixture
async def config(db):
    scholarship = ScholarshipType(code="roster_sync_scholarship", name="造冊同步測試獎學金")
    db.add(scholarship)
    db.add(
        ApplicationField(
            scholarship_type=scholarship.code,
            field_name="contact_phone",
            field_label="聯絡電話",
            field_type="text",
            is_required=True,
            is_active=True,
        )
    )
    await db.commit()
    await db.refresh(scholarship)
    row = ScholarshipConfiguration(
        scholarship_type_id=scholarship.id,
        config_code="roster_sync_cfg",
        config_name="造冊同步測試設定",
        academic_year=115,
        requires_professor_recommendation=False,
        requires_college_review=False,
        amount=40000,
        is_active=True,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


def _form(account: str | None = OLD_ACCOUNT, **other_accounts: str) -> dict:
    fields = {"contact_phone": {"field_id": "contact_phone", "field_type": "text", "value": "0912345678"}}
    accounts = {"account_number": account, **other_accounts}
    for key, value in accounts.items():
        if value is not None:
            fields[key] = {"field_id": key, "field_type": "text", "value": value}
    return {"fields": fields, "documents": []}


@pytest_asyncio.fixture
async def application(db, users, config) -> Application:
    return await _make_application(db, users, config, _form())


async def _make_application(db, users, config, form: dict) -> Application:
    row = Application(
        app_id="APP-115-0-08001",
        user_id=users["student"].id,
        scholarship_type_id=config.scholarship_type_id,
        scholarship_configuration_id=config.id,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        status=ApplicationStatus.approved,
        academic_year=115,
        semester="yearly",
        student_data={"std_stdcode": "S880001", "std_cname": "王小明", "std_academyno": "ENG"},
        submitted_form_data=form,
        agree_terms=True,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def _make_roster(
    db,
    users,
    config,
    application,
    code: str,
    status: RosterStatus,
    bank_account: str | None = OLD_ACCOUNT,
    exclusion_reason: str | None = None,
) -> PaymentRosterItem:
    roster = PaymentRoster(
        roster_code=code,
        scholarship_configuration_id=config.id,
        period_label=code,
        academic_year=115,
        roster_cycle=RosterCycle.YEARLY,
        status=status,
        trigger_type=RosterTriggerType.MANUAL,
        created_by=users["admin"].id,
        total_applications=1,
        qualified_count=1,
        disqualified_count=0,
        total_amount=40000,
    )
    db.add(roster)
    await db.flush()
    item = PaymentRosterItem(
        roster_id=roster.id,
        application_id=application.id,
        student_id_number="A123456789",
        student_number="S880001",
        student_name="王小明",
        bank_account=bank_account,
        scholarship_name="造冊同步測試獎學金",
        scholarship_amount=40000,
        is_included=exclusion_reason is None,
        exclusion_reason=exclusion_reason,
        **REVIEWED_BANK,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def _edit_account(client, application, account=NEW_ACCOUNT):
    return await client.patch(URL.format(id=application.id), json={"fields": {"postal_account": account}})


async def _reload(db, item: PaymentRosterItem) -> PaymentRosterItem:
    await db.refresh(item)
    await db.refresh(item, attribute_names=["roster"])
    await db.refresh(item.roster)
    return item


async def _roster_audits(db) -> list:
    return (await db.execute(select(RosterAuditLog).order_by(RosterAuditLog.id))).scalars().all()


async def _application_audit(db, application) -> AuditLog:
    stmt = select(AuditLog).where(AuditLog.resource_id == str(application.id), AuditLog.action == "update")
    return (await db.execute(stmt)).scalar_one()


def _ref(item: PaymentRosterItem, code: str) -> dict:
    return {"roster_id": item.roster_id, "roster_code": code, "item_id": item.id}


def _assert_untouched(item: PaymentRosterItem, account: str = OLD_ACCOUNT) -> None:
    assert item.bank_account == account
    assert {key: getattr(item, key) for key in REVIEWED_BANK} == REVIEWED_BANK
    assert item.roster.excel_stale is False


def _assert_points_at_new_account(item: PaymentRosterItem) -> None:
    assert item.bank_account == NEW_ACCOUNT
    assert {key: getattr(item, key) for key in RESET_BANK} == RESET_BANK
    assert item.bank_manual_review_notes == REVIEWED_BANK["bank_manual_review_notes"]


@pytest.mark.api
class TestAccountEditFollowsIntoRosters:
    @pytest.mark.parametrize(
        "status", [RosterStatus.DRAFT, RosterStatus.PROCESSING, RosterStatus.COMPLETED, RosterStatus.FAILED]
    )
    async def test_unlocked_roster_takes_the_new_account(self, client, db, login, users, config, application, status):
        item = await _make_roster(db, users, config, application, "ROSTER-OPEN", status)
        login(users["admin"])

        response = await _edit_account(client, application)

        assert response.status_code == 200, response.text
        assert response.json()["message"] == SAVED + SYNCED_ONE

        item = await _reload(db, item)
        _assert_points_at_new_account(item)
        assert item.is_included is True
        assert item.scholarship_amount == Decimal("40000")
        assert item.roster.status is status
        assert item.roster.excel_stale is True

        (audit,) = await _roster_audits(db)
        assert audit.roster_id == item.roster_id
        assert audit.action is RosterAuditAction.ITEM_UPDATE
        assert (audit.user_id, audit.user_name, audit.user_role) == (users["admin"].id, "承辦人", "admin")
        assert audit.old_values == {
            "bank_account": OLD_ACCOUNT,
            "bank_account_number_status": "verified",
            "bank_account_holder_status": "verified",
            "bank_verification_details": REVIEWED_BANK["bank_verification_details"],
        }
        assert audit.new_values == {"bank_account": NEW_ACCOUNT, **RESET_BANK}
        assert audit.audit_metadata["application_id"] == application.id
        assert audit.audit_metadata["student_id"] == "S880001"
        assert audit.audit_metadata["source"] == "staff_form_edit"
        assert application.app_id in audit.description

        meta = (await _application_audit(db, application)).meta_data
        assert meta["roster_items_updated"] == [_ref(item, "ROSTER-OPEN")]
        assert "locked_rosters_unchanged" not in meta

    async def test_college_staff_edit_is_attributed_to_them(self, client, db, login, users, config, application):
        await _make_roster(db, users, config, application, "ROSTER-OPEN", RosterStatus.COMPLETED)
        login(users["college"])

        response = await _edit_account(client, application)

        assert response.status_code == 200, response.text
        (audit,) = await _roster_audits(db)
        assert (audit.user_id, audit.user_role) == (users["college"].id, "college")

    async def test_locked_roster_keeps_what_was_paid(self, client, db, login, users, config, application):
        item = await _make_roster(db, users, config, application, "ROSTER-114-LOCKED", RosterStatus.LOCKED)
        login(users["admin"])

        response = await _edit_account(client, application)

        assert response.status_code == 200, response.text
        assert response.json()["message"] == (
            SAVED + "；1 份已鎖定的造冊（ROSTER-114-LOCKED）未變更，如需更正請解鎖後重新產生"
        )
        _assert_untouched(await _reload(db, item))
        assert item.roster.status is RosterStatus.LOCKED
        assert await _roster_audits(db) == []

        meta = (await _application_audit(db, application)).meta_data
        assert meta["locked_rosters_unchanged"] == [_ref(item, "ROSTER-114-LOCKED")]
        assert "roster_items_updated" not in meta

    async def test_open_and_locked_rosters_report_both(self, client, db, login, users, config, application):
        locked = await _make_roster(db, users, config, application, "ROSTER-A-LOCKED", RosterStatus.LOCKED)
        draft = await _make_roster(db, users, config, application, "ROSTER-B-DRAFT", RosterStatus.DRAFT)
        login(users["admin"])

        response = await _edit_account(client, application)

        assert response.status_code == 200, response.text
        assert response.json()["message"] == (
            SAVED + SYNCED_ONE + "；1 份已鎖定的造冊（ROSTER-A-LOCKED）未變更，如需更正請解鎖後重新產生"
        )
        _assert_points_at_new_account(await _reload(db, draft))
        _assert_untouched(await _reload(db, locked))
        assert [audit.roster_id for audit in await _roster_audits(db)] == [draft.roster_id]

        meta = (await _application_audit(db, application)).meta_data
        assert meta["roster_items_updated"] == [_ref(draft, "ROSTER-B-DRAFT")]
        assert meta["locked_rosters_unchanged"] == [_ref(locked, "ROSTER-A-LOCKED")]

    async def test_application_in_no_roster_gets_the_plain_message(self, client, db, login, users, application):
        login(users["admin"])

        response = await _edit_account(client, application)

        assert response.status_code == 200, response.text
        assert response.json()["message"] == SAVED
        meta = (await _application_audit(db, application)).meta_data
        assert "roster_items_updated" not in meta
        assert "locked_rosters_unchanged" not in meta

    async def test_other_field_edits_leave_rosters_alone(self, client, db, login, users, config, application):
        item = await _make_roster(db, users, config, application, "ROSTER-OPEN", RosterStatus.COMPLETED)
        login(users["admin"])

        response = await client.patch(URL.format(id=application.id), json={"fields": {"contact_phone": "0987654321"}})

        assert response.status_code == 200, response.text
        assert response.json()["message"] == SAVED
        _assert_untouched(await _reload(db, item))
        assert await _roster_audits(db) == []

    async def test_item_already_on_the_new_account_is_not_reported(self, client, db, login, users, config, application):
        await _make_roster(db, users, config, application, "ROSTER-L", RosterStatus.LOCKED, bank_account=NEW_ACCOUNT)
        login(users["admin"])

        response = await _edit_account(client, application)

        assert response.status_code == 200, response.text
        assert response.json()["message"] == SAVED
        assert await _roster_audits(db) == []

    async def test_item_missing_an_account_exports_the_added_one(self, client, db, login, users, config):
        application = await _make_application(db, users, config, _form(account=None))
        item = await _make_roster(db, users, config, application, "ROSTER-OPEN", RosterStatus.COMPLETED, None)
        login(users["admin"])

        response = await _edit_account(client, application)

        assert response.status_code == 200, response.text
        item = await _reload(db, item)
        roster = item.roster
        assert (roster.total_applications, roster.qualified_count, roster.total_amount) == (1, 1, Decimal("40000"))
        assert "缺少郵局帳號資訊" not in item.generate_excel_remarks(roster.period_label, "cfg")

        (row,), (fills,) = ExcelExportService()._prepare_excel_data(roster, [item])
        assert row["帳號"] == NEW_ACCOUNT
        assert "缺銀行資訊" not in row["說明"]
        assert ExcelExportService.COL_BANK_ACCOUNT not in fills

    async def test_rejected_account_leaves_rosters_alone(self, client, db, login, users, config, application):
        item = await _make_roster(db, users, config, application, "ROSTER-OPEN", RosterStatus.COMPLETED)
        login(users["admin"])

        response = await _edit_account(client, application, account="12345")

        assert response.status_code == 422
        _assert_untouched(await _reload(db, item))
        assert await _roster_audits(db) == []

    async def test_cleared_account_never_writes_a_leftover_one(self, client, db, login, users, config):
        db.add(
            ApplicationField(
                scholarship_type="roster_sync_scholarship",
                field_name="postal_account",
                fixed_key="postal_account",
                field_label="郵局帳號",
                field_type="text",
                is_required=False,
                is_active=True,
            )
        )
        application = await _make_application(db, users, config, _form(postal_account=LEAKED_ACCOUNT))
        item = await _make_roster(db, users, config, application, "ROSTER-OPEN", RosterStatus.COMPLETED)
        login(users["admin"])

        response = await _edit_account(client, application, account="")

        assert response.status_code == 200, response.text
        assert response.json()["message"] == SAVED
        _assert_untouched(await _reload(db, item))
        assert await _roster_audits(db) == []

    async def test_format_only_correction_is_not_a_change(self, client, db, login, users, config):
        dashed = "0001234-5678901"
        application = await _make_application(db, users, config, _form(account=dashed))
        item = await _make_roster(db, users, config, application, "ROSTER-OPEN", RosterStatus.COMPLETED, dashed)
        login(users["admin"])

        response = await _edit_account(client, application, account=NEW_ACCOUNT)

        assert response.status_code == 200, response.text
        assert response.json()["message"] == SAVED
        _assert_untouched(await _reload(db, item), account=dashed)
        assert await _roster_audits(db) == []

    async def test_manually_removed_item_follows_quietly(self, client, db, login, users, config, application):
        removed = await _make_roster(
            db, users, config, application, "ROSTER-OPEN", RosterStatus.COMPLETED, exclusion_reason="比對分發移除：x"
        )
        login(users["admin"])

        response = await _edit_account(client, application)

        assert response.status_code == 200, response.text
        assert response.json()["message"] == SAVED
        removed = await _reload(db, removed)
        _assert_points_at_new_account(removed)
        assert removed.is_included is False
        assert removed.roster.excel_stale is False
        assert [audit.roster_id for audit in await _roster_audits(db)] == [removed.roster_id]

        meta = (await _application_audit(db, application)).meta_data
        assert meta["removed_roster_items_updated"] == [_ref(removed, "ROSTER-OPEN")]
        assert "roster_items_updated" not in meta

    async def test_ineligible_item_still_listed_in_the_excel_is_synced(
        self, client, db, login, users, config, application
    ):
        excluded = await _make_roster(
            db, users, config, application, "ROSTER-OPEN", RosterStatus.COMPLETED, exclusion_reason="學籍驗證未通過"
        )
        login(users["admin"])

        response = await _edit_account(client, application)

        assert response.status_code == 200, response.text
        assert response.json()["message"] == SAVED + SYNCED_ONE
        excluded = await _reload(db, excluded)
        _assert_points_at_new_account(excluded)
        assert excluded.roster.excel_stale is True
        await db.refresh(excluded.roster, attribute_names=["items"])
        (row,), _ = ExcelExportService()._prepare_excel_data(
            excluded.roster, ExcelExportService()._get_roster_items(excluded.roster, include_excluded=False)
        )
        assert (row["帳號"], row[ExcelExportService.COL_INCLUDED]) == (NEW_ACCOUNT, "否")


class TestRosterAccountDecision:
    def test_long_locked_lists_are_shortened_and_counted_per_roster(self):
        refs = tuple(RosterItemRef(roster_id=n, roster_code=f"R-{n:02d}", item_id=n) for n in range(1, 13))

        clause = RosterAccountSync(items={RosterAccountAction.KEPT_LOCKED: refs}).message_clause

        assert clause == "；12 份已鎖定的造冊（R-01、R-02、R-03…）未變更，如需更正請解鎖後重新產生"

    def test_nothing_touched_adds_no_clause(self):
        assert RosterAccountSync().message_clause == ""
        assert RosterAccountSync().audit_meta() == {}
