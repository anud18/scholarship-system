"""
Pydantic validator tests for `review.py` + `college_review.py` input
schemas — the gates between reviewer-facing UIs and the review database.

`ReviewItemCreate.validate_recommendation` is a SECURITY-CRITICAL
allowlist: only 'approve' / 'reject' accepted. A bypass would let the
frontend ship junk values (or an injected 'partial_approve' through a
single-item submission) that downstream logic interprets unsafely.

`RankingImportItem.validate_rank` powers college ranking Excel imports.
Bool-passes-as-int is the canonical Python gotcha; floats with non-zero
fractional parts must reject; bare ints must be ≥ 1; the 'N' sentinel
must round-trip case-insensitively. A single mis-typed cell ranking a
student at 0 would distort the entire college's preliminary rank list.

5 validators (19 cases). Pure Pydantic, no DB.
"""

import pytest
from pydantic import ValidationError

from app.schemas.college_review import RankingImportItem
from app.schemas.review import ReviewCreate, ReviewItemCreate, ReviewSubmitRequest

# ─── ReviewItemCreate.validate_recommendation ────────────────────────


def test_recommendation_approve_accepted():
    r = ReviewItemCreate(sub_type_code="nstc", recommendation="approve")
    assert r.recommendation == "approve"


def test_recommendation_reject_accepted():
    r = ReviewItemCreate(sub_type_code="nstc", recommendation="reject")
    assert r.recommendation == "reject"


def test_recommendation_partial_approve_rejected():
    """SECURITY-CRITICAL: 'partial_approve' is an aggregated overall
    status — it must NOT be submittable at the item level. Otherwise a
    reviewer could ship arbitrary recommendation values that downstream
    interprets as approved-ish."""
    with pytest.raises(ValidationError) as exc:
        ReviewItemCreate(sub_type_code="nstc", recommendation="partial_approve")
    assert "approve" in str(exc.value) and "reject" in str(exc.value)


def test_recommendation_empty_string_rejected():
    with pytest.raises(ValidationError):
        ReviewItemCreate(sub_type_code="nstc", recommendation="")


def test_recommendation_case_sensitive():
    """Pin: case-sensitive allowlist. 'Approve' / 'APPROVE' do NOT match.
    Defensive: stops a UI that lowercases inconsistently from sneaking
    through."""
    with pytest.raises(ValidationError):
        ReviewItemCreate(sub_type_code="nstc", recommendation="Approve")
    with pytest.raises(ValidationError):
        ReviewItemCreate(sub_type_code="nstc", recommendation="APPROVE")


# ─── ReviewSubmitRequest.validate_items ──────────────────────────────


def test_review_submit_rejects_empty_items_list():
    """Pin: empty list rejected by both Field(min_length=1) AND the
    explicit validator. Defense-in-depth — pin the redundancy."""
    with pytest.raises(ValidationError) as exc:
        ReviewSubmitRequest(items=[])
    msg = str(exc.value)
    # Either the field constraint or the validator can surface — both are valid signals.
    assert "items" in msg or "至少需要一個" in msg


def test_review_submit_accepts_single_item():
    """min_length=1 — exactly one item is OK."""
    item = ReviewItemCreate(sub_type_code="nstc", recommendation="approve")
    req = ReviewSubmitRequest(items=[item])
    assert len(req.items) == 1


def test_review_submit_accepts_multiple_items():
    """Multiple sub-types in one submission — pin so the bulk-approve UX
    path remains accessible."""
    items = [
        ReviewItemCreate(sub_type_code="nstc", recommendation="approve"),
        ReviewItemCreate(sub_type_code="moe_1w", recommendation="reject", comments="GPA太低"),
    ]
    req = ReviewSubmitRequest(items=items)
    assert len(req.items) == 2


# ─── ReviewCreate.validate_items (parallel internal schema) ──────────


def test_review_create_rejects_empty_items_list():
    """ReviewCreate has the same empty-list rejection (separate code
    path used by internal service calls). Pin both so a refactor
    consolidating them doesn't silently drop one."""
    with pytest.raises(ValidationError):
        ReviewCreate(application_id=1, items=[])


def test_review_create_accepts_single_item():
    item = ReviewItemCreate(sub_type_code="nstc", recommendation="approve")
    rc = ReviewCreate(application_id=42, items=[item])
    assert rc.application_id == 42
    assert len(rc.items) == 1


# ─── RankingImportItem.validate_rank ─────────────────────────────────


def test_rank_positive_int_accepted():
    item = RankingImportItem(student_id="0856001", student_name="王小明", rank_position=1)
    assert item.rank_position == 1


def test_rank_string_n_accepted_as_sentinel():
    """'N' = rejected applicant. Pin both casings ('N' / 'n')."""
    item = RankingImportItem(student_id="0856001", student_name="X", rank_position="N")
    assert item.rank_position == "N"

    item2 = RankingImportItem(student_id="0856001", student_name="X", rank_position="n")
    assert item2.rank_position == "N"  # normalized to uppercase


def test_rank_string_with_whitespace_normalized():
    """Excel sometimes adds trailing spaces — pin strip() behavior."""
    item = RankingImportItem(student_id="0856001", student_name="X", rank_position="  N  ")
    assert item.rank_position == "N"


def test_rank_numeric_string_coerced_to_int():
    """Excel exports numbers as strings — '5' must become int 5."""
    item = RankingImportItem(student_id="0856001", student_name="X", rank_position="5")
    assert item.rank_position == 5
    assert isinstance(item.rank_position, int)


def test_rank_zero_rejected():
    """Pin: rank must be ≥ 1. A 0-rank would slot before #1 in
    downstream sorting → distorts the entire preliminary rank list."""
    with pytest.raises(ValidationError) as exc:
        RankingImportItem(student_id="0856001", student_name="X", rank_position=0)
    assert "正整數" in str(exc.value)


def test_rank_negative_rejected():
    with pytest.raises(ValidationError):
        RankingImportItem(student_id="0856001", student_name="X", rank_position=-3)


def test_rank_bool_rejected_first():
    """Pin the canonical Python gotcha: `bool is subclass of int`. If the
    isinstance check didn't reject booleans FIRST, True would silently
    coerce to rank=1 (and False to rank=0). The bool guard must run
    before the int branch."""
    with pytest.raises(ValidationError) as exc:
        RankingImportItem(student_id="0856001", student_name="X", rank_position=True)
    assert "正整數或 'N'" in str(exc.value)

    with pytest.raises(ValidationError):
        RankingImportItem(student_id="0856001", student_name="X", rank_position=False)


def test_rank_non_integer_float_rejected():
    """3.5 → reject. A float that's actually an integer (5.0) should
    coerce. This branch handles Excel's tendency to load 5 as 5.0."""
    with pytest.raises(ValidationError) as exc:
        RankingImportItem(student_id="0856001", student_name="X", rank_position=3.5)
    assert "整數" in str(exc.value)

    # 5.0 is an integer-valued float → accepted as int(5)
    item = RankingImportItem(student_id="0856001", student_name="X", rank_position=5.0)
    assert item.rank_position == 5
    assert isinstance(item.rank_position, int)


def test_rank_garbage_string_rejected():
    """Pin: non-numeric, non-N strings rejected. Otherwise typos in
    Excel cells silently become string-comparison junk downstream."""
    with pytest.raises(ValidationError):
        RankingImportItem(student_id="0856001", student_name="X", rank_position="abc")
