"""
Pure-property tests for `UserProfile` and `BankVerificationTask` models.

UserProfile.profile_completion_percentage drives the dashboard "Complete
your profile" prompt — wrong percentage either hides the prompt for
incomplete users (silent gaps on payment day) or keeps nagging fully-
complete users (UX noise).

BankVerificationTask.progress_percentage powers the admin task monitor
modal; division-by-zero would crash the progress bar CSS.

6 properties covered (14 cases):
- `UserProfile.has_complete_bank_info`
- `UserProfile.has_advisor_info`
- `UserProfile.profile_completion_percentage`
- `BankVerificationTask.is_completed / is_running / progress_percentage`
"""

import pytest

from app.models.bank_verification_task import BankVerificationTask, BankVerificationTaskStatus
from app.models.user_profile import UserProfile


def _profile(**overrides) -> UserProfile:
    p = object.__new__(UserProfile)
    defaults = {
        "id": 1,
        "user_id": 42,
        "account_number": None,
        "advisor_name": None,
        "advisor_email": None,
        "advisor_nycu_id": None,
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        object.__setattr__(p, k, v)
    return p


def _task(**overrides) -> BankVerificationTask:
    t = object.__new__(BankVerificationTask)
    defaults = {
        "id": 1,
        "task_id": "task-001",
        "status": BankVerificationTaskStatus.pending,
        "total_count": 0,
        "processed_count": 0,
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        object.__setattr__(t, k, v)
    return t


# ─── UserProfile.has_complete_bank_info ──────────────────────────────


def test_has_complete_bank_info_truthy_account():
    """Pin: 'complete bank info' requires only account_number set.
    Other bank fields (bank code, etc) NOT required — pin so a future
    refactor adding more required fields surfaces here."""
    assert _profile(account_number="0001234567").has_complete_bank_info is True


def test_has_complete_bank_info_falsy_when_missing():
    assert _profile(account_number=None).has_complete_bank_info is False
    assert _profile(account_number="").has_complete_bank_info is False


# ─── UserProfile.has_advisor_info ────────────────────────────────────


def test_has_advisor_info_requires_all_three_fields():
    """ALL three fields (name + email + nycu_id) must be set. Pin so a
    partial-data profile doesn't count as 'complete' for the
    professor-review routing logic."""
    p = _profile(advisor_name="Prof Wang", advisor_email="w@u.tw", advisor_nycu_id="A0001")
    assert p.has_advisor_info is True


def test_has_advisor_info_falsy_when_any_missing():
    """Any one field missing → False. Pin all three combinations."""
    assert _profile(advisor_name="X", advisor_email="x@u.tw", advisor_nycu_id=None).has_advisor_info is False
    assert _profile(advisor_name="X", advisor_email=None, advisor_nycu_id="A1").has_advisor_info is False
    assert _profile(advisor_name=None, advisor_email="x@u.tw", advisor_nycu_id="A1").has_advisor_info is False


# ─── profile_completion_percentage ───────────────────────────────────


def test_completion_zero_when_nothing_complete():
    """No bank info + no advisor info → 0%."""
    assert _profile().profile_completion_percentage == 0


def test_completion_50_when_one_section_complete():
    """Bank only → 50% (1/2 sections)."""
    p = _profile(account_number="0001234567")
    assert p.profile_completion_percentage == 50

    # Advisor only → 50%.
    p2 = _profile(advisor_name="X", advisor_email="x@u.tw", advisor_nycu_id="A1")
    assert p2.profile_completion_percentage == 50


def test_completion_100_when_all_sections_complete():
    p = _profile(account_number="0001234567", advisor_name="X", advisor_email="x@u.tw", advisor_nycu_id="A1")
    assert p.profile_completion_percentage == 100


def test_completion_returns_int_not_float():
    """Pin int return — UI expects '50%' not '50.0%'. Math is (n/2)*100
    which gives floats; the int() cast in the impl is load-bearing."""
    p = _profile(account_number="x")
    result = p.profile_completion_percentage
    assert isinstance(result, int)


# ─── BankVerificationTask.is_completed ───────────────────────────────


def test_is_completed_for_completed_and_failed():
    """Pin: 'completed' is the umbrella for terminal-but-done states
    (success + failure), NOT just success. Cancelled is NOT completed
    — it's a distinct terminal state for which 'completed' semantics
    don't apply (admin re-runnable)."""
    assert _task(status=BankVerificationTaskStatus.completed).is_completed is True
    assert _task(status=BankVerificationTaskStatus.failed).is_completed is True
    assert _task(status=BankVerificationTaskStatus.cancelled).is_completed is False
    assert _task(status=BankVerificationTaskStatus.pending).is_completed is False
    assert _task(status=BankVerificationTaskStatus.processing).is_completed is False


def test_is_running_only_when_processing():
    """is_running narrower than 'active' — only 'processing' counts.
    Pending isn't running (queued)."""
    assert _task(status=BankVerificationTaskStatus.processing).is_running is True
    assert _task(status=BankVerificationTaskStatus.pending).is_running is False


# ─── BankVerificationTask.progress_percentage ────────────────────────


def test_progress_percentage_zero_division_guard():
    """total_count=0 → 0.0 (avoid NaN crashing the progress bar CSS
    that uses 'width: {percent}%')."""
    assert _task(total_count=0, processed_count=0).progress_percentage == 0.0


def test_progress_percentage_partial():
    assert _task(total_count=100, processed_count=25).progress_percentage == 25.0
    assert _task(total_count=4, processed_count=1).progress_percentage == 25.0


def test_progress_percentage_full():
    assert _task(total_count=10, processed_count=10).progress_percentage == 100.0
