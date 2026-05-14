"""
Pure-function tests for `AnalyticsService._calculate_overview_metrics`.

Drives the admin dashboard's overview stats panel: approval rate,
rejection rate, pending rate, average processing time. A regression
here would silently mis-report scholarship effectiveness to leadership.

7 cases pinning rate calculations + edge cases:
- Empty list returns zero values, no division-by-zero crash.
- Status counts (approved/rejected/pending) split correctly.
- Approval rate computed from approved/total.
- Average processing time computed from submitted_at → decision_date.
- Processing-time samples count reflects only valid (>=0 day) entries.
- Pending counts include both submitted and under_review.
- Decision date or submission date missing ⇒ skipped from
  processing-time average.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.application import ApplicationStatus
from app.services.analytics_service import ScholarshipAnalyticsService


def _app(*, status, submitted_at=None, decision_date=None) -> SimpleNamespace:
    """Build a duck-typed Application with the fields the helper reads."""
    return SimpleNamespace(status=status, submitted_at=submitted_at, decision_date=decision_date)


@pytest.fixture
def service():
    return ScholarshipAnalyticsService(db=None)  # type: ignore[arg-type]


def test_empty_list_returns_zero_values(service):
    """Zero applications → all-zero result, NO division-by-zero crash."""
    result = service._calculate_overview_metrics([])
    assert result["total_applications"] == 0
    assert result["approval_rate"] == 0
    assert result["rejection_rate"] == 0
    assert result["pending_rate"] == 0
    assert result["average_processing_time"] == 0


def test_status_counts_split_correctly(service):
    apps = [
        _app(status=ApplicationStatus.approved),
        _app(status=ApplicationStatus.approved),
        _app(status=ApplicationStatus.rejected),
        _app(status=ApplicationStatus.submitted),
        _app(status=ApplicationStatus.under_review),
        _app(status=ApplicationStatus.draft),  # Not approved/rejected/pending.
    ]
    result = service._calculate_overview_metrics(apps)
    assert result["total_applications"] == 6
    assert result["approved_applications"] == 2
    assert result["rejected_applications"] == 1
    # Pending = submitted + under_review = 2.
    assert result["pending_applications"] == 2


def test_approval_rate_is_percentage_of_total(service):
    """approval_rate = approved / total * 100."""
    apps = [_app(status=ApplicationStatus.approved)] * 3 + [_app(status=ApplicationStatus.rejected)]
    result = service._calculate_overview_metrics(apps)
    # 3 approved out of 4 = 75%.
    assert result["approval_rate"] == 75.0


def test_average_processing_time_computed_from_dates(service):
    """Average days from submitted_at to decision_date."""
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    apps = [
        _app(
            status=ApplicationStatus.approved,
            submitted_at=base,
            decision_date=base + timedelta(days=10),
        ),
        _app(
            status=ApplicationStatus.approved,
            submitted_at=base,
            decision_date=base + timedelta(days=20),
        ),
    ]
    result = service._calculate_overview_metrics(apps)
    # (10 + 20) / 2 = 15.0.
    assert result["average_processing_time_days"] == 15.0
    assert result["processing_time_samples"] == 2


def test_negative_processing_time_excluded(service):
    """A decision_date BEFORE submitted_at means corrupt data — must
    not pollute the average (the >=0 guard)."""
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    apps = [
        _app(
            status=ApplicationStatus.approved,
            submitted_at=base,
            decision_date=base + timedelta(days=10),
        ),
        # Bad data: decision before submission.
        _app(
            status=ApplicationStatus.approved,
            submitted_at=base + timedelta(days=5),
            decision_date=base,
        ),
    ]
    result = service._calculate_overview_metrics(apps)
    # Only the valid sample counts. Average = 10.0 (NOT (10 + (-5)) / 2 = 2.5).
    assert result["average_processing_time_days"] == 10.0
    assert result["processing_time_samples"] == 1


def test_missing_dates_skipped_from_processing_time(service):
    """Applications without both timestamps are skipped from the average."""
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    apps = [
        _app(
            status=ApplicationStatus.approved,
            submitted_at=base,
            decision_date=base + timedelta(days=8),
        ),
        # No decision date.
        _app(status=ApplicationStatus.approved, submitted_at=base, decision_date=None),
        # No submission date.
        _app(status=ApplicationStatus.approved, submitted_at=None, decision_date=base),
    ]
    result = service._calculate_overview_metrics(apps)
    # Only the first sample counts.
    assert result["average_processing_time_days"] == 8.0
    assert result["processing_time_samples"] == 1


def test_pending_includes_submitted_and_under_review(service):
    """The pending bucket is submitted ∪ under_review (NOT draft, NOT approved/rejected)."""
    apps = [
        _app(status=ApplicationStatus.submitted),
        _app(status=ApplicationStatus.submitted),
        _app(status=ApplicationStatus.under_review),
        _app(status=ApplicationStatus.draft),  # NOT pending.
        _app(status=ApplicationStatus.approved),  # NOT pending.
    ]
    result = service._calculate_overview_metrics(apps)
    assert result["pending_applications"] == 3
    # 3 pending out of 5 = 60%.
    assert result["pending_rate"] == 60.0
