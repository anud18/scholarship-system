"""Tests for ApplicationField export-flag Pydantic validation."""

import pytest

from app.schemas.application_field import (
    ApplicationFieldCreate,
    ApplicationFieldUpdate,
)


def _create_payload(**overrides):
    base = {
        "scholarship_type": "phd",
        "field_name": "master_school",
        "field_label": "碑士畢業學校",
        "field_type": "text",
    }
    base.update(overrides)
    return base


class TestApplicationFieldCreateExportValidation:
    def test_text_field_with_export_flag_ok(self):
        ApplicationFieldCreate(**_create_payload(include_in_college_export=True))

    def test_textarea_field_with_export_flag_rejected(self):
        with pytest.raises(ValueError, match="僅支援"):
            ApplicationFieldCreate(**_create_payload(field_type="textarea", include_in_college_export=True))

    def test_number_field_with_export_flag_rejected(self):
        with pytest.raises(ValueError, match="僅支援"):
            ApplicationFieldCreate(**_create_payload(field_type="number", include_in_college_export=True))

    def test_select_field_with_export_flag_rejected(self):
        with pytest.raises(ValueError, match="僅支援"):
            ApplicationFieldCreate(**_create_payload(field_type="select", include_in_college_export=True))

    def test_text_field_without_export_flag_ok(self):
        ApplicationFieldCreate(**_create_payload(include_in_college_export=False))

    def test_export_label_without_flag_ok(self):
        ApplicationFieldCreate(
            **_create_payload(
                include_in_college_export=False,
                export_column_label="任意値",
            )
        )

    def test_export_label_with_text_flag_ok(self):
        ApplicationFieldCreate(
            **_create_payload(
                include_in_college_export=True,
                export_column_label="顯示名稱",
            )
        )


class TestApplicationFieldUpdateExportValidation:
    def test_update_to_text_with_flag_ok(self):
        ApplicationFieldUpdate(field_type="text", include_in_college_export=True)

    def test_update_to_number_with_flag_rejected(self):
        with pytest.raises(ValueError, match="僅支援"):
            ApplicationFieldUpdate(field_type="number", include_in_college_export=True)

    def test_update_flag_only_without_field_type_skips_validation(self):
        # When field_type isn't part of the update, the validator can't enforce
        # the rule (relies on existing DB value). Service layer must re-check.
        ApplicationFieldUpdate(include_in_college_export=True)
