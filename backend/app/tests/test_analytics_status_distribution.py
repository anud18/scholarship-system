"""
Tests for `ScholarshipAnalyticsService._analyze_application_status` and
`_analyze_status_transitions`.

Wave 6l covered `_calculate_overview_metrics`. This wave covers
the status-distribution analytics:

  - **_analyze_application_status**: returns dict with
    `status_distribution` (only non-zero statuses included),
    `status_flow_analysis` (sub-dict from _analyze_status_transitions),
    `completion_rate` (% of approved+rejected over total).
  - **_analyze_status_transitions**: currently a stub returning a
    fixed dict with `note` + `common_paths` array.

12 cases.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.enums import ApplicationStatus
from app.services.analytics_service import ScholarshipAnalyticsService


@pytest.fixture
def service():
    return ScholarshipAnalyticsService(db=MagicMock())


def _app(status):
    return SimpleNamespace(status=status)


# ─── _analyze_application_status ────────────────────────────────────


def test_status_empty_list_completion_rate_is_zero(service):
    # Pin: empty input → no divide-by-zero (handled by `if
    # applications else 0`).
    out = service._analyze_application_status([])
    assert out["status_distribution"] == {}
    assert out["completion_rate"] == 0


def test_status_only_nonzero_statuses_appear_in_distribution(service):
    # Pin: zero-count statuses are filtered out. The dashboard
    # only renders statuses that have data.
    apps = [_app(ApplicationStatus.approved), _app(ApplicationStatus.approved)]
    out = service._analyze_application_status(apps)
    assert "approved" in out["status_distribution"]
    assert "draft" not in out["status_distribution"]
    assert "rejected" not in out["status_distribution"]


def test_status_distribution_includes_count_and_percentage(service):
    # Pin: each status entry has both `count` and `percentage` keys.
    apps = [_app(ApplicationStatus.approved), _app(ApplicationStatus.rejected)]
    out = service._analyze_application_status(apps)
    assert out["status_distribution"]["approved"] == {"count": 1, "percentage": 50.0}
    assert out["status_distribution"]["rejected"] == {"count": 1, "percentage": 50.0}


def test_status_completion_rate_only_counts_terminal_statuses(service):
    # Pin: only approved+rejected count toward "completed". Under-
    # review / draft / submitted are pending.
    apps = [
        _app(ApplicationStatus.approved),
        _app(ApplicationStatus.rejected),
        _app(ApplicationStatus.under_review),
        _app(ApplicationStatus.draft),
    ]
    out = service._analyze_application_status(apps)
    assert out["completion_rate"] == 50.0  # 2 / 4 = 50%


def test_status_completion_rate_100_when_all_terminal(service):
    apps = [_app(ApplicationStatus.approved), _app(ApplicationStatus.rejected)]
    out = service._analyze_application_status(apps)
    assert out["completion_rate"] == 100.0


def test_status_completion_rate_0_when_no_terminal(service):
    apps = [_app(ApplicationStatus.draft), _app(ApplicationStatus.submitted)]
    out = service._analyze_application_status(apps)
    assert out["completion_rate"] == 0.0


def test_status_includes_status_flow_analysis_subkey(service):
    # Pin: the result includes the nested status_flow_analysis dict.
    # Drift in the key name breaks the dashboard.
    apps = [_app(ApplicationStatus.draft)]
    out = service._analyze_application_status(apps)
    assert "status_flow_analysis" in out


def test_status_distribution_keys_are_enum_values_not_names(service):
    # Pin: keys are .value strings (lowercase) not enum names. Per
    # CLAUDE.md §4, the wire shape uses lowercase enum values.
    apps = [_app(ApplicationStatus.under_review)]
    out = service._analyze_application_status(apps)
    assert "under_review" in out["status_distribution"]
    assert "UNDER_REVIEW" not in out["status_distribution"]


# ─── _analyze_status_transitions ────────────────────────────────────


def test_status_transitions_returns_placeholder_dict(service):
    # Pin: stub returns a dict with `note` + `common_paths` keys.
    # Pin so when real transition analysis is implemented (per the
    # source TODO "would require status change audit trail"), the
    # test breaks and forces explicit review.
    out = service._analyze_status_transitions([])
    assert "note" in out
    assert "common_paths" in out


def test_status_transitions_common_paths_documents_3_canonical_flows(service):
    # Pin: 3 documented flows. Drift in this docstring drift would
    # mislead operators reading the analytics endpoint output.
    out = service._analyze_status_transitions([])
    paths = out["common_paths"]
    assert len(paths) == 3
    assert any("APPROVED" in p for p in paths)
    assert any("REJECTED" in p for p in paths)


def test_status_transitions_ignores_input_applications(service):
    # Pin: stub doesn't read the applications list — output identical
    # regardless of input. Pin so a partial implementation that
    # accidentally starts reading the input doesn't break the stub
    # contract silently.
    out1 = service._analyze_status_transitions([])
    out2 = service._analyze_status_transitions([_app(ApplicationStatus.draft)] * 100)
    assert out1 == out2


def test_status_transitions_returns_new_dict_each_call(service):
    # Pin: fresh dict per call (mutable-default safety).
    out1 = service._analyze_status_transitions([])
    out2 = service._analyze_status_transitions([])
    assert out1 is not out2
