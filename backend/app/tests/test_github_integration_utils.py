from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.college_review import QuotaDistribution
from app.services.github_integration_service import (
    GitHubIntegrationService,
    format_distribution_for_export,
    generate_distribution_csv_content,
)


def build_distribution(success_rate: float) -> QuotaDistribution:
    distribution = QuotaDistribution()
    distribution.id = 321
    distribution.distribution_name = "Test Distribution"
    distribution.academic_year = 2024
    distribution.semester = "First"
    distribution.total_applications = 100
    distribution.total_quota = 80
    distribution.total_allocated = int(success_rate)
    distribution.algorithm_version = "v1"
    distribution.distribution_summary = {
        "general": {
            "quota": 40,
            "allocated": 30,
            "total_applications": 45,
            "rejected": 15,
        }
    }
    distribution.exceptions = ["Manual adjustment applied"]
    distribution.executed_at = datetime(2024, 1, 15, tzinfo=timezone.utc)
    distribution.github_issue_number = None
    distribution.github_issue_url = None
    return distribution


def test_generate_issue_labels_reflects_success_rate_buckets():
    distribution = build_distribution(95)
    service = GitHubIntegrationService(db=AsyncMock())

    labels = service._generate_issue_labels(distribution)

    assert "high-success-rate" in labels
    assert "semester-first" in labels

    distribution.total_allocated = 75
    labels = service._generate_issue_labels(distribution)
    assert "moderate-success-rate" in labels

    distribution.total_allocated = 40
    labels = service._generate_issue_labels(distribution)
    assert "low-success-rate" in labels


def test_format_distribution_for_export_collects_all_fields():
    distribution = build_distribution(70)
    export = format_distribution_for_export(distribution)

    assert export["distribution_id"] == 321
    assert export["distribution_name"] == "Test Distribution"
    assert export["success_rate"] == pytest.approx(distribution.success_rate)
    assert export["distribution_summary"]["general"]["quota"] == 40
    assert export["exceptions"] == ["Manual adjustment applied"]


def test_generate_distribution_csv_content_sorts_and_formats_rows():
    ranking_items = [
        SimpleNamespace(
            rank_position=2,
            application=SimpleNamespace(student_data={"std_cname": "B", "std_stdcode": "B002"}),
            is_allocated=False,
            status="pending",
            allocation_reason=None,
        ),
        SimpleNamespace(
            rank_position=1,
            application=SimpleNamespace(student_data={"std_cname": "A", "std_stdcode": "A001"}),
            is_allocated=True,
            status="approved",
            allocation_reason="Top score",
        ),
    ]

    csv_content = generate_distribution_csv_content(ranking_items)
    lines = csv_content.splitlines()

    assert lines[0] == "Rank,Student Name,Student ID,Allocated,Status,Allocation Reason"
    assert lines[1].startswith("1,A,A001,Yes,approved,Top score")
    assert lines[2].startswith("2,B,B002,No,pending,N/A")
