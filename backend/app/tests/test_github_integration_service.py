from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.github_integration_service import GitHubIntegrationService


class _FakeScalarResult:
    """Minimal async result wrapper to mimic SQLAlchemy scalar results."""

    def __init__(self, items=None):
        self._items = list(items or [])

    def scalar_one_or_none(self):  # pragma: no cover - convenience for completeness
        return self._items[0] if self._items else None

    class _Scalars:
        def __init__(self, items):
            self._items = list(items)

        def all(self):
            return list(self._items)

    def scalars(self):
        return self._Scalars(self._items)


@pytest.mark.parametrize(
    "success_rate, semester, expected_label",
    [
        (92.0, "Fall", "high-success-rate"),
        (75.0, None, "moderate-success-rate"),
        (45.0, "Spring", "low-success-rate"),
    ],
)
def test_generate_issue_labels(success_rate, semester, expected_label):
    db = AsyncMock()
    service = GitHubIntegrationService(db)

    distribution = SimpleNamespace(
        academic_year="2024",
        semester=semester,
        success_rate=success_rate,
    )

    labels = service._generate_issue_labels(distribution)

    assert "scholarship-distribution" in labels
    assert f"AY{distribution.academic_year}" in labels
    assert expected_label in labels
    if semester:
        assert f"semester-{semester.lower()}" in labels
    else:
        assert all(not label.startswith("semester-") for label in labels)


@pytest.mark.asyncio
async def test_generate_issue_body_includes_summary_and_ranking(monkeypatch):
    db = AsyncMock()

    service = GitHubIntegrationService(db)

    distribution = SimpleNamespace(
        academic_year="2024",
        semester="Fall",
        executed_at=datetime(2024, 10, 15, 9, 30, tzinfo=timezone.utc),
        total_applications=20,
        total_quota=12,
        total_allocated=11,
        success_rate=83.3,
        algorithm_version="v2",
        distribution_summary={
            "nstc": {
                "total_applications": 10,
                "quota": 8,
                "allocated": 7,
                "rejected": 3,
            }
        },
        exceptions=["Capacity adjustment applied"],
        scoring_weights={"gpa": 0.4},
        distribution_rules={"min_gpa": 3.0},
        id=42,
    )

    ranking = SimpleNamespace(id=1, ranking_name="NSTC Ranking", sub_type_code="NSTC")

    application = SimpleNamespace(student_data={"std_cname": "Alice", "std_stdcode": "S123"})
    ranking_item = SimpleNamespace(
        rank_position=1,
        application=application,
        total_score=95.0,
        is_allocated=True,
        college_review=None,
    )

    db.execute = AsyncMock(return_value=_FakeScalarResult([ranking_item]))

    body = await service._generate_issue_body(distribution, ranking)

    assert "# Scholarship Distribution Report" in body
    assert "**Academic Year:** 2024" in body
    assert "| nstc | 10 | 8 | 7 | 3 | 87.5% |" in body
    assert "| 1 | Alice | S123 | 95.00 | ✅ | Allocated |" in body
    assert "- Capacity adjustment applied" in body
    assert "- gpa: 0.4" in body
    assert "- min_gpa: 3.0" in body


@pytest.mark.asyncio
async def test_create_distribution_report_issue_updates_distribution(monkeypatch):
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_FakeScalarResult())

    service = GitHubIntegrationService(db)

    distribution = SimpleNamespace(
        academic_year="2024",
        semester="Fall",
        executed_at=datetime(2024, 9, 1, 12, 0, tzinfo=timezone.utc),
        total_applications=10,
        total_quota=5,
        total_allocated=5,
        success_rate=95.0,
        algorithm_version="v1",
        distribution_summary={},
        exceptions=[],
        scoring_weights={},
        distribution_rules={},
        id=99,
        github_issue_number=None,
        github_issue_url=None,
    )

    body_mock = AsyncMock(return_value="body text")
    monkeypatch.setattr(service, "_generate_issue_body", body_mock)
    monkeypatch.setattr(service, "_generate_issue_labels", lambda *_: ["label"])

    numbers = iter([111, 222, 333])
    monkeypatch.setattr(
        GitHubIntegrationService,
        "_generate_issue_number",
        lambda self: next(numbers),
    )

    issue = await service.create_distribution_report_issue(distribution)

    assert issue["number"] == 111
    assert issue["url"].endswith("/222")
    assert issue["html_url"].endswith("/333")
    assert issue["labels"] == ["label"]
    assert issue["body"] == "body text"
    assert issue["title"] == "Scholarship Distribution Report - AY2024 - Fall"

    assert distribution.github_issue_number == 111
    assert distribution.github_issue_url.endswith("/333")

    body_mock.assert_awaited_once_with(distribution, None)
    db.commit.assert_awaited_once()
