"""
Tests for the `CollegeReviewCreate`, `CollegeReviewUpdate`, and a few
peripheral schemas in `app/schemas/college_review.py`.

Wave 6a23 already covered `RankingImportItem.validate_rank` and the
ReviewItemCreate.recommendation allowlist (which has 2 values:
approve/reject — the PROFESSOR-LEVEL gate). This wave covers the
COLLEGE-LEVEL gate, which is intentionally wider with a 3-value
regex pattern:

  - `CollegeReviewCreate.recommendation` pattern:
    `^(approve|reject|conditional)$` — the college may issue a
    "conditional approval" requiring follow-up (CLAUDE.md §7
    review-flow). The professor level cannot use "conditional".

  - `review_comments` max=2000, `decision_reason` max=1000 — drift
    would let DB columns silently grow or truncate mid-string.

  - `is_priority` and `needs_special_attention` default to False —
    flipping would mark every application as priority/special-attention
    on creation, which would either swamp dashboards or change
    notification policy.

  - `RankingUpdate.ranking_name` min=1 max=200 — name cap.

15 cases.
"""

import pytest
from pydantic import ValidationError

from app.schemas.college_review import (
    CollegeReviewCreate,
    CollegeReviewUpdate,
    RankingOrderUpdate,
    RankingUpdate,
    StudentPreviewBasic,
    StudentPreviewResponse,
    StudentTermData,
)

# ─── CollegeReviewCreate ─────────────────────────────────────────────


def test_create_requires_recommendation():
    # Pin: recommendation is the only required field on Create (per
    # the recommendation/ranking model — CLAUDE.md §7 no-scoring).
    with pytest.raises(ValidationError):
        CollegeReviewCreate()  # type: ignore[call-arg]


@pytest.mark.parametrize("value", ["approve", "reject", "conditional"])
def test_create_recommendation_accepts_all_three_values(value):
    # Pin: COLLEGE level has 3 valid recommendations. Professor level
    # has only 2 (approve/reject) — pinned in wave 6a23. Do not
    # narrow this set silently — "conditional" is a documented
    # workflow state per CLAUDE.md §7.
    r = CollegeReviewCreate(recommendation=value)
    assert r.recommendation == value


def test_create_recommendation_rejects_partial_approve():
    # Pin: "partial_approve" is a synthetic state for the OVERALL
    # application status, NOT a value an individual college review
    # can set. Drift would let the college issue ambiguous results.
    with pytest.raises(ValidationError):
        CollegeReviewCreate(recommendation="partial_approve")


def test_create_recommendation_rejects_arbitrary_strings():
    with pytest.raises(ValidationError):
        CollegeReviewCreate(recommendation="maybe")


def test_create_review_comments_max_length_2000():
    with pytest.raises(ValidationError):
        CollegeReviewCreate(recommendation="approve", review_comments="x" * 2001)


def test_create_decision_reason_max_length_1000():
    # Pin: decision_reason cap is half of review_comments cap. They
    # serve different purposes — the reason is short justification;
    # comments are full notes.
    with pytest.raises(ValidationError):
        CollegeReviewCreate(recommendation="approve", decision_reason="x" * 1001)


def test_create_is_priority_defaults_false():
    # Pin: most applications are not priority. Flipping default would
    # swamp the priority dashboard.
    r = CollegeReviewCreate(recommendation="approve")
    assert r.is_priority is False


def test_create_needs_special_attention_defaults_false():
    # Pin: most applications need no special attention. Flipping
    # would silently change notification policy.
    r = CollegeReviewCreate(recommendation="approve")
    assert r.needs_special_attention is False


def test_create_rank_fields_optional():
    # Pin: preliminary_rank / final_rank can be set later during
    # review iteration — not required on initial creation.
    r = CollegeReviewCreate(recommendation="approve")
    assert r.preliminary_rank is None
    assert r.final_rank is None


# ─── CollegeReviewUpdate ─────────────────────────────────────────────


def test_update_all_fields_optional():
    # Pin: PATCH semantics — empty body valid.
    obj = CollegeReviewUpdate()
    assert obj.recommendation is None
    assert obj.review_comments is None


def test_update_recommendation_pattern_inherited():
    # Pin: same pattern as Create applies when value is supplied.
    with pytest.raises(ValidationError):
        CollegeReviewUpdate(recommendation="maybe")


# ─── RankingUpdate / RankingOrderUpdate ─────────────────────────────


def test_ranking_name_min_length_1():
    # Pin: ranking_name min=1 — empty string rejected. Ranking lists
    # need a label for staff to identify them.
    with pytest.raises(ValidationError):
        RankingUpdate(ranking_name="")


def test_ranking_name_max_length_200():
    with pytest.raises(ValidationError):
        RankingUpdate(ranking_name="x" * 201)


def test_ranking_order_update_required_fields():
    # Pin: drag-and-drop reorder API needs both item_id and position.
    with pytest.raises(ValidationError):
        RankingOrderUpdate(item_id=1)  # type: ignore[call-arg]


# ─── StudentPreview schemas ─────────────────────────────────────────


def test_student_preview_basic_required_anchor():
    # Pin: student_id + student_name required. The preview popup
    # always shows the student identifier — blank would surface as
    # "Loading..." stuck.
    with pytest.raises(ValidationError):
        StudentPreviewBasic(student_id="X")  # type: ignore[call-arg]


def test_student_preview_response_recent_terms_defaults_empty():
    # Pin: recent_terms defaults to [] via default_factory. A
    # regression to None would break .map() iteration on the
    # frontend.
    r = StudentPreviewResponse(
        basic=StudentPreviewBasic(student_id="X", student_name="Y"),
    )
    assert r.recent_terms == []
