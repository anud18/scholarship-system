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


from app.schemas.student_scholarship_history import AcademicInfo


class TestBuildAcademicInfo:
    def test_none_sis_data_marks_unavailable(self):
        svc = StudentScholarshipHistoryService()
        result = svc._build_academic_info(None, error_message="SIS timeout")
        assert isinstance(result, AcademicInfo)
        assert result.available is False
        assert result.error == "SIS timeout"
        assert result.basic_info is None

    def test_valid_sis_data_extracts_basic_info(self):
        svc = StudentScholarshipHistoryService()
        sis = {
            "std_cname": "王小明",
            "std_ename": "Wang",
            "std_degree": "1",
            "std_studingstatus": "在學",
            "std_aca_cname": "電機學院",
            "std_depname": "電子博士班",
            "std_depno": "4460",
            "com_email": "wang@nycu.edu.tw",
            "irrelevant_field": "ignored",
        }
        result = svc._build_academic_info(sis, error_message=None)
        assert result.available is True
        assert result.error is None
        assert result.basic_info is not None
        assert result.basic_info.std_cname == "王小明"
        assert result.basic_info.std_degree == "1"
        assert result.basic_info.com_email == "wang@nycu.edu.tw"
