"""Tests for `app.services.form_field_labels` — the field_id → zh-TW label map
behind 三、表單填寫資料 in the export summary PDF.

`submitted_form_data["fields"]` entries carry only the English `field_id`, so
without this map the PDF prints `postal_account` / `advisor_name` where the
reviewer expects 郵局帳號 / 指導教授姓名.
"""

import pytest

from app.services.application_field_service import ApplicationFieldService
from app.services.form_field_labels import (
    FIXED_FIELD_LABELS,
    load_form_field_labels,
    resolve_field_label,
)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDb:
    """Minimal AsyncSession double capturing the statement it was handed."""

    def __init__(self, rows=()):
        self.rows = list(rows)
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        return _FakeResult(self.rows)


class TestFixedFieldLabels:
    """Pin: the fields ApplicationFieldService injects at runtime have NO
    application_fields row, so this dict is their only label source."""

    def test_covers_every_runtime_injected_field(self):
        assert set(FIXED_FIELD_LABELS) == {
            "postal_account",
            "account_number",
            "advisor_name",
            "advisor_email",
            "advisor_nycu_id",
        }

    def test_postal_account_and_account_number_share_one_label(self):
        # Both ids carry the same 郵局帳號 the student typed (the wizard mints
        # account_number next to postal_account) — the summary PDF relies on
        # the identical label to collapse them into one row.
        assert FIXED_FIELD_LABELS["postal_account"] == "郵局帳號"
        assert FIXED_FIELD_LABELS["account_number"] == "郵局帳號"

    def test_all_labels_are_non_empty_chinese(self):
        for key, label in FIXED_FIELD_LABELS.items():
            assert label, f"FIXED_FIELD_LABELS[{key!r}] is empty"
            assert any("一" <= c <= "鿿" for c in label), f"FIXED_FIELD_LABELS[{key!r}] = {label!r} has no CJK"

    def test_application_field_service_uses_the_shared_constants(self):
        # DRY link: the injected form-config fields and the export PDF must not
        # drift apart into two label sources.
        svc = ApplicationFieldService(db=None)
        assert svc._create_fixed_bank_account_field()["field_label"] == FIXED_FIELD_LABELS["postal_account"]
        advisor_labels = {f["field_name"]: f["field_label"] for f in svc._create_fixed_advisor_fields()}
        assert advisor_labels == {
            "advisor_name": FIXED_FIELD_LABELS["advisor_name"],
            "advisor_email": FIXED_FIELD_LABELS["advisor_email"],
            "advisor_nycu_id": FIXED_FIELD_LABELS["advisor_nycu_id"],
        }


class TestLoadFormFieldLabels:
    @pytest.mark.asyncio
    async def test_db_rows_merge_on_top_of_the_fixed_defaults(self):
        db = _FakeDb([("master_school_info", "碩士畢業學校/學院/系所"), ("contact_phone", "聯絡電話")])
        labels = await load_form_field_labels(db, "phd")

        assert labels["master_school_info"] == "碩士畢業學校/學院/系所"
        assert labels["contact_phone"] == "聯絡電話"
        # fixed defaults survive alongside the queried rows
        assert labels["advisor_name"] == "指導教授姓名"

    @pytest.mark.asyncio
    async def test_admin_row_overrides_a_fixed_default(self):
        # bulk_update_fields re-inserts whatever the admin UI posts, so a fixed
        # field can also exist as a real row — then the admin owns the label.
        db = _FakeDb([("postal_account", "匯款帳號")])
        labels = await load_form_field_labels(db, "phd")
        assert labels["postal_account"] == "匯款帳號"

    @pytest.mark.asyncio
    async def test_blank_names_and_labels_are_skipped(self):
        db = _FakeDb([("", "空欄位"), ("advisor_name", None), ("ok_field", "有效標籤")])
        labels = await load_form_field_labels(db, "phd")

        assert labels["ok_field"] == "有效標籤"
        assert "" not in labels
        # a NULL label must not blank out the fixed default
        assert labels["advisor_name"] == "指導教授姓名"

    @pytest.mark.asyncio
    async def test_missing_scholarship_code_skips_the_query(self):
        db = _FakeDb([("master_school_info", "碩士畢業學校")])
        labels = await load_form_field_labels(db, None)

        assert db.statements == []
        assert labels == FIXED_FIELD_LABELS
        assert labels is not FIXED_FIELD_LABELS  # never hand out the module constant

    @pytest.mark.asyncio
    async def test_query_is_not_filtered_by_is_active(self):
        # A field deactivated after submission still needs its label to render
        # the submission that used it.
        db = _FakeDb()
        await load_form_field_labels(db, "phd")

        sql = str(db.statements[0]).lower()
        assert "scholarship_type" in sql
        assert "is_active" not in sql


class TestResolveFieldLabel:
    def test_known_id_maps_to_its_label(self):
        assert resolve_field_label("advisor_name", FIXED_FIELD_LABELS) == "指導教授姓名"

    def test_unknown_id_falls_back_to_the_raw_id(self):
        # Admin-created ids and batch-import custom_<x> columns can have no
        # definition — showing the raw id beats showing nothing.
        assert resolve_field_label("custom_thing", FIXED_FIELD_LABELS) == "custom_thing"

    def test_empty_label_falls_back_to_the_raw_id(self):
        assert resolve_field_label("weird", {"weird": ""}) == "weird"

    def test_empty_map_falls_back_to_the_raw_id(self):
        assert resolve_field_label("advisor_name", {}) == "advisor_name"
