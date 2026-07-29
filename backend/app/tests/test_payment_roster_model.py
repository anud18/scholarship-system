"""
Pure-property tests for `PaymentRoster` and `PaymentRosterItem` models.

These drive the payment workflow — the LAST gate before money moves.
`is_included` is the single judgement that decides who is on the roster,
how many people it reports and how much money it totals; a regression
would either drop qualified students off the payment file or inflate the
declared total.

The lock-state transitions are immutability invariants: a locked
roster MUST NOT be re-locked (would overwrite the `locked_by`
attribution → audit-trail forgery).

7 helpers / properties covered:
- `PaymentRoster.is_locked / can_be_modified / is_completed`
- `PaymentRoster.lock()`
- `PaymentRoster.generate_excel_filename()`
- `PaymentRosterItem.is_eligible`
- `PaymentRosterItem.generate_excel_remarks()`
- `verification_status_label()`
"""

import re
from datetime import datetime, timezone

import pytest

from app.models.payment_roster import (
    STUDENT_VERIFICATION_STATUS_LABELS,
    PaymentRoster,
    PaymentRosterItem,
    RosterStatus,
    StudentVerificationStatus,
    verification_status_label,
)


def _roster(**overrides) -> PaymentRoster:
    """Build a transient PaymentRoster for pure-property tests (no DB needed)."""
    defaults = {
        "id": 1,
        "roster_code": "ROSTER-114-2024",
        "status": RosterStatus.DRAFT,
        "locked_at": None,
        "locked_by": None,
    }
    defaults.update(overrides)
    return PaymentRoster(**defaults)


def _item(**overrides) -> PaymentRosterItem:
    defaults = {
        "id": 1,
        "student_id_number": "S12345",
        "student_name": "Test Student",
        "bank_account": "0001234567",
        "verification_status": StudentVerificationStatus.VERIFIED,
        "is_included": True,
        "exclusion_reason": None,
        "warning_rules": None,
    }
    defaults.update(overrides)
    return PaymentRosterItem(**defaults)


# ─── PaymentRoster.is_locked / can_be_modified / is_completed ──────


def test_is_locked_only_when_status_locked():
    """is_locked = (status == LOCKED). Pin so semantic drift doesn't
    silently allow modification of locked rosters."""
    assert _roster(status=RosterStatus.LOCKED).is_locked is True
    for s in (RosterStatus.DRAFT, RosterStatus.COMPLETED, RosterStatus.FAILED, RosterStatus.PROCESSING):
        assert _roster(status=s).is_locked is False, f"status={s}"


def test_can_be_modified_only_draft_or_failed():
    """Pin the 2-status modifiable set. Processing/completed/locked
    rosters MUST NOT be modifiable — would corrupt the payment file."""
    assert _roster(status=RosterStatus.DRAFT).can_be_modified is True
    assert _roster(status=RosterStatus.FAILED).can_be_modified is True
    for s in (RosterStatus.PROCESSING, RosterStatus.COMPLETED, RosterStatus.LOCKED):
        assert _roster(status=s).can_be_modified is False, f"status={s}"


def test_is_completed_for_completed_and_locked():
    """is_completed includes LOCKED — locked is a terminal state."""
    assert _roster(status=RosterStatus.COMPLETED).is_completed is True
    assert _roster(status=RosterStatus.LOCKED).is_completed is True
    for s in (RosterStatus.DRAFT, RosterStatus.PROCESSING, RosterStatus.FAILED):
        assert _roster(status=s).is_completed is False


# ─── PaymentRoster.lock() ───────────────────────────────────────────


def test_lock_sets_status_timestamp_and_user():
    """Locking a draft roster transitions to LOCKED + stamps timestamp
    + records who locked it."""
    r = _roster(status=RosterStatus.DRAFT)
    r.lock(locked_by_user_id=99)
    assert r.status == RosterStatus.LOCKED
    assert r.locked_by == 99
    assert r.locked_at is not None
    # Within last second (sanity check the timezone-aware utcnow path).
    assert (datetime.now(timezone.utc) - r.locked_at).total_seconds() < 1


def test_lock_idempotency_guard_raises():
    """SECURITY-CRITICAL: re-locking an already-locked roster MUST
    raise ValueError. This prevents overwriting the original
    `locked_by` attribution → audit-trail forgery guard."""
    r = _roster(status=RosterStatus.LOCKED, locked_by=10)
    with pytest.raises(ValueError, match="already locked"):
        r.lock(locked_by_user_id=99)
    # Locked_by must remain the original user.
    assert r.locked_by == 10


