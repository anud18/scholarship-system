"""
Counter-contract tests for the additional business-metric instrumentation
added in the scholarship_reviews_total / email_sent_total wave (#159).

These mirror test_application_metrics_instrumentation.py — they verify
that the counter symbols imported from app.core.metrics are real
Counter instances, that .inc() advances the value, and that the label
dimensions segregate series. The end-to-end paths that drive the
counters live in application_service.py / email_service.py and are
covered by existing service-level suites.
"""

from prometheus_client import REGISTRY

from app.core.metrics import email_sent_total, scholarship_reviews_total


def _sample(metric_name: str, **labels: str) -> float:
    value = REGISTRY.get_sample_value(metric_name, labels=labels)
    return value or 0.0


class TestScholarshipReviewsCounter:
    def test_increment_for_professor_approve(self):
        before = _sample(
            "scholarship_reviews_total_total",
            reviewer_type="professor",
            action="approve",
        )
        scholarship_reviews_total.labels(reviewer_type="professor", action="approve").inc()
        after = _sample(
            "scholarship_reviews_total_total",
            reviewer_type="professor",
            action="approve",
        )
        assert after - before == 1.0

    def test_increment_for_professor_reject_is_independent(self):
        before_approve = _sample(
            "scholarship_reviews_total_total",
            reviewer_type="professor",
            action="approve",
        )
        before_reject = _sample(
            "scholarship_reviews_total_total",
            reviewer_type="professor",
            action="reject",
        )
        scholarship_reviews_total.labels(reviewer_type="professor", action="reject").inc()
        assert (
            _sample(
                "scholarship_reviews_total_total",
                reviewer_type="professor",
                action="approve",
            )
            - before_approve
            == 0.0
        )
        assert (
            _sample(
                "scholarship_reviews_total_total",
                reviewer_type="professor",
                action="reject",
            )
            - before_reject
            == 1.0
        )

    def test_increment_for_college_reviewer_type(self):
        before = _sample(
            "scholarship_reviews_total_total",
            reviewer_type="college",
            action="approve",
        )
        scholarship_reviews_total.labels(reviewer_type="college", action="approve").inc()
        after = _sample(
            "scholarship_reviews_total_total",
            reviewer_type="college",
            action="approve",
        )
        assert after - before == 1.0


class TestEmailSentCounter:
    def test_increment_for_success_path(self):
        before = _sample(
            "email_sent_total_total",
            category="notification",
            status="sent",
        )
        email_sent_total.labels(category="notification", status="sent").inc()
        after = _sample(
            "email_sent_total_total",
            category="notification",
            status="sent",
        )
        assert after - before == 1.0

    def test_increment_for_failed_path(self):
        before = _sample(
            "email_sent_total_total",
            category="notification",
            status="failed",
        )
        email_sent_total.labels(category="notification", status="failed").inc()
        after = _sample(
            "email_sent_total_total",
            category="notification",
            status="failed",
        )
        assert after - before == 1.0

    def test_uncategorized_label_used_when_no_category(self):
        # email_service falls back to "uncategorized" when metadata
        # doesn't carry an email_category — ensure the literal label
        # works on the counter so the dashboard isn't surprised by a
        # validation error at runtime.
        before = _sample(
            "email_sent_total_total",
            category="uncategorized",
            status="sent",
        )
        email_sent_total.labels(category="uncategorized", status="sent").inc()
        after = _sample(
            "email_sent_total_total",
            category="uncategorized",
            status="sent",
        )
        assert after - before == 1.0
