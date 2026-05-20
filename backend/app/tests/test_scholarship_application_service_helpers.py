"""
Tests for the remaining pure helpers on `ScholarshipApplicationService`.

Wave 6v covered `ScholarshipService._safe_gpa_to_decimal` and
`_extract_sub_type`. This wave covers the **second class** in the
same module — `ScholarshipApplicationService` — focusing on its
pure helpers:

  - **_calculate_initial_priority(is_renewal, student_id)**:
    renewal applications get +100 priority bonus. Drives the
    "process renewals first" ordering in the queue.

  - **_validate_application_documents(application)**: scans the
    required_documents list against uploaded file document_types
    and reports any missing. Returns (False, "Missing...") with
    sorted list, or (True, "All required documents uploaded").

  - **_meets_renewal_criteria(application)**: currently a stub that
    always returns True. Pin this so the placeholder behaviour is
    documented — when real criteria are implemented, the test
    breaks and forces explicit review.

13 cases. Pure unit tests via SimpleNamespace bypass of SQLAlchemy.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.scholarship_service import ScholarshipApplicationService


@pytest.fixture
def service():
    db = MagicMock()
    return ScholarshipApplicationService(db)


# ─── _calculate_initial_priority ────────────────────────────────────


def test_initial_priority_zero_for_new_application(service):
    # Pin: non-renewal starts at 0. Base score for ranking.
    assert service._calculate_initial_priority(is_renewal=False, student_id=42) == 0


def test_initial_priority_plus_100_for_renewal(service):
    # Pin: renewal bonus is exactly +100. Drives "process renewals
    # first" ordering — flipping the constant would shuffle queue
    # order.
    assert service._calculate_initial_priority(is_renewal=True, student_id=42) == 100


def test_initial_priority_independent_of_student_id(service):
    # Pin: student_id is currently unused in the calculation (only
    # affects renewal flag check). Pinned so a regression that
    # accidentally biases by student_id (e.g. % math) surfaces.
    p1 = service._calculate_initial_priority(is_renewal=True, student_id=1)
    p2 = service._calculate_initial_priority(is_renewal=True, student_id=99999)
    assert p1 == p2


# ─── _validate_application_documents ────────────────────────────────


def _app_with_docs(required_docs, uploaded_doc_types):
    """Build a minimal Application-like object for the validator."""
    app = SimpleNamespace()
    app.scholarship_type = SimpleNamespace(required_documents=required_docs)
    app.files = [SimpleNamespace(document_type=t) for t in uploaded_doc_types]
    return app


def test_validate_documents_all_uploaded(service):
    # Pin: complete uploads return (True, "All required documents
    # uploaded").
    app = _app_with_docs(["transcript", "id_card"], ["transcript", "id_card"])
    ok, msg = service._validate_application_documents(app)
    assert ok is True
    assert msg == "All required documents uploaded"


def test_validate_documents_partial_missing(service):
    # Pin: returns (False, comma-separated list). Endpoint surfaces
    # this string to the student as the rejection reason.
    app = _app_with_docs(["transcript", "id_card", "recommendation"], ["transcript"])
    ok, msg = service._validate_application_documents(app)
    assert ok is False
    assert "id_card" in msg
    assert "recommendation" in msg
    assert "Missing required documents" in msg


def test_validate_documents_no_required_passes(service):
    # Pin: empty required list always passes. Some scholarships
    # don't require documents.
    app = _app_with_docs([], [])
    ok, msg = service._validate_application_documents(app)
    assert ok is True


def test_validate_documents_required_none_treated_as_empty(service):
    # Pin: scholarship_type.required_documents=None coerces to []
    # via the `or []` fallback. Defensive against legacy records
    # without the column populated.
    app = SimpleNamespace()
    app.scholarship_type = SimpleNamespace(required_documents=None)
    app.files = [SimpleNamespace(document_type="anything")]
    ok, msg = service._validate_application_documents(app)
    assert ok is True


def test_validate_documents_extra_uploads_dont_break(service):
    # Pin: uploading EXTRA documents beyond the required list is
    # fine — the validator only checks required ⊆ uploaded.
    app = _app_with_docs(["transcript"], ["transcript", "extra1", "extra2"])
    ok, msg = service._validate_application_documents(app)
    assert ok is True


def test_validate_documents_none_document_type_filtered_out(service):
    # Pin: files with document_type=None are filtered (list-comp
    # condition `if f.document_type`). Pin so a regression that
    # included them in the "uploaded" set would falsely pass a
    # missing document.
    app = SimpleNamespace()
    app.scholarship_type = SimpleNamespace(required_documents=["transcript"])
    app.files = [
        SimpleNamespace(document_type=None),  # filtered out
        SimpleNamespace(document_type="transcript"),
    ]
    ok, msg = service._validate_application_documents(app)
    assert ok is True


def test_validate_documents_only_none_doc_types_yields_missing(service):
    # Pin: all-None files leave the required set unsatisfied.
    app = SimpleNamespace()
    app.scholarship_type = SimpleNamespace(required_documents=["transcript"])
    app.files = [
        SimpleNamespace(document_type=None),
        SimpleNamespace(document_type=None),
    ]
    ok, msg = service._validate_application_documents(app)
    assert ok is False
    assert "transcript" in msg


# ─── _meets_renewal_criteria (stub) ─────────────────────────────────


def test_meets_renewal_criteria_returns_true_placeholder(service):
    # Pin: placeholder always returns True. Pinned so when real
    # criteria are implemented (per the TODO comment in the source),
    # this test breaks and forces explicit review.
    app = SimpleNamespace()  # arbitrary
    assert service._meets_renewal_criteria(app) is True


def test_meets_renewal_criteria_ignores_application_state(service):
    # Pin: also-stub — doesn't read any field. Pin that the
    # implementation doesn't accidentally start reading fields
    # before the criteria logic is in place.
    app_a = SimpleNamespace(id=1, gpa=3.5)
    app_b = SimpleNamespace(id=2, gpa=1.0)
    assert service._meets_renewal_criteria(app_a) is service._meets_renewal_criteria(app_b)
