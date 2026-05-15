"""
Tests for `ExcelExportService._generate_remarks` — the helper that
assembles the human-readable "備註" (remarks) cell for every roster Excel
row. This is the cell that operators / auditors read first when a row
is missing from the payment list.

A regression here either:
- Drops the exclusion reason silently (auditor can't tell why student
  was filtered out)
- Loses the warning flag (student paid despite an active warning rule)
- Garbles the period_label / scholarship config_code (cross-reference
  to the source roster impossible)

The method is pure: it reads attributes off a PaymentRosterItem +
PaymentRoster (no DB / IO inside the method body) — we test with
SimpleNamespace stubs.

Wave 6a159.
"""

from types import SimpleNamespace

import pytest

from app.services.excel_export_service import ExcelExportService


@pytest.fixture
def service():
    """ExcelExportService.__init__ touches the filesystem to load template
    paths. We bypass that by using __new__ — the method under test only
    reads its arguments + calls `_get_verification_status_label` (also pure).
    """
    return ExcelExportService.__new__(ExcelExportService)


def _make_roster(period_label="2025-09", config_code="NSTC-2025"):
    return SimpleNamespace(
        period_label=period_label,
        scholarship_configuration=SimpleNamespace(config_code=config_code),
    )


def _make_item(
    is_included=True,
    exclusion_reason=None,
    verification_status_value="verified",
    bank_account="123-456-789",
    warning_rules=None,
):
    return SimpleNamespace(
        is_included=is_included,
        exclusion_reason=exclusion_reason,
        verification_status=SimpleNamespace(value=verification_status_value),
        bank_account=bank_account,
        warning_rules=warning_rules or [],
    )


# ---------------------------------------------------------------------------
# 1. Happy path: included + verified + has bank → "合格"
# ---------------------------------------------------------------------------


def test_happy_path_marks_qualified(service):
    """Pin: a fully-eligible row is labeled '合格' (qualified).
    Pin so a refactor that drops the qualified-marker doesn't silently
    output an empty remarks cell."""
    item = _make_item()
    roster = _make_roster()
    result = service._generate_remarks(item, roster)
    assert "合格" in result


def test_happy_path_includes_period_label(service):
    """Pin: period_label is always present so auditors can cross-reference
    the source roster from the Excel cell alone."""
    item = _make_item()
    roster = _make_roster(period_label="2025-H1")
    result = service._generate_remarks(item, roster)
    assert "造冊期間: 2025-H1" in result


def test_happy_path_includes_config_code(service):
    """Pin: scholarship config_code is also present."""
    item = _make_item()
    roster = _make_roster(config_code="MOE-1W-2025")
    result = service._generate_remarks(item, roster)
    assert "獎學金: MOE-1W-2025" in result


# ---------------------------------------------------------------------------
# 2. Exclusion path — drops in the failure reason
# ---------------------------------------------------------------------------


def test_excluded_with_reason_includes_reason(service):
    """Pin: when is_included=False AND exclusion_reason is set, the reason
    surfaces in the remarks. This is the auditor's primary signal for
    "why didn't this student get paid?"."""
    item = _make_item(is_included=False, exclusion_reason="缺少銀行帳戶資訊")
    roster = _make_roster()
    result = service._generate_remarks(item, roster)
    assert "排除原因: 缺少銀行帳戶資訊" in result


def test_excluded_without_reason_omits_reason_label(service):
    """Pin: when is_included=False but exclusion_reason is None (rare —
    means the upstream forgot to fill it), we don't emit `排除原因: None`
    or similar garbage. The remarks fall through silently."""
    item = _make_item(is_included=False, exclusion_reason=None)
    roster = _make_roster()
    result = service._generate_remarks(item, roster)
    assert "排除原因" not in result
    # And the row isn't marked "合格" either
    assert "合格" not in result


def test_excluded_does_not_check_verification_or_bank(service):
    """Pin: once is_included=False, the verification / bank-account
    branches are short-circuited. This is the documented priority — an
    excluded row is excluded for ONE reason, not multiple."""
    item = _make_item(
        is_included=False,
        exclusion_reason="not eligible",
        verification_status_value="suspended",  # would normally trigger learning status
        bank_account="",  # would normally trigger bank-missing
    )
    roster = _make_roster()
    result = service._generate_remarks(item, roster)
    assert "排除原因: not eligible" in result
    assert "學籍狀態" not in result
    assert "缺少銀行資訊" not in result


