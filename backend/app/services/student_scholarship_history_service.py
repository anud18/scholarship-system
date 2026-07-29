"""Service: assemble admin student scholarship history (academic + payments)."""

import asyncio
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ScholarshipException
from app.models.application import Application
from app.models.payment_roster import PaymentRoster, PaymentRosterItem, RosterStatus
from app.models.scholarship import ScholarshipConfiguration
from app.models.user import User
from app.schemas.student_scholarship_history import (
    AcademicBasicInfo,
    AcademicInfo,
    HistorySummary,
    PaymentRecord,
    ReceivedMonthsBreakdown,
    StudentScholarshipHistoryData,
)
from app.services.received_months_import_service import get_student_imported_records
from app.services.received_months_service import months_for_cycle_value
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
        most-recent matching item, for SIS-fallback display.

        ``student_number`` is the 學號 (std_stdcode) the admin looks up by, so it
        must match PaymentRosterItem.student_number — NOT student_id_number, which
        holds the national ID (身分證字號) for the Excel payment column.

        Soft-deleted applications are excluded (issue #977 / G15): a roster
        item whose application was since soft-deleted must not surface in the
        payment history view. The outerjoin keeps legacy items whose
        application_id is NULL (imported rows) visible."""
        stmt = (
            select(PaymentRosterItem, PaymentRoster, Application, ScholarshipConfiguration)
            .join(PaymentRoster, PaymentRosterItem.roster_id == PaymentRoster.id)
            .outerjoin(Application, PaymentRosterItem.application_id == Application.id)
            .outerjoin(
                ScholarshipConfiguration,
                PaymentRoster.scholarship_configuration_id == ScholarshipConfiguration.id,
            )
            .where(
                PaymentRosterItem.student_number == student_number,
                PaymentRosterItem.is_included.is_(True),
                PaymentRoster.status.in_([RosterStatus.COMPLETED, RosterStatus.LOCKED]),
                or_(Application.id.is_(None), Application.deleted_at.is_(None)),
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
                # G25 (#987): post-payment revocation context from the
                # (outer-joined) application — None for legacy items.
                quota_allocation_status=app.quota_allocation_status if app else None,
                revoked_at=app.revoked_at if app else None,
                revoke_reason=app.revoke_reason if app else None,
                suspended_at=app.suspended_at if app else None,
                suspend_reason=app.suspend_reason if app else None,
                scholarship_type_id=config.scholarship_type_id if config else None,
            )
            for item, roster, app, config in rows
        ]
        snapshot_name = rows[0][0].student_name if rows else None
        return records, snapshot_name

    def _build_received_months(
        self,
        records: List[PaymentRecord],
        imported_records: List[Dict[str, Any]],
    ) -> List[ReceivedMonthsBreakdown]:
        """已領月份數 per scholarship type: 匯入 baseline + 系統 months.

        The system half is summed over the student's whole payment history —
        this page has no academic-year context, unlike the 手動分發 panel. The
        two halves are added, never substituted; see
        docs/adr/0001-received-months-are-additive.md.

        A scholarship type appears if it has an imported record, system
        payments, or both.
        """
        system_months: Dict[Optional[int], int] = {}
        names: Dict[Optional[int], str] = {}
        for record in records:
            key = record.scholarship_type_id
            system_months[key] = system_months.get(key, 0) + months_for_cycle_value(record.roster_cycle)
            names.setdefault(key, record.scholarship_name)

        breakdowns: List[ReceivedMonthsBreakdown] = []
        seen_types: set = set()

        for imported in imported_records:
            type_id = imported["scholarship_type_id"]
            seen_types.add(type_id)
            system = system_months.get(type_id, 0)
            breakdowns.append(
                ReceivedMonthsBreakdown(
                    scholarship_type_id=type_id,
                    scholarship_name=imported["scholarship_name"],
                    total_months=imported["months"] + system,
                    imported_months=imported["months"],
                    system_months=system,
                    award_start_month=imported["award_start_month"],
                    award_current_month=imported["award_current_month"],
                    raw_row=imported["raw_row"],
                    file_name=imported["file_name"],
                    imported_at=imported["imported_at"],
                )
            )

        for type_id, months in system_months.items():
            if type_id in seen_types or months <= 0:
                continue
            breakdowns.append(
                ReceivedMonthsBreakdown(
                    scholarship_type_id=type_id,
                    scholarship_name=names.get(type_id) or "未知獎學金",
                    total_months=months,
                    imported_months=0,
                    system_months=months,
                )
            )

        breakdowns.sort(key=lambda b: (-b.total_months, b.scholarship_name))
        return breakdowns

    def _build_summary(
        self,
        records: List[PaymentRecord],
        snapshot_name: Optional[str],
        received_months: List[ReceivedMonthsBreakdown],
    ) -> HistorySummary:
        total_amount = sum((r.scholarship_amount for r in records), Decimal("0"))
        type_count = len({r.scholarship_name for r in records})
        return HistorySummary(
            total_records=len(records),
            total_amount=total_amount,
            scholarship_type_count=type_count,
            snapshot_name=snapshot_name,
            # 總領月份數 across every scholarship type. Per-type caps (the
            # 36-month PhD limit) are checked against the individual
            # breakdowns, never against this sum.
            total_received_months=sum(b.total_months for b in received_months),
        )

    async def fetch_sis_lookups(
        self,
        student_numbers: List[str],
        concurrency: int = 10,
    ) -> Dict[str, Tuple[Optional[Dict[str, Any]], Optional[str]]]:
        """Concurrent SIS lookups for a batch, capped by ``concurrency``.

        Returns {student_number: (sis_data, error_message)}. Failures never
        raise — a degraded SIS costs at most one timeout window per wave
        instead of one per student, and each student degrades independently
        to the SIS-unavailable display state.
        """
        semaphore = asyncio.Semaphore(concurrency)
        service = StudentService()

        async def lookup(number: str) -> Tuple[str, Tuple[Optional[Dict[str, Any]], Optional[str]]]:
            async with semaphore:
                try:
                    return number, (await service.get_student_basic_info(number), None)
                except Exception as exc:
                    logger.warning("SIS lookup failed for student %s", number, exc_info=True)
                    return number, (None, str(exc))

        pairs = await asyncio.gather(*(lookup(number) for number in student_numbers))
        return dict(pairs)

    async def get_total_received_months(self, db: AsyncSession, student_number: str) -> int:
        """總領月份數 (匯入 + 系統) from DB records only — no SIS round trip.

        An unknown student simply has no records and totals 0; there is no
        404 concept here (student self-service treats empty history as a
        valid zero-month state)."""
        records, _ = await self._fetch_paid_payments(db, student_number)
        imported_records = await get_student_imported_records(db, student_number)
        breakdowns = self._build_received_months(records, imported_records)
        return sum(b.total_months for b in breakdowns)

    async def get_snapshot_academy_codes(self, db: AsyncSession, student_number: str) -> set:
        """College codes (std_academyno) frozen in the student's application
        snapshots, for college-scope checks that must not depend on live SIS.

        Applications are matched through User.nycu_id (== 學號 for student
        accounts, including batch-imported ones). JSON is parsed in Python,
        not SQL — SQLite (tests) lacks json_extract_path_text."""
        stmt = (
            select(Application.student_data)
            .join(User, Application.user_id == User.id)
            .where(User.nycu_id == student_number, Application.deleted_at.is_(None))
        )
        result = await db.execute(stmt)
        codes = set()
        for student_data in result.scalars():
            if not isinstance(student_data, dict):
                continue
            code = student_data.get("std_academyno")
            if code is not None and str(code).strip():
                codes.add(str(code).strip())
        return codes

    async def get_history(
        self,
        db: AsyncSession,
        student_number: str,
        prefetched_sis: Optional[Tuple[Optional[Dict[str, Any]], Optional[str]]] = None,
    ) -> StudentScholarshipHistoryData:
        """Orchestrate SIS lookup + paid-payment retrieval. Raises
        ScholarshipException(404) when both sources are empty.

        Without ``prefetched_sis``, SIS and DB are queried concurrently: SIS
        calls can take up to ``student_api_timeout`` seconds, while the DB
        query is local — running them in parallel keeps the worst-case latency
        at max(sis, db) rather than sis + db. Batch callers pass
        ``prefetched_sis`` (from :meth:`fetch_sis_lookups`) so N students cost
        one concurrent SIS wave, not N serialized calls."""
        sis_error: Optional[str] = None
        sis_data: Optional[Dict[str, Any]] = None
        if prefetched_sis is None:
            sis_task = asyncio.create_task(StudentService().get_student_basic_info(student_number))
            db_task = asyncio.create_task(self._fetch_paid_payments(db, student_number))

            sis_result, db_result = await asyncio.gather(sis_task, db_task, return_exceptions=True)

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
        else:
            sis_data, sis_error = prefetched_sis
            records, snapshot_name = await self._fetch_paid_payments(db, student_number)

        # Sequential, not gathered with the above: both use `db`, and an
        # AsyncSession does not support concurrent statements on one connection.
        imported_records = await get_student_imported_records(db, student_number)

        academic_info = self._build_academic_info(sis_data, error_message=sis_error)

        if not academic_info.available and not records and not imported_records:
            raise ScholarshipException(
                message=f"查無此學生資料: {student_number}",
                status_code=404,
                error_code="NOT_FOUND",
            )

        received_months = self._build_received_months(records, imported_records)
        summary = self._build_summary(
            records,
            snapshot_name=snapshot_name,
            received_months=received_months,
        )
        return StudentScholarshipHistoryData(
            student_number=student_number,
            academic_info=academic_info,
            summary=summary,
            payment_records=records,
            received_months=received_months,
        )
