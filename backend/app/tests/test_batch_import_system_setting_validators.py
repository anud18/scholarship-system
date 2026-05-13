"""
Pydantic validator tests for `batch_import.py` (Excel/CSV import rows)
and `system_setting.py` (admin-managed configuration keys).

`batch_import.ApplicationDataRow` is the **single SECURITY-CRITICAL
input boundary** for bulk imports — admins paste CSV/Excel data which is
saved verbatim. If `validate_name_fields` doesn't reject XSS payloads,
student names with `<script>` tags would be stored in the DB and
rendered later in admin / reviewer dashboards → stored XSS.

`system_setting.SystemSettingBase.validate_key` enforces a strict
alphanumeric+separator pattern. Bypasses could let admins create
configuration keys with special characters that break downstream
lookups or worse, allow injection into URL-based config fetches.

Bugs cause:
- XSS bypass: student/parent/admin names rendered raw → arbitrary JS
  executes for any reviewer viewing the application
- Junk student_id (letters with spaces / symbols) → mis-matching against
  SIS lookups → applicants stored as different identity
- Bad postal_account characters → bank transfer rejected on payment day
- Bad config_key → DB has weird keys that break config-lookup runtime

7 validators (21 cases). Pure Pydantic, no DB.
"""

import pytest
from pydantic import ValidationError

from app.models.system_setting import ConfigCategory, ConfigDataType
from app.schemas.batch_import import ApplicationDataRow
from app.schemas.system_setting import SystemSettingBase, SystemSettingUpdate

# ─── ApplicationDataRow.validate_student_id ──────────────────────────


def test_student_id_alphanumeric_accepted():
    row = ApplicationDataRow(student_id="0856001", student_name="王小明")
    assert row.student_id == "0856001"

    # Letters + digits both OK
    row2 = ApplicationDataRow(student_id="A12345", student_name="X")
    assert row2.student_id == "A12345"


def test_student_id_with_dashes_rejected():
    """Pin: alphanumeric ONLY. '0856-001' rejected. Otherwise an admin
    pasting dashes from a formatted Excel cell would silently corrupt
    the SIS-lookup key."""
    with pytest.raises(ValidationError) as exc:
        ApplicationDataRow(student_id="0856-001", student_name="X")
    assert "英文字母和數字" in str(exc.value)


def test_student_id_with_spaces_rejected():
    """Pin: internal spaces rejected (only outer strip)."""
    with pytest.raises(ValidationError):
        ApplicationDataRow(student_id="08 56001", student_name="X")


def test_student_id_outer_whitespace_stripped():
    """Pin: validator strips outer whitespace before regex check.
    Defends against trailing-newline-from-paste."""
    row = ApplicationDataRow(student_id="  0856001  ", student_name="X")
    assert row.student_id == "0856001"


# ─── ApplicationDataRow.validate_name_fields (XSS guard) ─────────────


def test_student_name_plain_text_accepted():
    """Standard CJK + Latin names accepted."""
    for name in ["王小明", "Smith, John", "李 大 偉", "Alice O'Brien"]:
        row = ApplicationDataRow(student_id="0856001", student_name=name)
        assert row.student_name == name


def test_student_name_script_tag_rejected():
    """SECURITY-CRITICAL: stored XSS prevention. A reviewer opening the
    application detail page would otherwise execute injected JS."""
    with pytest.raises(ValidationError) as exc:
        ApplicationDataRow(student_id="0856001", student_name="<script>alert(1)</script>")
    assert "不允許的字元" in str(exc.value)


def test_student_name_iframe_rejected():
    """Defense in depth — iframes also rejected (could load attacker-
    controlled URL into reviewer's browser context)."""
    with pytest.raises(ValidationError):
        ApplicationDataRow(student_id="0856001", student_name='<iframe src="http://evil.com"></iframe>')


def test_student_name_javascript_url_rejected():
    """Pin: 'javascript:' prefix rejected even outside HTML tag context.
    Otherwise a name like 'javascript:alert(1)' embedded in markdown-
    rendered prose would render as a clickable XSS link."""
    with pytest.raises(ValidationError):
        ApplicationDataRow(student_id="0856001", student_name="javascript:alert(1)")


def test_student_name_case_insensitive_xss_detection():
    """Pin: <SCRIPT>, <Script>, etc. all rejected — the regex uses
    re.IGNORECASE."""
    for variant in ["<SCRIPT>x</SCRIPT>", "<Script>x</Script>", "JaVaScRiPt:x", "<IFRAME>x</IFRAME>"]:
        with pytest.raises(ValidationError):
            ApplicationDataRow(student_id="0856001", student_name=variant)


