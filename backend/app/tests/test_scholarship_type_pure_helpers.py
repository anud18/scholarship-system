"""
Pure-helper tests for `ScholarshipType` model.

These helpers run on every student-side scholarship card load (whitelist
check) AND during eligibility gating (sub-type selection validation).

Bugs cause:
- Whitelist bypass (every student sees scholarships they shouldn't) →
  privacy + budget overrun
- Sub-type selection sneaking past gate → application rejected later
  with confusing error
- Code-based main/sub type extraction wrong → routing chaos

5 pure helpers covered (16 cases):
- `is_valid_sub_type_selection`  : single/multiple/hierarchical modes
- `is_student_in_whitelist`      : 3-state security gate
- `get_main_type_from_code`      : substring → bucketed main type
- `get_sub_type_from_code`       : substring → sub-type slug
- `validate_sub_type_list`       : list shape validation
"""

import pytest

from app.models.enums import SubTypeSelectionMode
from app.models.scholarship import ScholarshipType


def _scholarship(**overrides):
    """Construct an in-memory ScholarshipType (no DB session)."""
    defaults = {
        "id": 1,
        "code": "PHD_NSTC_2024",
        "sub_type_selection_mode": SubTypeSelectionMode.single,
        "sub_type_list": ["nstc", "moe_1w", "moe_2w"],
        "whitelist_enabled": False,
        "whitelist_student_ids": None,
    }
    defaults.update(overrides)
    # Construct via __init__ to get _sa_instance_state, then stuff __dict__
    # directly so vestigial/non-column keys are tolerated (bypasses descriptors).
    s = ScholarshipType()
    s.__dict__.update(defaults)
    return s


# ─── is_valid_sub_type_selection ─────────────────────────────────────


def test_single_mode_requires_exactly_one_from_list():
    """single mode: exactly one selected, must be in sub_type_list."""
    s = _scholarship(sub_type_selection_mode=SubTypeSelectionMode.single)
    assert s.is_valid_sub_type_selection(["nstc"]) is True
    assert s.is_valid_sub_type_selection([]) is False  # too few
    assert s.is_valid_sub_type_selection(["nstc", "moe_1w"]) is False  # too many
    assert s.is_valid_sub_type_selection(["unknown"]) is False  # not in list


def test_multiple_mode_allows_any_subset():
    """multiple mode: any subset of the allowed list."""
    s = _scholarship(sub_type_selection_mode=SubTypeSelectionMode.multiple)
    assert s.is_valid_sub_type_selection(["nstc"]) is True
    assert s.is_valid_sub_type_selection(["nstc", "moe_1w"]) is True
    assert s.is_valid_sub_type_selection([]) is True  # empty is OK
    assert s.is_valid_sub_type_selection(["nstc", "unknown"]) is False  # one invalid


def test_hierarchical_mode_requires_ordered_prefix():
    """hierarchical mode: selection must be a prefix of sub_type_list in
    order — A → AB → ABC. Pin so the strict-prefix invariant is
    preserved (a 'set equal to prefix' semantics would be wrong)."""
    s = _scholarship(sub_type_selection_mode=SubTypeSelectionMode.hierarchical)
    assert s.is_valid_sub_type_selection(["nstc"]) is True
    assert s.is_valid_sub_type_selection(["nstc", "moe_1w"]) is True
    assert s.is_valid_sub_type_selection(["nstc", "moe_1w", "moe_2w"]) is True
    # Out of order → invalid
    assert s.is_valid_sub_type_selection(["moe_1w", "nstc"]) is False
    # Skips ahead → invalid
    assert s.is_valid_sub_type_selection(["nstc", "moe_2w"]) is False


# ─── is_student_in_whitelist (3-state security gate) ─────────────────


def test_whitelist_disabled_returns_true_for_anyone():
    """Whitelist not enabled ⇒ everyone passes. Default open."""
    s = _scholarship(whitelist_enabled=False)
    assert s.is_student_in_whitelist(123) is True


