from copy import deepcopy
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.exceptions import ValidationError
from app.models.application import Application, ApplicationStatus
from app.models.application_field import ApplicationField
from app.models.audit_log import AuditLog
from app.models.notification import Notification
from app.models.review import ApplicationReview
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType, SubTypeSelectionMode
from app.models.user import User, UserRole, UserType
from app.models.user_profile import UserProfile, UserProfileHistory
from app.schemas.application_field import ApplicationFieldResponse
from app.services.staff_form_edit import (
    ProfessorFacts,
    ReassignmentOutcome,
    advisor_nycu_id_changed,
    apply_staff_form_edit,
    build_editable_form_spec,
    decide_professor_reassignment,
)

URL = "/api/v1/applications/{id}/form-fields"
SCHOLARSHIP_CODE = "staff_edit_scholarship"

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)

ACCOUNT_A = "11111111111111"
ACCOUNT_B = "22222222222222"
ACCOUNT_C = "33333333333333"
ACCOUNT_D = "44444444444444"
NEW_ACCOUNT = "00012345678901"


def _definition(field_name: str, field_type: str = "text", **overrides) -> ApplicationFieldResponse:
    values = {
        "id": 1,
        "scholarship_type": SCHOLARSHIP_CODE,
        "field_name": field_name,
        "field_label": f"{field_name} 標籤",
        "field_type": field_type,
        "created_at": _NOW,
        "updated_at": _NOW,
        **overrides,
    }
    return ApplicationFieldResponse(**values)


BASE_DEFINITIONS = [
    _definition("contact_phone", is_required=True, validation_rules={"pattern": r"09\d{8}"}),
    _definition("remark", "textarea", max_length=10),
    _definition("household_size", "number", min_value=1, max_value=10),
    _definition("contact_email", "email"),
    _definition("start_date", "date"),
    _definition(
        "category",
        "select",
        field_options=[{"value": "low_income", "label": "低收"}, {"value": "general", "label": "一般"}],
    ),
    _definition("identity", "radio", field_options=[{"value": "local", "label": "本地生"}]),
    _definition("consent", "checkbox"),
    _definition("retired_field", is_active=False),
    _definition("signature", "file"),
    _definition("postal_account", fixed_key="postal_account", is_required=True, max_length=30),
]
ADVISOR_DEFINITIONS = [
    _definition("advisor_name", fixed_key="advisor_name", is_required=True, max_length=100),
    _definition("advisor_email", "email", fixed_key="advisor_email", is_required=False),
    _definition("advisor_nycu_id", fixed_key="advisor_nycu_id", is_required=True, max_length=20),
]
DEFINITIONS = BASE_DEFINITIONS + ADVISOR_DEFINITIONS

PROFILE = {
    "account_number": ACCOUNT_B,
    "advisor_name": "舊教授",
    "advisor_email": "old@nycu.edu.tw",
    "advisor_nycu_id": "P0001",
}


def _stored_form() -> dict:
    return {
        "fields": {
            "contact_phone": {
                "field_id": "contact_phone",
                "field_type": "text",
                "value": "0912345678",
                "required": True,
                "label": "聯絡電話",
            },
            "remark": {"field_id": "remark", "field_type": "textarea", "value": "舊備註", "required": False},
            "household_size": {"field_id": "household_size", "field_type": "number", "value": 3, "required": False},
        },
        "documents": [{"document_id": "transcript", "document_type": "成績單", "file_path": "a.pdf"}],
    }


def _with_fields(**entries) -> dict:
    form = _stored_form()
    return {
        **form,
        "fields": {
            **form["fields"],
            **{key: {"field_id": key, "field_type": "text", "value": value} for key, value in entries.items()},
        },
    }


def _apply(raw_fields: dict, form_data: dict | None = None, profile: dict | None = None, definitions=DEFINITIONS):
    spec = build_editable_form_spec(definitions)
    return apply_staff_form_edit(
        _stored_form() if form_data is None else form_data,
        spec,
        raw_fields,
        PROFILE if profile is None else profile,
    )


