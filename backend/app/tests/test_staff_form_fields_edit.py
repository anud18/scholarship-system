"""Staff (admin / 學院) correction of a submitted application's form fields.

PATCH /api/v1/applications/{id}/form-fields and the pure merge in
app/services/staff_form_edit.py.
"""

from copy import deepcopy
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.exceptions import ValidationError
from app.models.application import Application, ApplicationStatus
from app.models.application_field import ApplicationField
from app.models.audit_log import AuditLog
from app.models.scholarship import ScholarshipType, SubTypeSelectionMode
from app.models.user import User, UserRole, UserType
from app.schemas.application_field import ApplicationFieldResponse
from app.services.application_service import PROFILE_OWNED_FORM_FIELDS
from app.services.staff_form_edit import apply_staff_form_edit, build_editable_form_spec

URL = "/api/v1/applications/{id}/form-fields"
SCHOLARSHIP_CODE = "staff_edit_scholarship"

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


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


DEFINITIONS = [
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
    _definition("postal_account", fixed_key="postal_account", is_required=True),
]


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


def _apply(raw_fields: dict, form_data: dict | None = None):
    spec = build_editable_form_spec(DEFINITIONS, PROFILE_OWNED_FORM_FIELDS)
    return apply_staff_form_edit(_stored_form() if form_data is None else form_data, spec, raw_fields)


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

    def test_input_form_data_is_not_mutated(self):
        stored = _stored_form()
        snapshot = deepcopy(stored)

        edit = _apply({"remark": "新備註", "category": "general"}, stored)

        assert stored == snapshot
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
        edit = _apply({"contact_phone": "0912345678", "household_size": 3})

        assert edit.changes == {}
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

    @pytest.mark.parametrize("name", ["postal_account", "advisor_name", "advisor_email", "advisor_nycu_id"])
    def test_profile_owned_field_is_rejected(self, name):
        with pytest.raises(ValidationError) as exc_info:
            _apply({name: "x"})
        assert name in exc_info.value.message

    def test_unsupported_field_type_is_rejected(self):
        with pytest.raises(ValidationError):
            _apply({"signature": "x"})

    def test_one_invalid_field_rejects_the_whole_request(self):
        stored = _stored_form()
        with pytest.raises(ValidationError):
            _apply({"remark": "ok", "category": "vip"}, stored)
        assert stored == _stored_form()


# ---------------------------------------------------------------------------
# HTTP


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
        "professor": User(nycu_id="sfe_prof", name="Prof", email="sfe_prof@test.edu", role=UserRole.professor),
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


async def _make_application(db, users, scholarship, status=ApplicationStatus.submitted) -> Application:
    application = Application(
        app_id="APP-115-1-09001",
        user_id=users["student"].id,
        scholarship_type_id=scholarship.id,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        status=status,
        academic_year=115,
        semester="first",
        student_data={"std_stdcode": "S990001", "std_cname": "Student", "std_academyno": "ENG"},
        submitted_form_data=_stored_form(),
        agree_terms=True,
    )
    db.add(application)
    await db.commit()
    await db.refresh(application)
    return application


async def _stored_fields(db, application_id: int) -> dict:
    stmt = select(Application.submitted_form_data).where(Application.id == application_id)
    return (await db.execute(stmt)).scalar_one()


async def _audit_rows(db, application_id: int) -> list:
    rows = await db.execute(
        select(AuditLog).where(AuditLog.resource_id == str(application_id), AuditLog.action == "update")
    )
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

    async def test_no_op_edit_succeeds_without_audit_row(self, client, db, login, users, scholarship):
        application = await _make_application(db, users, scholarship)
        login(users["admin"])

        response = await client.patch(URL.format(id=application.id), json={"fields": {"contact_phone": "0912345678"}})

        assert response.status_code == 200, response.text
        assert await _audit_rows(db, application.id) == []

    async def test_malformed_stored_phone_does_not_block_other_fields(self, client, db, login, users, scholarship):
        application = await _make_application(db, users, scholarship)
        form = _stored_form()
        application.submitted_form_data = {
            **form,
            "fields": {
                **form["fields"],
                "contact_phone": {**form["fields"]["contact_phone"], "value": "範例聯絡電話1"},
            },
        }
        await db.commit()
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

    async def test_profile_owned_field_is_rejected(self, client, db, login, users, scholarship):
        application = await _make_application(db, users, scholarship)
        login(users["admin"])

        response = await client.patch(URL.format(id=application.id), json={"fields": {"postal_account": "0" * 14}})

        assert response.status_code == 422
        assert "postal_account" in response.json()["message"]

    async def test_empty_payload_is_rejected(self, client, db, login, users, scholarship):
        application = await _make_application(db, users, scholarship)
        login(users["admin"])

        response = await client.patch(URL.format(id=application.id), json={"fields": {}})

        assert response.status_code == 422
