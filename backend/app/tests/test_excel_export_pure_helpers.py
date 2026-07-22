"""
Tests for `ExcelExportService` security + display helpers.

Two distinct concerns covered:

1. `_resolve_template_path` is a **security gate** — it accepts a
   user-supplied template name and resolves it to a file on disk. The
   allowlist prevents path traversal (e.g. `../../../etc/passwd`).
   These tests pin the allowlist contract so any future change to the
   resolver is intentional.

2. `_format_allocation_display` produces a roster-row label visible to
   finance. Wrong rendering of the sub-type name shows the wrong
   scholarship source on the payment voucher.

2 helpers covered (10 cases).
"""

from types import SimpleNamespace

import pytest

from app.services.excel_export_service import ExcelExportService


@pytest.fixture
def service():
    """Constructor reads settings, tries to load a template file. Both
    fall back gracefully if missing, so we can construct without prepping
    a temp template directory."""
    return ExcelExportService()


# ─── _resolve_template_path (security) ───────────────────────────────


def test_resolve_template_path_none_returns_default(service):
    """None template name ⇒ default template (no user input to validate)."""
    assert service._resolve_template_path(None) == service.template_path


def test_resolve_template_path_empty_string_returns_default(service):
    """Empty string is falsy ⇒ same as None."""
    assert service._resolve_template_path("") == service.template_path


def test_resolve_template_path_path_traversal_rejected(service):
    """SECURITY: an attempted traversal like '../../etc/passwd' is NOT
    in the allowlist, so it falls back to the default. Pin this so any
    future refactor that drops the allowlist breaks this test."""
    out = service._resolve_template_path("../../etc/passwd")
    assert out == service.template_path
    # Even with .xlsx suffix coercion attempt
    out = service._resolve_template_path("../etc/passwd.xlsx")
    assert out == service.template_path


def test_resolve_template_path_unknown_name_rejected(service):
    """Random valid-looking template name not on allowlist ⇒ default."""
    out = service._resolve_template_path("custom_template.xlsx")
    assert out == service.template_path


def test_resolve_template_path_known_name_returns_default_when_file_missing(service):
    """Known allowlisted name without .xlsx is auto-suffixed; if the file
    doesn't actually exist on disk (default test env), falls back to the
    configured default template path. Pin this fallback so missing
    templates don't crash export."""
    out = service._resolve_template_path("scholarship_roster")
    # File doesn't exist in test env → falls back to default
    assert out == service.template_path


def test_resolve_template_path_allowlist_membership(service):
    """The allowlist itself is part of the contract — pin its content
    so any new template addition is reviewed."""
    assert service.ALLOWED_TEMPLATES == {
        "STD_UP_MIXLISTA.xlsx",
        "payment_roster_template.xlsx",
        "scholarship_roster.xlsx",
    }


# ─── _format_allocation_display ──────────────────────────────────────


def test_format_allocation_display_no_sub_type_returns_empty():
    """Unallocated items render as '' (don't show year-only on roster)."""
    item = SimpleNamespace(allocated_sub_type=None, allocation_year=2024)
    assert ExcelExportService._format_allocation_display(item) == ""


def test_format_allocation_display_known_sub_types_with_year():
    """Year prefixed with 年 + Chinese label."""
    item = SimpleNamespace(allocated_sub_type="nstc", allocation_year=114)
    assert ExcelExportService._format_allocation_display(item) == "114年 國科會"

    item = SimpleNamespace(allocated_sub_type="moe_1w", allocation_year=113)
    assert ExcelExportService._format_allocation_display(item) == "113年 教育部(5000)"

    item = SimpleNamespace(allocated_sub_type="moe_2w", allocation_year=113)
    assert ExcelExportService._format_allocation_display(item) == "113年 教育部(2萬)"


def test_format_allocation_display_unknown_sub_type_passes_through():
    """Unknown sub-types (admin added a new track) pass through as-is —
    matches CLAUDE.md §4 (sub-types are config-driven, not enum-constrained)."""
    item = SimpleNamespace(allocated_sub_type="new_custom_track", allocation_year=114)
    assert ExcelExportService._format_allocation_display(item) == "114年 new_custom_track"


def test_format_allocation_display_no_year_omits_year_prefix():
    """If allocation_year is missing/0, render just the label (no '0年' prefix)."""
    item = SimpleNamespace(allocated_sub_type="nstc", allocation_year=None)
    assert ExcelExportService._format_allocation_display(item) == "國科會"

    item = SimpleNamespace(allocated_sub_type="nstc", allocation_year=0)
    assert ExcelExportService._format_allocation_display(item) == "國科會"