class TestApplyStaffFormEdit:
    def test_changed_text_field_is_stripped_and_keeps_entry_keys(self):
        edit = _apply({"contact_phone": " 0987654321 "})

        assert edit.form_data["fields"]["contact_phone"] == {
            "field_id": "contact_phone",
            "field_type": "text",
            "value": "0987654321",
            "required": True,
            "label": "聯絡電話",
        }
        assert {name: (c.old, c.new) for name, c in edit.changes.items()} == {
            "contact_phone": ("0912345678", "0987654321")
        }

    def test_untouched_fields_and_documents_are_carried_over(self):
        stored = _stored_form()
        edit = _apply({"remark": "新備註"}, stored)

        assert edit.form_data["documents"] == _stored_form()["documents"]
        assert edit.form_data["fields"]["contact_phone"] == _stored_form()["fields"]["contact_phone"]
        assert edit.form_data["fields"]["household_size"] == _stored_form()["fields"]["household_size"]
        assert edit.form_data["fields"]["remark"]["value"] == "新備註"

    def test_inputs_are_not_mutated(self):
        stored = _with_fields(account_number=ACCOUNT_A)
        profile = dict(PROFILE)
        snapshot = (deepcopy(stored), deepcopy(profile))

        edit = _apply(
            {"remark": "新備註", "category": "general", "postal_account": NEW_ACCOUNT, "advisor_name": "新教授"},
            stored,
            profile,
        )

        assert (stored, profile) == snapshot
        assert edit.form_data is not stored

    def test_field_absent_from_stored_form_gets_the_standard_entry_shape(self):
        edit = _apply({"category": "general"})

        assert edit.form_data["fields"]["category"] == {
            "field_id": "category",
            "field_type": "select",
            "value": "general",
            "required": False,
        }
        assert edit.changes["category"].old is None

    def test_unchanged_values_produce_no_changes(self):
        edit = _apply(
            {"contact_phone": "0912345678", "household_size": 3, "postal_account": ACCOUNT_B, "advisor_name": "舊教授"}
        )

        assert edit.changes == {}
        assert edit.profile_updates == {}
        assert edit.form_data == _stored_form()

    def test_clearing_an_empty_optional_field_is_not_a_change(self):
        assert _apply({"start_date": ""}).changes == {}

    @pytest.mark.parametrize(
        "raw_fields",
        [
            {"household_size": 11},
            {"household_size": 0},
            {"household_size": "3"},
            {"household_size": True},
            {"category": "vip"},
            {"identity": "foreign"},
            {"start_date": "2026/01/01"},
            {"start_date": "2026-02-30"},
            {"contact_email": "not-an-email"},
            {"consent": "yes"},
            {"remark": "x" * 11},
            {"remark": 42},
            {"contact_phone": "0912345678 ext 9"},
            {"contact_phone": ""},
            {"contact_phone": None},
            {"postal_account": "1234567890123"},
            {"postal_account": "123456789012345"},
            {"postal_account": "郵局帳號"},
            {"postal_account": 12345678901234},
            {"postal_account": ""},
            {"advisor_name": ""},
            {"advisor_nycu_id": None},
            {"advisor_email": "not-an-email"},
        ],
    )
    def test_invalid_values_are_rejected_with_the_field_label(self, raw_fields):
        (name,) = raw_fields
        with pytest.raises(ValidationError) as exc_info:
            _apply(raw_fields)
        assert f"{name} 標籤" in exc_info.value.message

    @pytest.mark.parametrize(
        ("raw_fields", "stored_value"),
        [
            ({"household_size": 7.5}, 7.5),
            ({"contact_email": "a@b.tw"}, "a@b.tw"),
            ({"start_date": "2026-02-28"}, "2026-02-28"),
            ({"identity": "local"}, "local"),
            ({"consent": True}, True),
            ({"remark": ""}, ""),
            ({"household_size": None}, None),
        ],
    )
    def test_valid_values_are_stored_normalized(self, raw_fields, stored_value):
        ((name, _),) = raw_fields.items()
        assert _apply(raw_fields).form_data["fields"][name]["value"] == stored_value

    @pytest.mark.parametrize("name", ["not_in_config", "retired_field"])
    def test_unknown_or_inactive_field_is_rejected(self, name):
        with pytest.raises(ValidationError) as exc_info:
            _apply({name: "x"})
        assert name in exc_info.value.message

    @pytest.mark.parametrize("name", ["advisor_name", "advisor_email", "advisor_nycu_id"])
    def test_advisor_field_absent_from_the_config_is_rejected(self, name):
        with pytest.raises(ValidationError) as exc_info:
            _apply({name: "x@nycu.edu.tw"}, definitions=BASE_DEFINITIONS)
        assert name in exc_info.value.message

    def test_unsupported_field_type_is_rejected(self):
        with pytest.raises(ValidationError):
            _apply({"signature": "x"})

    def test_one_invalid_field_rejects_the_whole_request(self):
        stored = _stored_form()
        with pytest.raises(ValidationError):
            _apply({"remark": "ok", "category": "vip"}, stored)
        assert stored == _stored_form()