def test_whitelist_enabled_empty_returns_false_for_anyone():
    """SECURITY-CRITICAL: enabled + empty list = no-one. Pin so the
    accidentally-enabled-empty-whitelist state doesn't fall through to
    'everyone allowed'. This is the 'fail closed' contract."""
    s = _scholarship(whitelist_enabled=True, whitelist_student_ids=[])
    assert s.is_student_in_whitelist(123) is False
    s2 = _scholarship(whitelist_enabled=True, whitelist_student_ids=None)
    assert s2.is_student_in_whitelist(123) is False


def test_whitelist_enabled_membership_check():
    """Standard whitelist check."""
    s = _scholarship(whitelist_enabled=True, whitelist_student_ids=[42, 100, 200])
    assert s.is_student_in_whitelist(42) is True
    assert s.is_student_in_whitelist(100) is True
    assert s.is_student_in_whitelist(999) is False


# ─── get_main_type_from_code ─────────────────────────────────────────


def test_main_type_extraction_priority():
    """Substring match order matters — UNDERGRADUATE_FRESHMAN > DIRECT_PHD
    > PHD > GENERAL. Pin precedence so a code like 'DIRECT_PHD_PROGRAM'
    isn't accidentally tagged 'PHD'."""
    assert _scholarship(code="UNDERGRADUATE_FRESHMAN_2024").get_main_type_from_code() == "UNDERGRADUATE_FRESHMAN"
    assert _scholarship(code="DIRECT_PHD_PROGRAM").get_main_type_from_code() == "DIRECT_PHD"
    assert _scholarship(code="PHD_NSTC").get_main_type_from_code() == "PHD"
    assert _scholarship(code="ACADEMIC_EXCELLENCE").get_main_type_from_code() == "GENERAL"


def test_main_type_is_case_insensitive():
    """code.upper() means lowercase codes still match."""
    assert _scholarship(code="phd_nstc").get_main_type_from_code() == "PHD"


# ─── get_sub_type_from_code ──────────────────────────────────────────


def test_sub_type_extraction_chain():
    """NSTC → MOE_1W → MOE_2W → GENERAL substring chain."""
    assert _scholarship(code="PHD_NSTC").get_sub_type_from_code() == "NSTC"
    assert _scholarship(code="PHD_MOE_1W").get_sub_type_from_code() == "MOE_1W"
    assert _scholarship(code="PHD_MOE_2W").get_sub_type_from_code() == "MOE_2W"
    assert _scholarship(code="UNDERGRAD_REGULAR").get_sub_type_from_code() == "GENERAL"


def test_sub_type_moe_2w_doesnt_match_moe_1w_prefix():
    """Pin: MOE_2W code shouldn't match the MOE_1W check (the substring
    'MOE_1W' isn't in 'MOE_2W'). Defensive against ordering refactor
    that swaps the checks."""
    s = _scholarship(code="PHD_MOE_2W")
    assert s.get_sub_type_from_code() == "MOE_2W"


# ─── validate_sub_type_list ──────────────────────────────────────────


def test_validate_sub_type_list_empty_is_valid():
    """Empty list valid (no sub-types configured)."""
    assert _scholarship(sub_type_list=[]).validate_sub_type_list() is True
    assert _scholarship(sub_type_list=None).validate_sub_type_list() is True


def test_validate_sub_type_list_string_members_pass():
    """Non-empty strings are valid (configuration-driven, no enum)."""
    assert _scholarship(sub_type_list=["nstc", "moe_1w"]).validate_sub_type_list() is True


def test_validate_sub_type_list_rejects_whitespace_and_non_strings():
    """Whitespace-only ('   ') and non-strings (None, int) → invalid.
    Pin against config corruption."""
    assert _scholarship(sub_type_list=["nstc", ""]).validate_sub_type_list() is False
    assert _scholarship(sub_type_list=["nstc", "   "]).validate_sub_type_list() is False
    assert _scholarship(sub_type_list=["nstc", None]).validate_sub_type_list() is False
    assert _scholarship(sub_type_list=["nstc", 42]).validate_sub_type_list() is False