# ─── PaymentRoster.generate_excel_filename ─────────────────────────


def test_excel_filename_format():
    """Format: roster_{code}_{YYYYMMDD_HHMMSS}.xlsx. Pin so the
    timestamp uses UTC (cross-server consistency) and the code is
    embedded."""
    r = _roster(roster_code="ROSTER-114-A")
    fn = r.generate_excel_filename()
    assert fn.startswith("roster_ROSTER-114-A_")
    assert fn.endswith(".xlsx")
    # Timestamp pattern YYYYMMDD_HHMMSS.
    assert re.search(r"_\d{8}_\d{6}\.xlsx$", fn)


# ─── verification_status_label ─────────────────────────────────────


def test_verification_status_labels_are_traditional_chinese():
    """exclusion_reason / Excel 欄位直接顯示這些標籤，不得外洩英文列舉值
    (e.g. `學籍驗證未通過: suspended`)。"""
    for status in StudentVerificationStatus:
        label = verification_status_label(status)
        assert label != status.value
        assert not re.search(r"[A-Za-z_]", label)


def test_verification_status_label_covers_every_member():
    """A new StudentVerificationStatus member without a label would leak
    its raw value into the UI — pin the map's completeness."""
    assert set(STUDENT_VERIFICATION_STATUS_LABELS) == set(StudentVerificationStatus)


# ─── PaymentRosterItem.is_eligible ─────────────────────────────────


def test_is_eligible_none_without_snapshot():
    """Items predating rule-validation snapshots have no verdict; the
    UI renders '-' rather than a reconstructed (possibly stale) one."""
    assert _item(rule_validation_result=None).is_eligible is None
    assert _item(rule_validation_result={}).is_eligible is None


def test_is_eligible_reflects_snapshot_verdict():
    """The generation-time verdict wins — including a False verdict with
    empty failed_rules (e.g. a verification-error snapshot)."""
    assert _item(rule_validation_result={"is_eligible": True, "failed_rules": []}).is_eligible is True
    assert _item(rule_validation_result={"is_eligible": False, "failed_rules": []}).is_eligible is False


def test_missing_bank_account_stays_included():
    """規則資格 (is_eligible) 與納入造冊 (is_included) 都不受郵局帳號影響：
    缺帳號是可補件的行政缺漏，不得把學生踢出造冊名單/人數/總金額。
    提醒僅出現在 Excel 說明欄。"""
    item = _item(bank_account=None, rule_validation_result={"is_eligible": True})
    assert item.is_eligible is True
    assert item.is_included is True
    assert "缺少郵局帳號資訊" in item.generate_excel_remarks("2024-09", "PHD")


# ─── PaymentRosterItem.generate_excel_remarks ──────────────────────


def test_excel_remarks_qualified_baseline():
    """Qualified item gets '合格' as the third remark (after period +
    scholarship). Pin the order: period → scholarship → status."""
    item = _item()
    remarks = item.generate_excel_remarks("2024-09", "PHD_NSTC")
    parts = remarks.split("; ")
    assert "造冊期間: 2024-09" in parts
    assert "獎學金: PHD_NSTC" in parts
    assert "合格" in parts


def test_excel_remarks_excluded_shows_reason():
    """Excluded item's remarks include the exclusion_reason — finance
    team needs to see why."""
    item = _item(is_included=False, exclusion_reason="manual exclusion by admin")
    remarks = item.generate_excel_remarks("2024-09", "PHD")
    assert "排除原因: manual exclusion by admin" in remarks


def test_excel_remarks_unverified_shows_verification_status():
    """Verification failure → 繁體中文 status label in remarks (never the
    raw enum value — the 說明欄 is承辦人-facing)."""
    item = _item(verification_status=StudentVerificationStatus.GRADUATED)
    remarks = item.generate_excel_remarks("2024-09", "PHD")
    assert "學籍狀態: 已畢業" in remarks


def test_excel_remarks_missing_bank_account_flagged():
    """is_included + verified but no bank → '缺少郵局帳號資訊'."""
    item = _item(bank_account=None)
    remarks = item.generate_excel_remarks("2024-09", "PHD")
    assert "缺少郵局帳號資訊" in remarks


def test_excel_remarks_warning_rules_appended():
    """Warning rules (non-blocking) appended as last segment."""
    item = _item(warning_rules=["GPA borderline", "Late submission"])
    remarks = item.generate_excel_remarks("2024-09", "PHD")
    assert "警告:" in remarks
    assert "GPA borderline" in remarks
    assert "Late submission" in remarks