class TestPostalAccountEdit:
    @pytest.mark.parametrize(
        ("submitted", "profile_account", "expected_old"),
        [
            ({"account_number": ACCOUNT_A, "postal_account": ACCOUNT_C}, ACCOUNT_B, ACCOUNT_A),
            ({"postal_account": ACCOUNT_C, "bank_account": ACCOUNT_D}, ACCOUNT_B, ACCOUNT_B),
            ({"postal_account": ACCOUNT_C, "bank_account": ACCOUNT_D}, None, ACCOUNT_C),
            ({"bank_account": ACCOUNT_D}, "", ACCOUNT_D),
            ({}, None, None),
        ],
    )
    def test_writes_account_number_and_diffs_against_the_shown_account(self, submitted, profile_account, expected_old):
        stored = _with_fields(**submitted)

        edit = _apply({"postal_account": NEW_ACCOUNT}, stored, {**PROFILE, "account_number": profile_account})

        assert edit.form_data["fields"]["account_number"]["value"] == NEW_ACCOUNT
        for key in ("postal_account", "bank_account"):
            assert edit.form_data["fields"].get(key) == stored["fields"].get(key)
        assert (edit.changes["postal_account"].old, edit.changes["postal_account"].new) == (expected_old, NEW_ACCOUNT)
        assert edit.profile_updates == {}

    def test_account_is_stored_as_digits_and_keeps_the_entry_keys(self):
        stored = _with_fields(account_number=ACCOUNT_A)
        stored["fields"]["account_number"]["label"] = "郵局帳號"

        edit = _apply({"postal_account": "0001234-5678901"}, stored)

        assert edit.form_data["fields"]["account_number"] == {
            "field_id": "account_number",
            "field_type": "text",
            "value": NEW_ACCOUNT,
            "required": True,
            "label": "郵局帳號",
        }

    def test_account_change_marks_bank_verification_stale(self):
        assert _apply({"postal_account": NEW_ACCOUNT}).stale_meta_keys >= {"bank_verification"}
        assert _apply({"remark": "新備註"}).stale_meta_keys == frozenset()

    def test_edit_names_the_digits_of_the_account_it_set(self):
        assert _apply({"postal_account": "0001234-5678901"}).postal_account == NEW_ACCOUNT
        assert _apply({"remark": "新備註"}).postal_account is None
        assert _apply({"postal_account": ACCOUNT_B}).postal_account is None

    def test_clearing_an_optional_account_names_no_account(self):
        optional = [
            (
                definition.model_copy(update={"is_required": False})
                if definition.field_name == "postal_account"
                else definition
            )
            for definition in DEFINITIONS
        ]

        edit = _apply({"postal_account": ""}, _with_fields(account_number=ACCOUNT_A), definitions=optional)

        assert edit.changes["postal_account"].new == ""
        assert edit.postal_account is None


class TestAdvisorEdit:
    def test_advisor_edits_go_to_the_profile_and_leave_the_form_alone(self):
        stored = _stored_form()

        edit = _apply({"advisor_name": " 新教授 ", "advisor_email": "new@nycu.edu.tw"}, stored)

        assert edit.form_data == stored
        assert edit.profile_updates == {"advisor_name": "新教授", "advisor_email": "new@nycu.edu.tw"}
        assert {name: (c.old, c.new) for name, c in edit.changes.items()} == {
            "advisor_name": ("舊教授", "新教授"),
            "advisor_email": ("old@nycu.edu.tw", "new@nycu.edu.tw"),
        }

    def test_old_value_falls_back_to_the_submitted_copy_when_the_profile_is_empty(self):
        edit = _apply({"advisor_name": "新教授"}, _with_fields(advisor_name="匯入教授"), {})

        assert edit.changes["advisor_name"].old == "匯入教授"

    def test_clearing_an_optional_advisor_field_stores_none(self):
        edit = _apply({"advisor_email": ""})

        assert edit.profile_updates == {"advisor_email": None}


