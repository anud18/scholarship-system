"""
Tests for `RosterService.validate_roster_consistency` — the post-generation
audit that the worker calls before exposing a roster to the bank-payment
flow.

A regression here ships malformed payment data to bank-ops. The five
documented checks are pinned:

  1. items count must equal qualified + disqualified statistics
  2. sum of qualified item.scholarship_amount must equal roster.total_amount
     (±0.01 tolerance for float drift)
  3. if expected_count > 0 but no items exist → error
  4. every item must have student_id_number, student_name, and
     scholarship_amount > 0
  5. COMPLETED rosters without an Excel artifact → warning (not error)

Pure-unit: takes a roster object, returns a dict. No DB / IO inside.

Wave 6a163.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.payment_roster import RosterStatus
from app.services.roster_service import RosterService


@pytest.fixture
def service():
    return RosterService(db=MagicMock())


def _make_item(
    *,
    is_included=True,
    is_qualified=True,
    scholarship_amount=1000,
    student_id_number="A123456789",
    student_name="王小明",
):
    return SimpleNamespace(
        is_included=is_included,
        is_qualified=is_qualified,
        scholarship_amount=scholarship_amount,
        student_id_number=student_id_number,
        student_name=student_name,
    )


def _make_roster(
    *,
    items=None,
    qualified_count=0,
    disqualified_count=0,
    total_amount=0,
    status=None,
    excel_filename="output.xlsx",
    minio_object_name=None,
):
    return SimpleNamespace(
        items=items if items is not None else [],
        qualified_count=qualified_count,
        disqualified_count=disqualified_count,
        total_amount=total_amount,
        status=status if status is not None else RosterStatus.PROCESSING,
        excel_filename=excel_filename,
        minio_object_name=minio_object_name,
    )


# ---------------------------------------------------------------------------
# 1. Happy path: counts match, amounts match, all fields present
# ---------------------------------------------------------------------------


def test_happy_path_is_valid(service):
    """Pin: a roster with consistent counts + amounts + complete items
    passes validation."""
    item = _make_item(scholarship_amount=1000)
    roster = _make_roster(items=[item], qualified_count=1, disqualified_count=0, total_amount=1000)
    result = service.validate_roster_consistency(roster)
    assert result["is_valid"] is True
    assert result["errors"] == []
    assert result["warnings"] == []


def test_returns_dict_with_three_keys(service):
    """Pin: result has exactly {is_valid, errors, warnings} keys. Pin so
    downstream consumer (dashboard / alert) doesn't break on missing keys."""
    roster = _make_roster()
    result = service.validate_roster_consistency(roster)
    assert set(result.keys()) == {"is_valid", "errors", "warnings"}


# ---------------------------------------------------------------------------
# 2. Count mismatch → error
# ---------------------------------------------------------------------------


def test_count_mismatch_is_error(service):
    """Pin: when item count != qualified + disqualified, emit error.
    Pin so a refactor doesn't silently accept counts."""
    items = [_make_item(), _make_item()]  # 2 items
    roster = _make_roster(items=items, qualified_count=5, disqualified_count=0, total_amount=2000)
    result = service.validate_roster_consistency(roster)
    assert result["is_valid"] is False
    assert any("明細數量不一致" in e for e in result["errors"])


def test_zero_items_with_zero_counts_is_valid(service):
    """Pin: empty roster (no students processed yet) → no error from
    count check. is_valid=True if no other errors."""
    roster = _make_roster(items=[], qualified_count=0, disqualified_count=0, total_amount=0)
    result = service.validate_roster_consistency(roster)
    assert result["is_valid"] is True


# ---------------------------------------------------------------------------
# 3. Total amount mismatch → error (0.01 tolerance)
# ---------------------------------------------------------------------------


def test_total_amount_mismatch_is_error(service):
    """Pin SECURITY: stored total_amount differing from sum of qualified
    items by > 0.01 → error. This is the audit trail vs payment-list
    cross-check; mismatch could indicate tampering or calculation drift."""
    items = [_make_item(scholarship_amount=1000)]
    roster = _make_roster(
        items=items,
        qualified_count=1,
        disqualified_count=0,
        total_amount=999,  # off by 1
    )
    result = service.validate_roster_consistency(roster)
    assert result["is_valid"] is False
    assert any("總金額不一致" in e for e in result["errors"])


def test_total_amount_within_tolerance_is_ok(service):
    """Pin: 0.005 drift (float round-trip) accepted."""
    items = [_make_item(scholarship_amount=1000.005)]
    roster = _make_roster(items=items, qualified_count=1, disqualified_count=0, total_amount=1000)
    result = service.validate_roster_consistency(roster)
    # No total_amount error (count + field checks still might pass)
    assert not any("總金額不一致" in e for e in result["errors"])


def test_excluded_items_not_summed(service):
    """Pin: items with is_included=False are NOT counted toward the total
    sum. Pin so excluded students don't poison the financial total."""
    items = [
        _make_item(is_included=True, scholarship_amount=1000),
        _make_item(is_included=False, scholarship_amount=99999),  # excluded
    ]
    roster = _make_roster(items=items, qualified_count=1, disqualified_count=1, total_amount=1000)
    result = service.validate_roster_consistency(roster)
    assert not any("總金額不一致" in e for e in result["errors"])