def test_student_name_html_like_tags_without_xss_accepted():
    """Pin: only `<script`, `<iframe`, `javascript:` are blocked. Other
    HTML-ish tags (e.g., `<b>`, `<i>`) pass — the school's data import
    may legitimately include angle brackets in places. Defensive: if
    this becomes a problem, tighten the regex AND update this test."""
    # `<b>` doesn't match the XSS patterns, so it's allowed.
    row = ApplicationDataRow(student_id="0856001", student_name="<b>王小明</b>")
    assert row.student_name == "<b>王小明</b>"


# ─── ApplicationDataRow.validate_postal_account ──────────────────────


def test_postal_account_numbers_only_accepted():
    row = ApplicationDataRow(student_id="0856001", student_name="X", postal_account="0001234567")
    assert row.postal_account == "0001234567"


def test_postal_account_with_hyphens_accepted():
    """Postal account format includes hyphens (e.g., '0001-234-5678')."""
    row = ApplicationDataRow(student_id="0856001", student_name="X", postal_account="0001-234-5678")
    assert row.postal_account == "0001-234-5678"


def test_postal_account_with_letters_rejected():
    """Pin: letters rejected. Defensive against admin pasting account
    numbers with stray characters."""
    with pytest.raises(ValidationError) as exc:
        ApplicationDataRow(student_id="0856001", student_name="X", postal_account="0001a234")
    assert "數字和連字號" in str(exc.value)


def test_postal_account_with_spaces_rejected():
    with pytest.raises(ValidationError):
        ApplicationDataRow(student_id="0856001", student_name="X", postal_account="0001 234 567")


def test_postal_account_none_allowed():
    """Optional field — None passes through."""
    row = ApplicationDataRow(student_id="0856001", student_name="X", postal_account=None)
    assert row.postal_account is None


# ─── SystemSettingBase.validate_key ──────────────────────────────────


def test_config_key_alphanumeric_accepted():
    s = _system_setting(key="max_login_attempts")
    assert s.key == "max_login_attempts"


def test_config_key_with_dots_and_dashes_accepted():
    """Pin: dots and dashes allowed (config namespacing convention)."""
    s = _system_setting(key="email.smtp.host")
    assert s.key == "email.smtp.host"

    s2 = _system_setting(key="feature-flag-xyz")
    assert s2.key == "feature-flag-xyz"


def test_config_key_empty_rejected():
    with pytest.raises(ValidationError) as exc:
        _system_setting(key="")
    assert "cannot be empty" in str(exc.value)


def test_config_key_whitespace_only_rejected():
    with pytest.raises(ValidationError):
        _system_setting(key="   ")


def test_config_key_over_100_chars_rejected():
    """Pin: 100-char cap. Matches DB column length."""
    with pytest.raises(ValidationError) as exc:
        _system_setting(key="x" * 101)
    assert "100 characters" in str(exc.value)


def test_config_key_special_chars_rejected():
    """Pin: only alphanumeric + _ . - allowed. Defensive against keys
    like 'email/host' or 'foo;bar' that could break URL routing or
    SQL/log injection in the config-lookup layer."""
    for bad in ["foo/bar", "foo bar", "foo;bar", "foo$bar", "foo:bar"]:
        with pytest.raises(ValidationError):
            _system_setting(key=bad)


def test_config_key_outer_whitespace_stripped():
    """Pin: outer whitespace stripped before storage. Otherwise '  foo  '
    silently saved with spaces, and downstream lookup by 'foo' fails."""
    s = _system_setting(key="  good_key  ")
    assert s.key == "good_key"


# ─── SystemSettingBase.validate_value + description ──────────────────


def test_config_value_coerced_to_string():
    """Pin: validator returns str(v). Numeric value-types still pass
    through as their string form. Defensive against admin sending an
    int via JSON."""
    s = _system_setting(value="42")
    assert s.value == "42"
    assert isinstance(s.value, str)


def test_config_description_over_500_chars_rejected():
    with pytest.raises(ValidationError) as exc:
        _system_setting(description="x" * 501)
    assert "500 characters" in str(exc.value)


def test_config_description_none_or_short_accepted():
    s = _system_setting(description=None)
    assert s.description is None

    s2 = _system_setting(description="short description")
    assert s2.description == "short description"


# ─── SystemSettingUpdate (partial-update parallel validators) ─────────


def test_update_value_none_passes_through():
    """SystemSettingUpdate.validate_value is separate from Base — None
    means 'no change', not 'set to None'. Pin so a partial-update
    refactor preserves the sentinel."""
    upd = SystemSettingUpdate(value=None)
    assert upd.value is None


def test_update_description_length_capped_too():
    """Pin: the cap is enforced on Update as well as Base."""
    with pytest.raises(ValidationError):
        SystemSettingUpdate(description="x" * 501)


# ─── Helpers ─────────────────────────────────────────────────────────


def _system_setting(**overrides) -> SystemSettingBase:
    payload = {
        "key": "test_key",
        "value": "test_value",
        "category": ConfigCategory.features,
        "data_type": ConfigDataType.string,
    }
    payload.update(overrides)
    return SystemSettingBase(**payload)