class TestProfessorReassignmentDecision:
    @staticmethod
    def _facts(**overrides) -> ProfessorFacts:
        values = {
            "has_professor_stage": True,
            "is_professor_actionable": True,
            "current_professor_id": 1,
            "current_professor_reviewed": False,
            "matched_professor_id": 2,
            **overrides,
        }
        return ProfessorFacts(**values)

    @pytest.mark.parametrize(
        ("overrides", "outcome", "to_professor_id"),
        [
            ({}, ReassignmentOutcome.REASSIGNED, 2),
            ({"current_professor_id": None}, ReassignmentOutcome.REASSIGNED, 2),
            ({"matched_professor_id": 1}, ReassignmentOutcome.ALREADY_ASSIGNED, 1),
            ({"current_professor_reviewed": True}, ReassignmentOutcome.KEPT_REVIEWED, 1),
            ({"matched_professor_id": None}, ReassignmentOutcome.UNASSIGNED_NO_ACCOUNT, None),
            ({"has_professor_stage": False}, ReassignmentOutcome.NOT_APPLICABLE, 1),
            ({"is_professor_actionable": False}, ReassignmentOutcome.NOT_APPLICABLE, 1),
            (
                {"is_professor_actionable": False, "current_professor_reviewed": True},
                ReassignmentOutcome.NOT_APPLICABLE,
                1,
            ),
        ],
    )
    def test_outcome(self, overrides, outcome, to_professor_id):
        decision = decide_professor_reassignment(self._facts(**overrides))

        assert decision.outcome is outcome
        assert decision.to_professor_id == to_professor_id
        assert decision.from_professor_id == overrides.get("current_professor_id", 1)

    @pytest.mark.parametrize(
        ("old", "new", "changed"),
        [("P0001", " p0001 ", False), ("P0001", "P0002", True), (None, "P0002", True), (None, "", False)],
    )
    def test_nycu_id_change_ignores_case_and_whitespace(self, old, new, changed):
        assert advisor_nycu_id_changed(old, new) is changed


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
        "admin": User(nycu_id="sfe_admin", name="Admin", email="sfe_admin@test.edu", role=UserRole.admin),
        "college_eng": User(
            nycu_id="sfe_eng", name="ENG", email="sfe_eng@test.edu", role=UserRole.college, college_code="ENG"
        ),
        "college_sci": User(
            nycu_id="sfe_sci", name="SCI", email="sfe_sci@test.edu", role=UserRole.college, college_code="SCI"
        ),
        "professor": User(nycu_id="P0001", name="原教授", email="sfe_prof@test.edu", role=UserRole.professor),
        "professor_b": User(nycu_id="P0002", name="王小明", email="sfe_prof_b@test.edu", role=UserRole.professor),
        "student": User(
            nycu_id="S990001",
            name="Student",
            email="sfe_stu@test.edu",
            role=UserRole.student,
            user_type=UserType.student,
        ),
    }
    for user in rows.values():
        if user.user_type is None:
            user.user_type = UserType.employee
        db.add(user)
    await db.commit()
    for user in rows.values():
        await db.refresh(user)
    return rows


@pytest_asyncio.fixture
async def scholarship(db):
    scholarship = ScholarshipType(code=SCHOLARSHIP_CODE, name="表單修改測試獎學金")
    db.add(scholarship)
    db.add_all(
        [
            ApplicationField(
                scholarship_type=SCHOLARSHIP_CODE,
                field_name="contact_phone",
                field_label="聯絡電話",
                field_type="text",
                is_required=True,
                is_active=True,
            ),
            ApplicationField(
                scholarship_type=SCHOLARSHIP_CODE,
                field_name="category",
                field_label="身分類別",
                field_type="select",
                field_options=[{"value": "low_income", "label": "低收"}, {"value": "general", "label": "一般"}],
                is_active=True,
            ),
        ]
    )
    await db.commit()
    await db.refresh(scholarship)
    return scholarship