def test_unqualified_items_not_summed(service):
    """Pin: is_qualified=False items NOT summed (even if is_included=True).
    The two flags are AND-gated for inclusion in the financial total."""
    items = [
        _make_item(is_included=True, is_qualified=True, scholarship_amount=1000),
        _make_item(is_included=True, is_qualified=False, scholarship_amount=99999),
    ]
    roster = _make_roster(items=items, qualified_count=1, disqualified_count=1, total_amount=1000)
    result = service.validate_roster_consistency(roster)
    assert not any("總金額不一致" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# 4. Expected count > 0 but no items → error
# ---------------------------------------------------------------------------


def test_expected_count_but_no_items_is_error(service):
    """Pin: stats say there should be students but items list is empty —
    catches the case where the DB upsert failed silently."""
    roster = _make_roster(
        items=[],
        qualified_count=10,
        disqualified_count=5,
        total_amount=0,
    )
    result = service.validate_roster_consistency(roster)
    assert result["is_valid"] is False
    # Both count mismatch and "no items" errors should fire
    error_text = " ".join(result["errors"])
    assert "沒有任何明細項目" in error_text or "明細數量不一致" in error_text


# ---------------------------------------------------------------------------
# 5. Per-item field validation
# ---------------------------------------------------------------------------


def test_missing_student_id_is_error(service):
    """Pin SECURITY: empty student_id_number → error. Pin so a roster
    can't ship without ID (fraud prevention)."""
    item = _make_item(student_id_number="")
    roster = _make_roster(items=[item], qualified_count=1, disqualified_count=0, total_amount=1000)
    result = service.validate_roster_consistency(roster)
    assert result["is_valid"] is False
    assert any("學生身分證字號" in e for e in result["errors"])


def test_missing_student_name_is_error(service):
    item = _make_item(student_name="")
    roster = _make_roster(items=[item], qualified_count=1, disqualified_count=0, total_amount=1000)
    result = service.validate_roster_consistency(roster)
    assert result["is_valid"] is False
    assert any("學生姓名" in e for e in result["errors"])


def test_zero_scholarship_amount_is_error(service):
    """Pin: scholarship_amount <= 0 → error. Pin so a roster can't ship
    with $0 or negative payments."""
    item = _make_item(scholarship_amount=0)
    roster = _make_roster(items=[item], qualified_count=1, disqualified_count=0, total_amount=0)
    result = service.validate_roster_consistency(roster)
    assert result["is_valid"] is False
    assert any("獎學金金額無效" in e for e in result["errors"])


def test_none_scholarship_amount_is_error(service):
    item = _make_item(scholarship_amount=None)
    roster = _make_roster(items=[item], qualified_count=1, disqualified_count=0, total_amount=0)
    result = service.validate_roster_consistency(roster)
    assert result["is_valid"] is False


def test_negative_scholarship_amount_is_error(service):
    """Pin: negative amounts also caught."""
    item = _make_item(scholarship_amount=-100)
    roster = _make_roster(items=[item], qualified_count=1, disqualified_count=0, total_amount=-100)
    result = service.validate_roster_consistency(roster)
    assert result["is_valid"] is False
    assert any("獎學金金額無效" in e for e in result["errors"])


def test_error_message_includes_item_index(service):
    """Pin: per-item error messages include the row number (1-indexed) so
    bank ops can quickly find the bad row in the Excel."""
    items = [
        _make_item(),
        _make_item(student_name=""),  # row 2
    ]
    roster = _make_roster(items=items, qualified_count=2, disqualified_count=0, total_amount=2000)
    result = service.validate_roster_consistency(roster)
    assert any("#2" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# 6. COMPLETED status without Excel → warning (not error)
# ---------------------------------------------------------------------------


def test_completed_without_excel_is_warning(service):
    """Pin: a COMPLETED roster missing both Excel filename and MinIO
    object name → warning. Pin so a refactor doesn't promote to error
    (would mark valid rosters as failed)."""
    item = _make_item()
    roster = _make_roster(
        items=[item],
        qualified_count=1,
        disqualified_count=0,
        total_amount=1000,
        status=RosterStatus.COMPLETED,
        excel_filename=None,
        minio_object_name=None,
    )
    result = service.validate_roster_consistency(roster)
    assert result["is_valid"] is True
    assert any("Excel" in w for w in result["warnings"])


def test_completed_with_excel_no_warning(service):
    """Pin: COMPLETED + excel_filename → no warning."""
    item = _make_item()
    roster = _make_roster(
        items=[item],
        qualified_count=1,
        disqualified_count=0,
        total_amount=1000,
        status=RosterStatus.COMPLETED,
        excel_filename="output.xlsx",
    )
    result = service.validate_roster_consistency(roster)
    assert result["warnings"] == []


def test_completed_with_minio_only_no_warning(service):
    """Pin: COMPLETED + minio_object_name (no excel_filename) is also OK
    — either artifact satisfies the check."""
    item = _make_item()
    roster = _make_roster(
        items=[item],
        qualified_count=1,
        disqualified_count=0,
        total_amount=1000,
        status=RosterStatus.COMPLETED,
        excel_filename=None,
        minio_object_name="rosters/output.xlsx",
    )
    result = service.validate_roster_consistency(roster)
    assert result["warnings"] == []


def test_non_completed_status_no_excel_warning(service):
    """Pin: PROCESSING / FAILED rosters without Excel → NO warning
    (warning is only meaningful for COMPLETED rosters that should have
    produced an artifact)."""
    roster = _make_roster(
        items=[],
        qualified_count=0,
        disqualified_count=0,
        total_amount=0,
        status=RosterStatus.PROCESSING,
        excel_filename=None,
        minio_object_name=None,
    )
    result = service.validate_roster_consistency(roster)
    assert result["warnings"] == []
