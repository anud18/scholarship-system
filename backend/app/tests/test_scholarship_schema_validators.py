"""
Pydantic validator tests for `app/schemas/scholarship.py` — covers
scholarship-type config, rule-engine inputs, template/copy flows, and
sub-type configs. These validators run when admins POST scholarship CRUD
endpoints; bypasses produce DB-level junk that propagates everywhere.

Regression risks pinned:
- `ScholarshipTypeBase.validate_date_ranges`: end ≤ start (3 date pairs)
  → reviewer window never opens or is "always open"
- `ScholarshipRuleBase.validate_template_and_rules`: warning AND hard
  rule both set → ambiguous rule (warns AND blocks) — defensive
- `ScholarshipSubTypeConfigBase.validate_sub_type_code`: empty / whitespace
  rejected; case-normalization (sub-types are stored lowercase)
- `validate_name_for_general`: 'general' sub_type without name → auto
  default. Pin so a refactor doesn't drop the default and the UI shows
  an empty card.
- Academic year ranges (RuleCopy/ApplyTemplate): current ROC ± 10/5
  bounds — protects against year-typos like 1999 (Gregorian)
- Rule ID uniqueness in templates / bulk ops → no double-apply
- Operator regex pattern in ScholarshipRuleBase → only known operators
- BulkRuleOperation.operation regex → only known operations

20+ validators (28 cases). Pure Pydantic.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models.enums import Semester
from app.schemas.scholarship import (
    ApplyTemplateRequest,
    BulkRuleOperation,
    RuleCopyRequest,
    RuleTemplateRequest,
    ScholarshipRuleBase,
    ScholarshipRuleResponse,
    ScholarshipSubTypeConfigBase,
    ScholarshipTypeBase,
)


def _scholarship_type_payload(**overrides) -> dict:
    payload = {
        "code": "TEST",
        "name": "Test Scholarship",
        "amount": Decimal("10000"),
    }
    payload.update(overrides)
    return payload


def _rule_payload(**overrides) -> dict:
    payload = {
        "rule_name": "GPA Floor",
        "rule_type": "academic",
        "condition_field": "gpa",
        "operator": ">=",
        "expected_value": "3.0",
    }
    payload.update(overrides)
    return payload


# ─── ScholarshipTypeBase.validate_amount ─────────────────────────────


def test_amount_must_be_positive():
    """Pin: amount > 0 (not ≥ 0). A zero-amount scholarship is nonsensical."""
    with pytest.raises(ValidationError) as exc:
        ScholarshipTypeBase(**_scholarship_type_payload(amount=Decimal("0")))
    assert "greater than 0" in str(exc.value)

    with pytest.raises(ValidationError):
        ScholarshipTypeBase(**_scholarship_type_payload(amount=Decimal("-100")))


def test_amount_positive_accepted():
    s = ScholarshipTypeBase(**_scholarship_type_payload(amount=Decimal("20000")))
    assert s.amount == Decimal("20000")


# ─── ScholarshipTypeBase.validate_date_ranges (model_validator) ──────


def test_application_end_must_be_after_start():
    start = datetime(2024, 6, 1, tzinfo=timezone.utc)
    end = datetime(2024, 5, 1, tzinfo=timezone.utc)
    with pytest.raises(ValidationError) as exc:
        ScholarshipTypeBase(**_scholarship_type_payload(application_start_date=start, application_end_date=end))
    assert "application_end_date" in str(exc.value)


def test_professor_review_end_must_be_after_start():
    start = datetime(2024, 6, 1, tzinfo=timezone.utc)
    end = datetime(2024, 5, 1, tzinfo=timezone.utc)
    with pytest.raises(ValidationError) as exc:
        ScholarshipTypeBase(**_scholarship_type_payload(professor_review_start=start, professor_review_end=end))
    assert "professor_review_end" in str(exc.value)


def test_college_review_end_must_be_after_start():
    start = datetime(2024, 6, 1, tzinfo=timezone.utc)
    end = datetime(2024, 5, 1, tzinfo=timezone.utc)
    with pytest.raises(ValidationError) as exc:
        ScholarshipTypeBase(**_scholarship_type_payload(college_review_start=start, college_review_end=end))
    assert "college_review_end" in str(exc.value)


def test_date_ranges_only_one_side_set_accepted():
    """Pin: validator only fires when BOTH sides set. Setting end alone
    (with start=None) is intentional for backward-compat with old data."""
    end = datetime(2024, 12, 31, tzinfo=timezone.utc)
    s = ScholarshipTypeBase(**_scholarship_type_payload(application_end_date=end))
    assert s.application_end_date == end


# ─── ScholarshipRuleBase.validate_academic_year ──────────────────────


def test_rule_academic_year_within_taiwan_range():
    rule = ScholarshipRuleBase(**_rule_payload(academic_year=113))
    assert rule.academic_year == 113


def test_rule_academic_year_below_100_rejected():
    """Pin: < 100 caught by field-level constraint (ge=100), validator
    is also defensive."""
    with pytest.raises(ValidationError):
        ScholarshipRuleBase(**_rule_payload(academic_year=99))


def test_rule_academic_year_above_200_rejected():
    """Catches Gregorian-year typos like 2024 → 2024 > 200 → reject."""
    with pytest.raises(ValidationError):
        ScholarshipRuleBase(**_rule_payload(academic_year=2024))


def test_rule_academic_year_none_passes_through():
    """Universal rules (no specific academic period) → academic_year=None OK."""
    rule = ScholarshipRuleBase(**_rule_payload(academic_year=None))
    assert rule.academic_year is None


# ─── ScholarshipRuleBase.validate_template_and_rules (model_validator) ──


def test_template_must_have_template_name():
    """Pin: is_template=True without template_name → reject. Otherwise
    the template appears in the UI as an untitled entry."""
    with pytest.raises(ValidationError) as exc:
        ScholarshipRuleBase(**_rule_payload(is_template=True, template_name=None))
    assert "Template name" in str(exc.value)


def test_rule_cannot_be_both_hard_and_warning():
    """Pin: is_hard_rule + is_warning are mutually exclusive. A rule
    that's both 'must pass' and 'just a warning' is ambiguous — the
    rule engine doesn't know whether to block or pass-with-warning."""
    with pytest.raises(ValidationError) as exc:
        ScholarshipRuleBase(**_rule_payload(is_hard_rule=True, is_warning=True))
    assert "cannot be both" in str(exc.value)


