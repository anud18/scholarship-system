"""
Tests for `app.models.enums` — the shared enum value contract.

These enum values are written to PostgreSQL ENUM columns (CLAUDE.md §4
mandates Python lowercase names matching DB values exactly) AND read
by the TypeScript frontend (which has its own UPPERCASE enum members
but identical string values). A drift between Python and DB or between
Python and frontend would cause:
- LookupError on read ('value' is not among the defined enum values)
- DB filter queries returning empty results
- Frontend status-display switch statements falling through to default

This test pins every value-string in the 7 shared enums so any rename
surfaces immediately rather than silently breaking a downstream consumer.

7 enums (10 cases). Pure, no DB.
"""

from app.models.enums import (
    ApplicationCycle,
    ApplicationStatus,
    BatchImportStatus,
    QuotaManagementMode,
    ReviewStage,
    Semester,
    SubTypeSelectionMode,
)

# ─── Semester (CLAUDE.md §4 currentenums) ────────────────────────────


def test_semester_values():
    """Pin: Semester values match CLAUDE.md §4 + DB enum.
    Frontend enums.ts uses FIRST/SECOND/YEARLY uppercase names with
    these exact lowercase values."""
    assert Semester.first.value == "first"
    assert Semester.second.value == "second"
    assert Semester.yearly.value == "yearly"
    assert len(list(Semester)) == 3


# ─── ApplicationStatus (12 user-facing outcomes) ─────────────────────


def test_application_status_lifecycle_values():
    """Pin: every ApplicationStatus value used by the student dashboard
    + admin filters. The full lifecycle (draft → submitted → reviewed
    → outcome) plus special states (withdrawn, cancelled, etc.)."""
    assert ApplicationStatus.draft.value == "draft"
    assert ApplicationStatus.submitted.value == "submitted"
    assert ApplicationStatus.under_review.value == "under_review"
    assert ApplicationStatus.pending_documents.value == "pending_documents"
    assert ApplicationStatus.approved.value == "approved"
    assert ApplicationStatus.partial_approved.value == "partial_approved"
    assert ApplicationStatus.rejected.value == "rejected"
    assert ApplicationStatus.returned.value == "returned"
    assert ApplicationStatus.withdrawn.value == "withdrawn"
    assert ApplicationStatus.cancelled.value == "cancelled"
    assert ApplicationStatus.manual_excluded.value == "manual_excluded"
    assert ApplicationStatus.deleted.value == "deleted"


def test_application_status_count_pinned_for_change_review():
    """Pin: 13 statuses defined. Adding a new status without updating
    the frontend switch-statement + admin filters would silently treat
    the new status as 'unknown'. This count forces code review."""
    assert len(list(ApplicationStatus)) == 13


# ─── ReviewStage (16 workflow positions) ─────────────────────────────


def test_review_stage_values():
    """Pin: ReviewStage tracks position in the workflow (distinct from
    ApplicationStatus which tracks the outcome). The admin's workflow
    dashboard groups applications by these stages."""
    assert ReviewStage.student_draft.value == "student_draft"
    assert ReviewStage.student_submitted.value == "student_submitted"
    assert ReviewStage.professor_review.value == "professor_review"
    assert ReviewStage.professor_reviewed.value == "professor_reviewed"
    assert ReviewStage.college_review.value == "college_review"
    assert ReviewStage.college_reviewed.value == "college_reviewed"
    assert ReviewStage.college_ranking.value == "college_ranking"
    assert ReviewStage.college_ranked.value == "college_ranked"
    assert ReviewStage.admin_review.value == "admin_review"
    assert ReviewStage.admin_reviewed.value == "admin_reviewed"
    assert ReviewStage.quota_distribution.value == "quota_distribution"
    assert ReviewStage.quota_distributed.value == "quota_distributed"
    assert ReviewStage.roster_preparation.value == "roster_preparation"
    assert ReviewStage.roster_prepared.value == "roster_prepared"
    assert ReviewStage.roster_submitted.value == "roster_submitted"
    assert ReviewStage.completed.value == "completed"
    assert ReviewStage.archived.value == "archived"


def test_review_stage_count():
    """Pin: 17 stages. Same code-review-forcing pattern as
    ApplicationStatus."""
    assert len(list(ReviewStage)) == 17


# ─── SubTypeSelectionMode (3 modes per CLAUDE.md §4) ─────────────────


def test_subtype_selection_mode_values():
    """Pin: CLAUDE.md §4 documents these exact mode values. Mode is
    used by the scholarship-eligibility frontend to render the right
    sub-type selector (radio vs checkbox vs hierarchical-stepper)."""
    assert SubTypeSelectionMode.single.value == "single"
    assert SubTypeSelectionMode.multiple.value == "multiple"
    assert SubTypeSelectionMode.hierarchical.value == "hierarchical"
    assert len(list(SubTypeSelectionMode)) == 3


# ─── ApplicationCycle (2 modes) ──────────────────────────────────────


def test_application_cycle_values():
    """Pin: CLAUDE.md §4 — semester / yearly. Drives the scholarship
    period selection in admin scholarship-type CRUD."""
    assert ApplicationCycle.semester.value == "semester"
    assert ApplicationCycle.yearly.value == "yearly"
    assert len(list(ApplicationCycle)) == 2


# ─── QuotaManagementMode (4 modes) ───────────────────────────────────


def test_quota_management_mode_values():
    """Pin: CLAUDE.md §4 quota modes. Drives the matrix-allocation UI
    behavior (none → unlimited, simple → single bucket,
    college_based → per-college rows, matrix_based → 2D grid)."""
    assert QuotaManagementMode.none.value == "none"
    assert QuotaManagementMode.simple.value == "simple"
    assert QuotaManagementMode.college_based.value == "college_based"
    assert QuotaManagementMode.matrix_based.value == "matrix_based"
    assert len(list(QuotaManagementMode)) == 4


# ─── BatchImportStatus ───────────────────────────────────────────────


def test_batch_import_status_values():
    """Pin: batch-import status strings used by admin dashboard +
    background job state machine."""
    assert BatchImportStatus.pending.value == "pending"
    assert BatchImportStatus.processing.value == "processing"
    assert BatchImportStatus.completed.value == "completed"
    assert BatchImportStatus.failed.value == "failed"
    assert BatchImportStatus.cancelled.value == "cancelled"
    assert BatchImportStatus.partial.value == "partial"
    assert len(list(BatchImportStatus)) == 6


# ─── Cross-enum invariant: all values lowercase per CLAUDE.md §4 ─────


def test_all_enum_values_are_lowercase():
    """SECURITY-ADJACENT: CLAUDE.md §4 mandates all enum values be
    lowercase to match PostgreSQL ENUM columns exactly. A regression
    introducing an upper-case value would cause:
      LookupError: 'value' is not among the defined enum values

    when SQLAlchemy tries to bind/load the value. Pin the invariant
    across all 7 shared enums."""
    for enum_cls in (
        Semester,
        ApplicationStatus,
        ReviewStage,
        SubTypeSelectionMode,
        ApplicationCycle,
        QuotaManagementMode,
        BatchImportStatus,
    ):
        for member in enum_cls:
            assert (
                member.value == member.value.lower()
            ), f"{enum_cls.__name__}.{member.name} value '{member.value}' is not lowercase"
