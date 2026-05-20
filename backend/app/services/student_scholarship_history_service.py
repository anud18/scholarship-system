"""Service: assemble admin student scholarship history (academic + payments)."""

from decimal import Decimal
from typing import List, Optional

from app.schemas.student_scholarship_history import HistorySummary, PaymentRecord


class StudentScholarshipHistoryService:
    """Orchestrates SIS lookup and locked-roster payment retrieval."""

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
