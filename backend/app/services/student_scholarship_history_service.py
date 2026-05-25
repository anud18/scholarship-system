"""Service: assemble admin student scholarship history (academic + payments)."""

import asyncio
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ScholarshipException
from app.models.payment_roster import PaymentRoster, PaymentRosterItem, RosterStatus
from app.schemas.student_scholarship_history import (
    AcademicBasicInfo,
    AcademicInfo,
    HistorySummary,
    PaymentRecord,
    StudentScholarshipHistoryData,
)
from app.services.student_service import StudentService

logger = logging.getLogger(__name__)


class StudentScholarshipHistoryService:
    """Orchestrates SIS lookup and paid-roster payment retrieval.

    A roster counts as paid out once it has reached either COMPLETED or LOCKED
    status (the Excel file has been produced; the distribution is final). Earlier
    states (DRAFT/PROCESSING/FAILED) are considered in-flight and excluded.
    """

    _BASIC_INFO_FIELDS = {
        "std_cname",
        "std_ename",
        "std_degree",
        "std_studingstatus",
        "std_academyno",
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
        # SIS returns some fields as ints (e.g. std_degree=1); coerce to str so
        # the frontend's string-keyed degree/status lookups work uniformly.
        subset = {k: (None if (v := sis_data.get(k)) is None else str(v)) for k in self._BASIC_INFO_FIELDS}
        return AcademicInfo(
            available=True,
            error=None,
            basic_info=AcademicBasicInfo(**subset),
        )

    async def _fetch_paid_payments(
        self,
        db: AsyncSession,
        student_number: str,
    ) -> Tuple[List[PaymentRecord], Optional[str]]:
        """Return roster items for the student from rosters in a paid state
        (COMPLETED or LOCKED). Also returns the student_name snapshot from the
        most-recent matching item, for SIS-fallback display."""
        stmt = (
            select(PaymentRosterItem, PaymentRoster)
            .join(PaymentRoster, PaymentRosterItem.roster_id == PaymentRoster.id)
            .where(
                PaymentRosterItem.student_id_number == student_number,
                PaymentRosterItem.is_included.is_(True),
                PaymentRoster.status.in_([RosterStatus.COMPLETED, RosterStatus.LOCKED]),
            )
            .order_by(
                PaymentRoster.academic_year.desc(),
                PaymentRoster.period_label.desc(),
            )
        )
        result = await db.execute(stmt)
        rows = result.all()
        records = [
            PaymentRecord(
                roster_id=roster.id,
                roster_code=roster.roster_code,
                period_label=roster.period_label,
                academic_year=roster.academic_year,
                roster_cycle=roster.roster_cycle.value,
                scholarship_name=item.scholarship_name,
                scholarship_amount=item.scholarship_amount,
                scholarship_subtype=item.scholarship_subtype,
                allocation_year=item.allocation_year,
                locked_at=roster.locked_at,
            )
            for item, roster in rows
        ]
        snapshot_name = rows[0][0].student_name if rows else None
        return records, snapshot_name

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

    async def get_history(
        self,
        db: AsyncSession,
        student_number: str,
    ) -> StudentScholarshipHistoryData:
        """Orchestrate SIS lookup + paid-payment retrieval. Raises
        ScholarshipException(404) when both sources are empty.

        SIS and DB are queried concurrently: SIS calls can take up to
        ``student_api_timeout`` seconds, while the DB query is local — running
        them in parallel keeps the worst-case latency at max(sis, db) rather
        than sis + db."""
        sis_task = asyncio.create_task(StudentService().get_student_basic_info(student_number))
        db_task = asyncio.create_task(self._fetch_paid_payments(db, student_number))

        sis_result, db_result = await asyncio.gather(sis_task, db_task, return_exceptions=True)

        sis_error: Optional[str] = None
        sis_data: Optional[Dict[str, Any]] = None
        if isinstance(sis_result, BaseException):
            logger.warning("SIS lookup failed for student %s: %s", student_number, sis_result)
            sis_error = str(sis_result)
        else:
            sis_data = sis_result

        if isinstance(db_result, BaseException):
            # DB failures are not user-recoverable — re-raise so the global
            # handler can produce a 500 with trace_id.
            raise db_result
        records, snapshot_name = db_result

        academic_info = self._build_academic_info(sis_data, error_message=sis_error)

        if not academic_info.available and not records:
            raise ScholarshipException(
                message=f"查無此學生資料: {student_number}",
                status_code=404,
                error_code="NOT_FOUND",
            )

        summary = self._build_summary(records, snapshot_name=snapshot_name)
        return StudentScholarshipHistoryData(
            student_number=student_number,
            academic_info=academic_info,
            summary=summary,
            payment_records=records,
        )
