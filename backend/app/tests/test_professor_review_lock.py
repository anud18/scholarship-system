"""
Tests for `is_professor_review_locked` + the LOCKED_STAGES_FOR_
PROFESSOR_REVIEW frozenset on `app.services.review_service`.

This is the WORKFLOW GATE that determines whether a professor
can still edit / submit a review on an application. Once the
college takes over, professor edits must be locked so:
  * Different reviewers can't fight over the same record
  * Audit trail stays linear
  * Approval workflow can't be "undone" partway through

A regression in either direction is bad:
  * Lock too aggressive → professors can't fix their own typos
    before college sees the data
  * Lock too lax → professors can override college decisions

Wave 6a102 — pure-helper test wave on a load-bearing review
gate.

12 cases covering:
  - The exact set of locked stages (13 stages)
  - The exact set of unlocked stages (4 stages)
  - Tolerance for SQLAlchemy returning either enum instance or
    string value (per source comment)
  - Defensive None / missing stage behaviour
"""

from types import SimpleNamespace

from app.models.enums import ReviewStage
from app.services.review_service import (
    LOCKED_STAGES_FOR_PROFESSOR_REVIEW,
    is_professor_review_locked,
)

# ─── LOCKED_STAGES_FOR_PROFESSOR_REVIEW constant ─────────────────────


def test_locked_stages_is_frozenset():
    # Pin: type is frozenset (immutable + O(1) lookup). Pin so
    # a refactor to list doesn't silently degrade per-call perf.
    assert isinstance(LOCKED_STAGES_FOR_PROFESSOR_REVIEW, frozenset)


def test_locked_stages_documented_size():
    # Pin: exactly 13 stages locked. If a new stage is added to
    # ReviewStage, this test forces explicit review of whether
    # it belongs in the lock set.
    assert len(LOCKED_STAGES_FOR_PROFESSOR_REVIEW) == 13


def test_locked_stages_contains_all_post_college_stages():
    # Pin: every stage from college_review onward is locked.
    # This is the documented contract.
    expected_locked = {
        ReviewStage.college_review.value,
        ReviewStage.college_reviewed.value,
        ReviewStage.college_ranking.value,
        ReviewStage.college_ranked.value,
        ReviewStage.admin_review.value,
        ReviewStage.admin_reviewed.value,
        ReviewStage.quota_distribution.value,
        ReviewStage.quota_distributed.value,
        ReviewStage.roster_preparation.value,
        ReviewStage.roster_prepared.value,
        ReviewStage.roster_submitted.value,
        ReviewStage.completed.value,
        ReviewStage.archived.value,
    }
    assert LOCKED_STAGES_FOR_PROFESSOR_REVIEW == expected_locked


def test_locked_stages_excludes_professor_stages():
    # Pin: professor_review and professor_reviewed remain editable
    # so professors can iterate on their own input. See issue #64.
    assert ReviewStage.professor_review.value not in LOCKED_STAGES_FOR_PROFESSOR_REVIEW
    assert ReviewStage.professor_reviewed.value not in LOCKED_STAGES_FOR_PROFESSOR_REVIEW


def test_locked_stages_excludes_student_stages():
    # Pin: student_draft and student_submitted are NOT locked from
    # professor's perspective (professor hasn't even started yet).
    assert ReviewStage.student_draft.value not in LOCKED_STAGES_FOR_PROFESSOR_REVIEW
    assert ReviewStage.student_submitted.value not in LOCKED_STAGES_FOR_PROFESSOR_REVIEW


# ─── is_professor_review_locked function ─────────────────────────────


def _app(stage):
    """Helper: build an application-like object with a review_stage."""
    return SimpleNamespace(review_stage=stage)


def test_locked_for_college_review_stage():
    # Pin: once college_review starts, professor is locked out.
    # The #1 use case for this gate.
    assert is_professor_review_locked(_app(ReviewStage.college_review)) is True


def test_unlocked_for_professor_review_stage():
    # Pin: professor_review stage NOT locked — professor is
    # actively reviewing.
    assert is_professor_review_locked(_app(ReviewStage.professor_review)) is False


def test_unlocked_for_student_draft_stage():
    # Pin: student_draft stage not locked (defensive — though
    # the professor shouldn't be reviewing yet, the function
    # should still report unlocked).
    assert is_professor_review_locked(_app(ReviewStage.student_draft)) is False


def test_accepts_string_value_per_source_comment():
    # Pin: source comment says "SQLAlchemy may return either the
    # enum instance or its string value". Function uses getattr
    # fallback. Pinned so a refactor to strict-enum doesn't break
    # the read path when SQLAlchemy returns the raw string.
    assert is_professor_review_locked(_app("college_review")) is True
    assert is_professor_review_locked(_app("professor_review")) is False


def test_completed_stage_is_locked():
    # Pin: archived / completed stages → locked. Professors can't
    # reopen completed reviews.
    assert is_professor_review_locked(_app(ReviewStage.completed)) is True
    assert is_professor_review_locked(_app(ReviewStage.archived)) is True


def test_unknown_string_value_is_not_locked():
    # Pin: unknown stage value → not in locked set → unlocked.
    # Defensive — caller code can rely on "False means definitely
    # unlocked" even when the stage column has garbage.
    assert is_professor_review_locked(_app("some_unknown_stage")) is False
    assert is_professor_review_locked(_app("")) is False