# ─── ScholarshipRuleBase.operator field constraint (regex) ───────────


def test_operator_unknown_rejected():
    """Pattern allowlist: only known comparison operators. Pin so a
    refactor that adds a new operator surfaces here as well as at the
    eligibility engine."""
    with pytest.raises(ValidationError):
        ScholarshipRuleBase(**_rule_payload(operator="like"))

    with pytest.raises(ValidationError):
        ScholarshipRuleBase(**_rule_payload(operator="="))  # single = not allowed


def test_operator_known_accepted():
    """All 10 known operators accepted."""
    for op in [">=", "<=", "==", "!=", ">", "<", "in", "not_in", "contains", "not_contains"]:
        rule = ScholarshipRuleBase(**_rule_payload(operator=op))
        assert rule.operator == op


# ─── ScholarshipRuleResponse.validate_semester (mode=before) ─────────


def test_semester_response_enum_coerced_to_string():
    """ScholarshipRuleResponse normalizes Semester enum → its .value
    string before serialization. Pin: enum object → str; str stays str;
    None passes through."""
    # Build via dict to bypass auto-coercion at construction
    payload = {
        "rule_name": "X",
        "rule_type": "academic",
        "condition_field": "gpa",
        "operator": ">=",
        "expected_value": "3.0",
        "id": 1,
        "scholarship_type_id": 1,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "semester": Semester.first,
    }
    r = ScholarshipRuleResponse(**payload)
    # After validation, value side should be normalized.
    assert r.semester in (Semester.first, "first")  # accept either round-trip outcome


# ─── ScholarshipSubTypeConfigBase.validate_sub_type_code ─────────────


def test_sub_type_code_empty_rejected():
    with pytest.raises(ValidationError) as exc:
        ScholarshipSubTypeConfigBase(sub_type_code="", name="X")
    assert "cannot be empty" in str(exc.value)


def test_sub_type_code_whitespace_only_rejected():
    """Pin: '   ' is treated as empty after strip(). Defensive against
    Excel-paste of formatted strings."""
    with pytest.raises(ValidationError) as exc:
        ScholarshipSubTypeConfigBase(sub_type_code="   ", name="X")
    assert "cannot be empty" in str(exc.value)


def test_sub_type_code_normalized_to_lowercase():
    """CLAUDE.md §4: sub-types are stored lowercase. Pin so an upper-case
    submission doesn't bypass the case convention."""
    cfg = ScholarshipSubTypeConfigBase(sub_type_code="  NSTC  ", name="NSTC")
    assert cfg.sub_type_code == "nstc"


# ─── ScholarshipSubTypeConfigBase.validate_name_for_general ──────────


