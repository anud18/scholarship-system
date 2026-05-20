"""Unit tests for StudentScholarshipHistoryService helpers."""

from decimal import Decimal

from app.schemas.student_scholarship_history import PaymentRecord
from app.services.student_scholarship_history_service import (
    StudentScholarshipHistoryService,
)


def _record(name: str, amount: str, period: str = "114-10") -> PaymentRecord:
    return PaymentRecord(
        roster_id=1,
        roster_code="ROSTER-X",
        period_label=period,
        academic_year=114,
        roster_cycle="monthly",
        scholarship_name=name,
        scholarship_amount=Decimal(amount),
    )


class TestBuildSummary:
    def test_empty_records_yields_zero_summary(self):
        svc = StudentScholarshipHistoryService()
        result = svc._build_summary([], snapshot_name=None)
        assert result.total_records == 0
        assert result.total_amount == Decimal("0")
        assert result.scholarship_type_count == 0
        assert result.snapshot_name is None

    def test_counts_records_and_sums_amounts(self):
        svc = StudentScholarshipHistoryService()
        records = [_record("A", "1000"), _record("A", "2000"), _record("B", "500")]
        result = svc._build_summary(records, snapshot_name="王小明")
        assert result.total_records == 3
        assert result.total_amount == Decimal("3500")
        assert result.scholarship_type_count == 2  # A and B
        assert result.snapshot_name == "王小明"

    def test_scholarship_type_count_dedupes_by_name(self):
        svc = StudentScholarshipHistoryService()
        records = [_record("國科會", "100"), _record("國科會", "100"), _record("國科會", "100")]
        result = svc._build_summary(records, snapshot_name=None)
        assert result.scholarship_type_count == 1