# ---------------------------------------------------------------------------
# 3. Included but verification not verified → status label
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status_value,expected_label",
    [
        ("graduated", "已畢業"),
        ("suspended", "休學中"),
        ("withdrawn", "已退學"),
        ("api_error", "驗證錯誤"),
        ("not_found", "查無此人"),
    ],
)
def test_included_but_unverified_includes_status_label(service, status_value, expected_label):
    """Pin: when included but verification_status != 'verified', emit the
    zh-TW label from `_get_verification_status_label`. A refactor dropping
    one of these labels would render the cell as a raw enum value."""
    item = _make_item(is_included=True, verification_status_value=status_value)
    roster = _make_roster()
    result = service._generate_remarks(item, roster)
    assert f"學籍狀態: {expected_label}" in result


# ---------------------------------------------------------------------------
# 4. Included + verified but missing bank account
# ---------------------------------------------------------------------------


def test_included_verified_missing_bank_account(service):
    """Pin: when included and verified but bank_account is empty, the
    remarks say '缺少銀行資訊'. Bank ops uses this cell to chase the
    student for account info."""
    item = _make_item(verification_status_value="verified", bank_account="")
    roster = _make_roster()
    result = service._generate_remarks(item, roster)
    assert "缺少銀行資訊" in result
    assert "合格" not in result


# ---------------------------------------------------------------------------
# 5. Warning rules — appended after the main status
# ---------------------------------------------------------------------------


def test_single_warning_rule_appended(service):
    """Pin: warning_rules are appended with the '警告: ' prefix. Pin so a
    refactor that drops warnings doesn't silently pay a student whose
    rule check returned a warning."""
    item = _make_item(warning_rules=["GPA marginal"])
    roster = _make_roster()
    result = service._generate_remarks(item, roster)
    assert "警告: GPA marginal" in result


def test_multiple_warnings_semicolon_joined(service):
    """Pin: multiple warnings are joined with '; '."""
    item = _make_item(warning_rules=["GPA marginal", "Late submission"])
    roster = _make_roster()
    result = service._generate_remarks(item, roster)
    assert "警告: GPA marginal; Late submission" in result


def test_no_warnings_no_warning_segment(service):
    """Pin: empty warning_rules list emits NO warning segment (not
    '警告: ' with nothing after)."""
    item = _make_item(warning_rules=[])
    roster = _make_roster()
    result = service._generate_remarks(item, roster)
    assert "警告" not in result


# ---------------------------------------------------------------------------
# 6. Segment ordering
# ---------------------------------------------------------------------------


def test_segments_joined_with_semicolon_space(service):
    """Pin: the final string uses '; ' as the segment separator. Excel
    cell parsers downstream may split on this; pin so refactor doesn't
    use ', ' or newline silently."""
    item = _make_item()
    roster = _make_roster()
    result = service._generate_remarks(item, roster)
    # Period + config_code + 合格 = at least 2 separators
    assert result.count("; ") >= 2


def test_period_label_appears_before_scholarship(service):
    """Pin: order matters — period_label comes before scholarship config_code.
    Auditors scan left-to-right; pin so the visual format stays consistent
    across releases."""
    item = _make_item()
    roster = _make_roster(period_label="2025-09", config_code="NSTC")
    result = service._generate_remarks(item, roster)
    period_idx = result.index("造冊期間")
    sch_idx = result.index("獎學金")
    assert period_idx < sch_idx


# ---------------------------------------------------------------------------
# 7. Edge cases
# ---------------------------------------------------------------------------


def test_no_scholarship_configuration_omits_config_segment(service):
    """Pin: roster.scholarship_configuration can be None (legacy /
    in-progress rosters). Pin so the falsy check doesn't crash with
    AttributeError on None.config_code."""
    item = _make_item()
    roster = SimpleNamespace(period_label="2025-09", scholarship_configuration=None)
    result = service._generate_remarks(item, roster)
    # Period still present
    assert "造冊期間: 2025-09" in result
    # Scholarship segment absent
    assert "獎學金:" not in result
    # Row is still labeled qualified
    assert "合格" in result
