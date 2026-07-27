"""Tests for `ExportPackageService._generate_summary_pdf` — the per-student
學生資料彙整 PDF, focused on 三、表單填寫資料.

The stored `submitted_form_data["fields"]` entries carry only the English
`field_id` (there is no `label` key on DynamicFormField), so the label column
must come from the field-label map, not from the id.

Uses the real reportlab pipeline — the WQY CJK font is available in the
backend image and CI.
"""

from types import SimpleNamespace

import pytest
from pypdf import PdfReader

import io

from app.services.export_package_service import ExportPackageService
from app.services.form_field_labels import FIXED_FIELD_LABELS


def _mk_app(fields):
    return SimpleNamespace(
        id=1,
        student_data={
            "std_stdcode": "001",
            "std_cname": "甲",
            "trm_depname": "A系",
            "trm_academyname": "某學院",
            "trm_degree": "3",
        },
        submitted_form_data={"fields": fields, "documents": []},
    )


def _field(field_id, value):
    return {"field_id": field_id, "field_type": "text", "value": value, "required": True}


def _summary_text(fields, field_labels):
    svc = ExportPackageService(db=None, minio_service=None)
    pdf = svc._generate_summary_pdf(_mk_app(fields), "某獎學金", 114, "first", field_labels)
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)


class TestFormFieldSection:
    def test_configured_field_renders_its_chinese_label_not_the_id(self):
        text = _summary_text(
            {"master_school_info": _field("master_school_info", "交大資工所")},
            {"master_school_info": "碩士畢業學校/學院/系所"},
        )

        assert "三、表單填寫資料" in text
        assert "碩士畢業學校/學院/系所" in text
        assert "交大資工所" in text
        assert "master_school_info" not in text

    def test_runtime_injected_fixed_fields_render_in_chinese(self):
        # postal_account / advisor_* have no application_fields row — before
        # FIXED_FIELD_LABELS they printed as raw English ids.
        text = _summary_text(
            {
                "advisor_name": _field("advisor_name", "王教授"),
                "advisor_email": _field("advisor_email", "prof@nycu.edu.tw"),
                "advisor_nycu_id": _field("advisor_nycu_id", "P12345"),
            },
            dict(FIXED_FIELD_LABELS),
        )

        assert "指導教授姓名" in text
        assert "指導教授本校人事編號" in text
        assert "advisor_name" not in text
        assert "advisor_nycu_id" not in text

    def test_postal_account_and_account_number_collapse_to_one_row(self):
        # Both ids hold the same 郵局帳號 the student typed; translated they
        # would otherwise print the identical row twice.
        text = _summary_text(
            {
                "account_number": _field("account_number", "12341234123412"),
                "postal_account": _field("postal_account", "12341234123412"),
            },
            dict(FIXED_FIELD_LABELS),
        )

        assert text.count("郵局帳號") == 1
        assert text.count("12341234123412") == 1

    def test_differing_account_values_both_render(self):
        # The de-dupe is on (label, value) — a genuine discrepancy between the
        # two account ids must stay visible to the reviewer.
        text = _summary_text(
            {
                "account_number": _field("account_number", "111"),
                "postal_account": _field("postal_account", "222"),
            },
            dict(FIXED_FIELD_LABELS),
        )

        assert text.count("郵局帳號") == 2
        assert "111" in text
        assert "222" in text

    def test_two_distinct_fields_sharing_a_label_and_value_both_render(self):
        # application_fields has no uniqueness constraint on field_label, so two
        # real questions can share one label. The de-dupe is scoped to the
        # account synonyms precisely so neither answer is swallowed here.
        text = _summary_text(
            {
                "guardian_note": _field("guardian_note", "無"),
                "student_note": _field("student_note", "無"),
            },
            {"guardian_note": "備註", "student_note": "備註"},
        )

        assert text.count("備註") == 2
        assert text.count("無") == 2

    def test_rows_are_ordered_by_field_id_not_by_label(self):
        # Pin the ordering key. Sorting on the zh-TW label would order by CJK
        # codepoint (乙 U+4E59 < 甲 U+7532) — no more meaningful to a reviewer
        # than the id, and it would reshuffle the PDF whenever a label is
        # edited. Deliberately unchanged by the label work.
        text = _summary_text(
            {
                "aaa_first_by_id": _field("aaa_first_by_id", "v1"),
                "zzz_last_by_id": _field("zzz_last_by_id", "v2"),
            },
            {"aaa_first_by_id": "乙標籤", "zzz_last_by_id": "甲標籤"},
        )

        assert text.index("乙標籤") < text.index("甲標籤")

    def test_undefined_field_id_falls_back_to_the_raw_id(self):
        # Batch import accepts any custom_<x> column, so an id with no
        # definition must still render rather than vanish.
        text = _summary_text({"custom_thing": _field("custom_thing", "某值")}, {})

        assert "custom_thing" in text
        assert "某值" in text

    def test_section_omitted_when_no_form_fields(self):
        text = _summary_text({}, dict(FIXED_FIELD_LABELS))

        assert "三、表單填寫資料" not in text
        # the sections that do not depend on submitted data are still there
        assert "一、基本資料" in text
        assert "學生資料彙整" in text


class TestSummaryPdfBasics:
    @pytest.mark.parametrize(
        "semester,expected",
        [("first", "第一學期"), ("second", "第二學期"), (None, "全學年")],
    )
    def test_header_carries_scholarship_year_and_semester(self, semester, expected):
        svc = ExportPackageService(db=None, minio_service=None)
        pdf = svc._generate_summary_pdf(_mk_app({}), "某獎學金", 114, semester, {})
        text = PdfReader(io.BytesIO(pdf)).pages[0].extract_text()

        assert "某獎學金 114學年度 " + expected in text