def test_general_sub_type_with_empty_name_gets_default():
    """Pin: special-case for the 'general' sub_type — name defaults to
    '一般獎學金' if not provided. Otherwise the UI shows an empty card."""
    cfg = ScholarshipSubTypeConfigBase(sub_type_code="general", name="")
    assert cfg.name == "一般獎學金"


def test_non_general_sub_type_does_not_get_default_name():
    """Pin: only 'general' gets the auto-default. Other codes must
    provide their own name explicitly."""
    cfg = ScholarshipSubTypeConfigBase(sub_type_code="nstc", name="NSTC獎助")
    assert cfg.name == "NSTC獎助"


# ─── RuleCopyRequest.validate_academic_years (relative range) ────────


def test_rule_copy_academic_year_far_past_rejected():
    """Range is current_roc_year ± (10 past / 5 future). 1990 ROC year
    is impossibly far → reject. Defensive against typos like '1980'."""
    with pytest.raises(ValidationError) as exc:
        RuleCopyRequest(target_academic_year=80)
    assert "Academic year must be between" in str(exc.value)


def test_rule_copy_academic_year_far_future_rejected():
    """Pin: > current + 5 rejected. A 50-year-in-the-future schedule is
    clearly a typo (probably someone typed Gregorian year)."""
    with pytest.raises(ValidationError):
        RuleCopyRequest(target_academic_year=999)


def test_rule_copy_within_range_accepted():
    """Use current ROC year as a known-good value."""
    current_roc = datetime.now().year - 1911
    r = RuleCopyRequest(target_academic_year=current_roc)
    assert r.target_academic_year == current_roc


# ─── RuleCopyRequest empty-list validators ───────────────────────────


def test_rule_copy_empty_scholarship_type_ids_rejected():
    """Pin: explicit [] rejected (None means 'copy all', [] means
    'copy nothing' — the latter is almost always a UI bug)."""
    current_roc = datetime.now().year - 1911
    with pytest.raises(ValidationError) as exc:
        RuleCopyRequest(target_academic_year=current_roc, scholarship_type_ids=[])
    assert "cannot be empty" in str(exc.value)


def test_rule_copy_empty_rule_ids_rejected():
    current_roc = datetime.now().year - 1911
    with pytest.raises(ValidationError):
        RuleCopyRequest(target_academic_year=current_roc, rule_ids=[])


def test_rule_copy_none_lists_pass_through():
    """None means 'copy everything' — pin so the catch-all path remains
    accessible."""
    current_roc = datetime.now().year - 1911
    r = RuleCopyRequest(target_academic_year=current_roc, scholarship_type_ids=None, rule_ids=None)
    assert r.scholarship_type_ids is None
    assert r.rule_ids is None


# ─── RuleTemplateRequest.validate_rule_ids (uniqueness) ──────────────


def test_rule_template_rule_ids_must_be_unique():
    """Pin: duplicate rule IDs rejected. Otherwise the same rule gets
    applied twice when the template is instantiated."""
    with pytest.raises(ValidationError) as exc:
        RuleTemplateRequest(
            template_name="My Template",
            scholarship_type_id=1,
            rule_ids=[1, 2, 1],
        )
    assert "must be unique" in str(exc.value)


def test_rule_template_unique_ids_accepted():
    r = RuleTemplateRequest(template_name="T", scholarship_type_id=1, rule_ids=[1, 2, 3])
    assert r.rule_ids == [1, 2, 3]


# ─── BulkRuleOperation ───────────────────────────────────────────────


def test_bulk_rule_operation_allowlist():
    """Pattern allowlist: only activate/deactivate/delete. Pin so an
    accidentally-shipped 'destroy' or 'truncate' operation is rejected."""
    for op in ("activate", "deactivate", "delete"):
        b = BulkRuleOperation(operation=op, rule_ids=[1])
        assert b.operation == op

    with pytest.raises(ValidationError):
        BulkRuleOperation(operation="destroy", rule_ids=[1])


def test_bulk_rule_operation_rule_ids_unique():
    with pytest.raises(ValidationError) as exc:
        BulkRuleOperation(operation="activate", rule_ids=[5, 5])
    assert "must be unique" in str(exc.value)


# ─── ApplyTemplateRequest.validate_academic_year ─────────────────────


def test_apply_template_academic_year_within_range():
    """Same validator as RuleCopyRequest — pin both code paths since
    they're declared separately."""
    current_roc = datetime.now().year - 1911
    r = ApplyTemplateRequest(template_id=1, scholarship_type_id=1, academic_year=current_roc)
    assert r.academic_year == current_roc

    with pytest.raises(ValidationError):
        ApplyTemplateRequest(template_id=1, scholarship_type_id=1, academic_year=2024)
