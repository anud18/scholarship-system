"""
Pure-function tests for `GitHubIntegrationService` issue-formatting helpers.

When a scholarship distribution finishes, this service creates a GitHub
issue with a summary report. Wrong title/labels break the GitHub
workflow that the operations team uses to triage distribution
failures (queries like `is:issue label:low-success-rate` would silently
skip events).

2 helpers covered (10 cases):
- `_generate_issue_title`   : 'Scholarship Distribution Report - AY{year}[{- semester}]'
- `_generate_issue_labels`  : 3 base labels + semester + success-rate tier
"""

from types import SimpleNamespace

import pytest

from app.services.github_integration_service import GitHubIntegrationService


@pytest.fixture
def service():
    return GitHubIntegrationService(db=None)  # type: ignore[arg-type]


# ─── _generate_issue_title ───────────────────────────────────────────


def test_issue_title_no_semester(service):
    """Yearly distribution (no semester) ⇒ no semester suffix."""
    d = SimpleNamespace(academic_year=113, semester=None)
    assert service._generate_issue_title(d) == "Scholarship Distribution Report - AY113"


def test_issue_title_with_semester(service):
    """Semester distribution ⇒ ' - {semester}' suffix."""
    d = SimpleNamespace(academic_year=113, semester="first")
    assert service._generate_issue_title(d) == "Scholarship Distribution Report - AY113 - first"


def test_issue_title_empty_semester_treated_as_missing(service):
    """Empty-string semester is falsy ⇒ same as None (no suffix)."""
    d = SimpleNamespace(academic_year=114, semester="")
    assert service._generate_issue_title(d) == "Scholarship Distribution Report - AY114"


# ─── _generate_issue_labels ──────────────────────────────────────────


def test_issue_labels_base_three_always_present(service):
    """3 baseline labels always present, regardless of success rate."""
    d = SimpleNamespace(academic_year=113, semester=None, success_rate=85)
    labels = service._generate_issue_labels(d)
    assert "scholarship-distribution" in labels
    assert "AY113" in labels
    assert "automated-report" in labels


def test_issue_labels_includes_semester_when_present(service):
    """Semester appended as 'semester-{lowercased}' when set."""
    d = SimpleNamespace(academic_year=113, semester="First", success_rate=95)
    labels = service._generate_issue_labels(d)
    assert "semester-first" in labels


def test_issue_labels_no_semester_when_none(service):
    """No 'semester-*' label if the distribution is yearly."""
    d = SimpleNamespace(academic_year=113, semester=None, success_rate=95)
    labels = service._generate_issue_labels(d)
    assert not any(l.startswith("semester-") for l in labels)


def test_issue_labels_high_success_rate_above_90(service):
    """≥ 90 ⇒ 'high-success-rate' (op team filter)."""
    d = SimpleNamespace(academic_year=113, semester=None, success_rate=90)
    assert "high-success-rate" in service._generate_issue_labels(d)
    d = SimpleNamespace(academic_year=113, semester=None, success_rate=100)
    assert "high-success-rate" in service._generate_issue_labels(d)


def test_issue_labels_moderate_70_to_89(service):
    """70-89 ⇒ 'moderate-success-rate'."""
    d = SimpleNamespace(academic_year=113, semester=None, success_rate=70)
    assert "moderate-success-rate" in service._generate_issue_labels(d)
    d = SimpleNamespace(academic_year=113, semester=None, success_rate=89)
    assert "moderate-success-rate" in service._generate_issue_labels(d)


def test_issue_labels_low_below_70_triggers_alert(service):
    """< 70 ⇒ 'low-success-rate' (oncall queries this label for triage)."""
    d = SimpleNamespace(academic_year=113, semester=None, success_rate=69)
    assert "low-success-rate" in service._generate_issue_labels(d)
    d = SimpleNamespace(academic_year=113, semester=None, success_rate=0)
    assert "low-success-rate" in service._generate_issue_labels(d)


def test_issue_labels_exactly_one_success_tier_always(service):
    """Pin that exactly ONE tier label is added — preventing a future
    refactor that accidentally adds two tier labels (which would mess
    up oncall's exclusive-label queries)."""
    for rate in (0, 50, 70, 89, 90, 100):
        d = SimpleNamespace(academic_year=113, semester=None, success_rate=rate)
        labels = service._generate_issue_labels(d)
        tier_labels = [l for l in labels if l.endswith("-success-rate")]
        assert len(tier_labels) == 1, f"rate={rate} → {tier_labels}"