async def _make_config(db, scholarship, *, initial_needs_professor=True) -> ScholarshipConfiguration:
    # Any active configuration with a professor stage makes the form config carry the advisor trio.
    config = ScholarshipConfiguration(
        scholarship_type_id=scholarship.id,
        config_code="staff_edit_cfg",
        config_name="表單修改測試設定",
        academic_year=115,
        requires_professor_recommendation=initial_needs_professor,
        renewal_requires_professor_review=True,
        requires_college_review=False,
        amount=0,
        is_active=True,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


@pytest_asyncio.fixture
async def config(db, scholarship):
    return await _make_config(db, scholarship)


@pytest_asyncio.fixture
async def profile(db, users):
    row = UserProfile(user_id=users["student"].id, **PROFILE)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def _make_application(
    db,
    users,
    scholarship,
    status=ApplicationStatus.submitted,
    config=None,
    form_data=None,
    meta_data=None,
) -> Application:
    application = Application(
        app_id="APP-115-1-09001",
        user_id=users["student"].id,
        scholarship_type_id=scholarship.id,
        scholarship_configuration_id=config.id if config else None,
        professor_id=users["professor"].id if config else None,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        status=status,
        academic_year=115,
        semester="first",
        student_data={"std_stdcode": "S990001", "std_cname": "Student", "std_academyno": "ENG"},
        submitted_form_data=form_data or _stored_form(),
        meta_data=meta_data,
        agree_terms=True,
    )
    db.add(application)
    await db.commit()
    await db.refresh(application)
    return application


async def _stored_fields(db, application_id: int) -> dict:
    stmt = select(Application.submitted_form_data).where(Application.id == application_id)
    return (await db.execute(stmt)).scalar_one()


async def _application_row(db, application_id: int):
    stmt = select(Application.professor_id, Application.meta_data).where(Application.id == application_id)
    return (await db.execute(stmt)).one()


async def _profile_row(db, user_id: int):
    stmt = select(
        UserProfile.account_number,
        UserProfile.advisor_name,
        UserProfile.advisor_email,
        UserProfile.advisor_nycu_id,
    ).where(UserProfile.user_id == user_id)
    return (await db.execute(stmt)).one_or_none()


async def _audit_rows(db, application_id: int) -> list:
    rows = await db.execute(
        select(AuditLog).where(AuditLog.resource_id == str(application_id), AuditLog.action == "update")
    )
    return rows.scalars().all()


async def _notifications_for(db, user_id: int) -> list:
    rows = await db.execute(select(Notification).where(Notification.user_id == user_id))
    return rows.scalars().all()


@pytest.mark.api
class TestStaffFormFieldsEndpoint:
    async def test_admin_edit_persists_and_is_audited(self, client, db, login, users, scholarship):
        application = await _make_application(db, users, scholarship)
        login(users["admin"])

        response = await client.patch(
            URL.format(id=application.id), json={"fields": {"contact_phone": "0987654321", "category": "general"}}
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["success"] is True
        assert body["message"] == "表單內容已更新"
        assert body["data"]["id"] == application.id
        assert body["data"]["submitted_form_data"]["fields"]["contact_phone"]["value"] == "0987654321"

        stored = await _stored_fields(db, application.id)
        assert stored["fields"]["contact_phone"]["value"] == "0987654321"
        assert stored["fields"]["category"]["value"] == "general"
        assert stored["fields"]["remark"] == _stored_form()["fields"]["remark"]
        assert stored["documents"] == _stored_form()["documents"]

        (audit,) = await _audit_rows(db, application.id)
        assert audit.user_id == users["admin"].id
        assert audit.old_values == {"contact_phone": "0912345678", "category": None}
        assert audit.new_values == {"contact_phone": "0987654321", "category": "general"}
        assert audit.meta_data["update_type"] == "staff_form_fields_edit"
        assert audit.meta_data["changed_fields"] == ["category", "contact_phone"]
        assert audit.meta_data["profile_fields_updated"] == []

    async def test_no_op_edit_succeeds_without_audit_row(self, client, db, login, users, scholarship):
        application = await _make_application(db, users, scholarship)
        login(users["admin"])

        response = await client.patch(URL.format(id=application.id), json={"fields": {"contact_phone": "0912345678"}})

        assert response.status_code == 200, response.text
        assert response.json()["message"] == "表單內容沒有變更"
        assert await _audit_rows(db, application.id) == []

    async def test_malformed_stored_phone_does_not_block_other_fields(self, client, db, login, users, scholarship):
        form = _stored_form()
        malformed = {
            **form,
            "fields": {
                **form["fields"],
                "contact_phone": {**form["fields"]["contact_phone"], "value": "範例聯絡電話1"},
            },
        }
        application = await _make_application(db, users, scholarship, form_data=malformed)
        login(users["admin"])

        response = await client.patch(URL.format(id=application.id), json={"fields": {"category": "general"}})

        assert response.status_code == 200, response.text
        stored = await _stored_fields(db, application.id)
        assert stored["fields"]["category"]["value"] == "general"
        assert stored["fields"]["contact_phone"]["value"] == "範例聯絡電話1"

    async def test_same_college_staff_may_edit(self, client, db, login, users, scholarship):
        application = await _make_application(db, users, scholarship)
        login(users["college_eng"])

        response = await client.patch(URL.format(id=application.id), json={"fields": {"category": "low_income"}})

        assert response.status_code == 200, response.text
        assert (await _stored_fields(db, application.id))["fields"]["category"]["value"] == "low_income"

    async def test_other_college_staff_get_404_and_nothing_changes(self, client, db, login, users, scholarship):
        application = await _make_application(db, users, scholarship)
        login(users["college_sci"])

        response = await client.patch(URL.format(id=application.id), json={"fields": {"category": "low_income"}})

        assert response.status_code == 404
        assert await _stored_fields(db, application.id) == _stored_form()

    @pytest.mark.parametrize("role", ["professor", "student"])
    async def test_professor_and_student_are_forbidden(self, client, db, login, users, scholarship, role):
        application = await _make_application(db, users, scholarship)
        login(users[role])

        response = await client.patch(URL.format(id=application.id), json={"fields": {"category": "general"}})

        assert response.status_code == 403
        assert await _stored_fields(db, application.id) == _stored_form()

    @pytest.mark.parametrize(
        "status", [ApplicationStatus.draft, ApplicationStatus.returned, ApplicationStatus.withdrawn]
    )
    async def test_student_owned_or_closed_status_is_rejected(self, client, db, login, users, scholarship, status):
        application = await _make_application(db, users, scholarship, status=status)
        login(users["admin"])

        response = await client.patch(URL.format(id=application.id), json={"fields": {"category": "general"}})

        assert response.status_code == 422
        assert response.json()["success"] is False
        assert await _stored_fields(db, application.id) == _stored_form()

    async def test_invalid_contact_phone_is_rejected(self, client, db, login, users, scholarship):
        application = await _make_application(db, users, scholarship)
        login(users["admin"])

        response = await client.patch(URL.format(id=application.id), json={"fields": {"contact_phone": "12345"}})

        assert response.status_code == 422
        assert await _stored_fields(db, application.id) == _stored_form()

    async def test_empty_payload_is_rejected(self, client, db, login, users, scholarship):
        application = await _make_application(db, users, scholarship)
        login(users["admin"])

        response = await client.patch(URL.format(id=application.id), json={"fields": {}})

        assert response.status_code == 422


VERIFIED = {
    "overall_status": "verified",
    "account_number_status": "verified",
    "account_holder_status": "verified",
    "verified_at": "2026-01-01T00:00:00+00:00",
}
ORIGINAL_BANK_FIELDS = {"fields": {"account_number": ACCOUNT_A}, "preserved_at": "2026-01-01T00:00:00+00:00"}


@pytest.mark.api
class TestPostalAccountEndpoint:
    async def test_admin_edit_writes_the_application_account_only(self, client, db, login, users, scholarship, profile):
        form = _with_fields(account_number=ACCOUNT_A, postal_account=ACCOUNT_C)
        application = await _make_application(
            db,
            users,
            scholarship,
            form_data=form,
            meta_data={"bank_verification": VERIFIED, "original_bank_fields": ORIGINAL_BANK_FIELDS},
        )
        login(users["admin"])

        response = await client.patch(URL.format(id=application.id), json={"fields": {"postal_account": NEW_ACCOUNT}})

        assert response.status_code == 200, response.text
        assert response.json()["data"]["submitted_form_data"]["fields"]["account_number"]["value"] == NEW_ACCOUNT

        stored = await _stored_fields(db, application.id)
        assert stored["fields"]["account_number"]["value"] == NEW_ACCOUNT
        assert stored["fields"]["postal_account"] == form["fields"]["postal_account"]
        assert (await _profile_row(db, users["student"].id)).account_number == ACCOUNT_B

        _, meta_data = await _application_row(db, application.id)
        assert "bank_verification" not in meta_data
        assert meta_data["original_bank_fields"] == ORIGINAL_BANK_FIELDS

        (audit,) = await _audit_rows(db, application.id)
        assert audit.old_values == {"postal_account": ACCOUNT_A}
        assert audit.new_values == {"postal_account": NEW_ACCOUNT}
        assert audit.meta_data["cleared_meta_data"] == {"bank_verification": VERIFIED}

    async def test_other_edits_keep_the_verification(self, client, db, login, users, scholarship, profile):
        application = await _make_application(db, users, scholarship, meta_data={"bank_verification": VERIFIED})
        login(users["admin"])

        response = await client.patch(URL.format(id=application.id), json={"fields": {"category": "general"}})

        assert response.status_code == 200, response.text
        _, meta_data = await _application_row(db, application.id)
        assert meta_data["bank_verification"] == VERIFIED

    async def test_invalid_account_is_rejected(self, client, db, login, users, scholarship, profile):
        application = await _make_application(db, users, scholarship)
        login(users["admin"])

        response = await client.patch(URL.format(id=application.id), json={"fields": {"postal_account": "12345"}})

        assert response.status_code == 422
        assert await _stored_fields(db, application.id) == _stored_form()


@pytest.mark.api
class TestAdvisorEndpoint:
    async def test_college_edit_updates_the_profile_with_history(
        self, client, db, login, users, scholarship, config, profile
    ):
        application = await _make_application(db, users, scholarship, config=config)
        login(users["college_eng"])

        response = await client.patch(URL.format(id=application.id), json={"fields": {"advisor_name": "新教授"}})

        assert response.status_code == 200, response.text
        assert response.json()["data"]["advisor_name"] == "新教授"
        assert (await _profile_row(db, users["student"].id)).advisor_name == "新教授"
        assert await _stored_fields(db, application.id) == _stored_form()

        professor_id, _ = await _application_row(db, application.id)
        assert professor_id == users["professor"].id

        history = (
            (await db.execute(select(UserProfileHistory).where(UserProfileHistory.user_id == users["student"].id)))
            .scalars()
            .all()
        )
        assert [(h.field_name, h.old_value, h.new_value) for h in history] == [("advisor_name", "舊教授", "新教授")]
        assert application.app_id in history[0].change_reason

        (audit,) = await _audit_rows(db, application.id)
        assert audit.old_values == {"advisor_name": "舊教授"}
        assert audit.new_values == {"advisor_name": "新教授"}
        assert audit.meta_data["profile_fields_updated"] == ["advisor_name"]
        assert "professor_reassignment" not in audit.meta_data

    async def test_dynamic_field_and_advisor_land_together(
        self, client, db, login, users, scholarship, config, profile
    ):
        application = await _make_application(db, users, scholarship, config=config)
        login(users["admin"])

        response = await client.patch(
            URL.format(id=application.id),
            json={"fields": {"category": "general", "advisor_email": "new@nycu.edu.tw"}},
        )

        assert response.status_code == 200, response.text
        assert (await _stored_fields(db, application.id))["fields"]["category"]["value"] == "general"
        assert (await _profile_row(db, users["student"].id)).advisor_email == "new@nycu.edu.tw"

    async def test_rejected_advisor_value_leaves_everything_unchanged(
        self, client, db, login, users, scholarship, config, profile
    ):
        application = await _make_application(db, users, scholarship, config=config)
        login(users["admin"])

        response = await client.patch(
            URL.format(id=application.id),
            json={"fields": {"category": "general", "advisor_name": "x" * 101}},
        )

        assert response.status_code == 422
        assert await _stored_fields(db, application.id) == _stored_form()
        assert (await _profile_row(db, users["student"].id)).advisor_name == "舊教授"

    async def test_student_without_a_profile_gets_one(self, client, db, login, users, scholarship, config):
        application = await _make_application(db, users, scholarship, config=config)
        login(users["admin"])

        response = await client.patch(URL.format(id=application.id), json={"fields": {"advisor_name": "新教授"}})

        assert response.status_code == 200, response.text
        assert (await _profile_row(db, users["student"].id)).advisor_name == "新教授"

    async def test_advisor_fields_are_rejected_without_a_professor_stage(
        self, client, db, login, users, scholarship, profile
    ):
        application = await _make_application(db, users, scholarship)
        login(users["admin"])

        response = await client.patch(URL.format(id=application.id), json={"fields": {"advisor_name": "新教授"}})

        assert response.status_code == 422
        assert (await _profile_row(db, users["student"].id)).advisor_name == "舊教授"


@pytest.mark.api
class TestAdvisorNycuIdReassignment:
    async def _edit_nycu_id(self, client, application, nycu_id):
        return await client.patch(URL.format(id=application.id), json={"fields": {"advisor_nycu_id": nycu_id}})

    async def test_unreviewed_application_moves_to_the_new_advisor(
        self, client, db, login, users, scholarship, config, profile
    ):
        application = await _make_application(db, users, scholarship, config=config)
        login(users["admin"])

        response = await self._edit_nycu_id(client, application, "p0002")

        assert response.status_code == 200, response.text
        assert response.json()["message"] == "表單內容已更新，審核教授已改派為 王小明"
        assert response.json()["data"]["professor_id"] == users["professor_b"].id
        professor_id, _ = await _application_row(db, application.id)
        assert professor_id == users["professor_b"].id
        assert (await _profile_row(db, users["student"].id)).advisor_nycu_id == "p0002"

        (notification,) = await _notifications_for(db, users["professor_b"].id)
        assert application.app_id in notification.message
        assert await _notifications_for(db, users["professor"].id) == []

        (audit,) = await _audit_rows(db, application.id)
        assert audit.meta_data["professor_reassignment"] == {
            "outcome": "reassigned",
            "from_professor_id": users["professor"].id,
            "to_professor_id": users["professor_b"].id,
        }

    async def test_reviewed_application_keeps_its_professor(
        self, client, db, login, users, scholarship, config, profile
    ):
        application = await _make_application(db, users, scholarship, config=config)
        db.add(
            ApplicationReview(
                application_id=application.id,
                reviewer_id=users["professor"].id,
                recommendation="approve",
                reviewed_at=_NOW,
            )
        )
        await db.commit()
        login(users["admin"])

        response = await self._edit_nycu_id(client, application, "P0002")

        assert response.status_code == 200, response.text
        assert response.json()["message"] == "表單內容已更新；原審核教授已完成審核，未改派"
        professor_id, _ = await _application_row(db, application.id)
        assert professor_id == users["professor"].id
        assert (await _profile_row(db, users["student"].id)).advisor_nycu_id == "P0002"
        assert await _notifications_for(db, users["professor_b"].id) == []
        (audit,) = await _audit_rows(db, application.id)
        assert audit.meta_data["professor_reassignment"]["outcome"] == "kept_reviewed"

    async def test_unknown_advisor_leaves_the_application_unassigned(
        self, client, db, login, users, scholarship, config, profile
    ):
        application = await _make_application(db, users, scholarship, config=config)
        login(users["admin"])

        response = await self._edit_nycu_id(client, application, "P9999")

        assert response.status_code == 200, response.text
        assert response.json()["message"] == "表單內容已更新；查無此人事編號的教授帳號，該教授登入後會自動指派"
        professor_id, _ = await _application_row(db, application.id)
        assert professor_id is None
        (audit,) = await _audit_rows(db, application.id)
        assert audit.meta_data["professor_reassignment"] == {
            "outcome": "unassigned_no_account",
            "from_professor_id": users["professor"].id,
            "to_professor_id": None,
        }

    async def test_configuration_without_a_professor_stage_is_left_alone(
        self, client, db, login, users, scholarship, profile
    ):
        config = await _make_config(db, scholarship, initial_needs_professor=False)
        application = await _make_application(db, users, scholarship, config=config)
        login(users["admin"])

        response = await self._edit_nycu_id(client, application, "P0002")

        assert response.status_code == 200, response.text
        assert response.json()["message"] == "表單內容已更新"
        professor_id, _ = await _application_row(db, application.id)
        assert professor_id == users["professor"].id
        (audit,) = await _audit_rows(db, application.id)
        assert audit.meta_data["professor_reassignment"]["outcome"] == "not_applicable"

    async def test_case_only_change_does_not_reassign(self, client, db, login, users, scholarship, config, profile):
        application = await _make_application(db, users, scholarship, config=config)
        login(users["admin"])

        response = await self._edit_nycu_id(client, application, "p0001")

        assert response.status_code == 200, response.text
        professor_id, _ = await _application_row(db, application.id)
        assert professor_id == users["professor"].id
        (audit,) = await _audit_rows(db, application.id)
        assert "professor_reassignment" not in audit.meta_data
