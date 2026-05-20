"""Service: assemble admin student scholarship history (academic + payments)."""

from decimal import Decimal
from typing import Any, Dict, List, Optional

from app.schemas.student_scholarship_history import (
    AcademicBasicInfo,
    AcademicInfo,
    HistorySummary,
    PaymentRecord,
)


class StudentScholarshipHistoryService:
    """Orchestrates SIS lookup and locked-roster payment retrieval."""

    _BASIC_INFO_FIELDS = {
        "std_cname",
        "std_ename",
        "std_degree",
        "std_studingstatus",
        "std_aca_cname",
        "std_depname",
        "std_depno",
        "com_email",
    }

    def _build_academic_info(
        self,
        sis_data: Optional[Dict[str, Any]],
        error_message: Optional[str],
    ) -> AcademicInfo:
        if not sis_data:
            return AcademicInfo(available=False, error=error_message, basic_info=None)
        subset = {k: sis_data.get(k) for k in self._BASIC_INFO_FIELDS}
        return AcademicInfo(
            available=True,
            error=None,
            basic_info=AcademicBasicInfo(**subset),
        )

    def _build_summary(
        self,
        records: List[PaymentRecord],
        snapshot_name: Optional[str],
    ) -> HistorySummary:
        total_amount = sum((r.scholarship_amount for r in records), Decimal("0"))
        type_count = len({r.scholarship_name for r in records})
        return HistorySummary(
            total_records=len(records),
            total_amount=total_amount,
            scholarship_type_count=type_count,
            snapshot_name=snapshot_name,
        )
