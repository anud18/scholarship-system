"""
Service: 匯入已領月份數 (import 國科會's received-months report).

Two phases, so a malformed file can never overwrite live values:

1. ``preview`` parses the workbook and stores the result on a ``pending``
   ReceivedMonthImport. Nothing reaches the ledger.
2. ``confirm`` upserts every valid row into student_received_month_records and
   flips the run to ``completed``.

Rows are keyed by 學號 alone — a student 國科會 lists but this system has never
seen is imported anyway, and the record simply waits for them to apply.
"""

import logging
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ScholarshipException
from app.models.received_months import (
    IMPORT_STATUS_CANCELLED,
    IMPORT_STATUS_COMPLETED,
    IMPORT_STATUS_PENDING,
    ReceivedMonthImport,
    StudentReceivedMonthRecord,
)
from app.models.scholarship import ScholarshipType
from app.services.received_months_parser import (
    ParsedRow,
    format_roc_month,
    parse_received_months_workbook,
)

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
PARSED_DATA_TTL_DAYS = 7


class ReceivedMonthsImportService:
    """Preview/confirm lifecycle for 已領月份數 imports."""

    async def preview(
        self,
        db: AsyncSession,
        *,
        content: bytes,
        file_name: str,
        scholarship_type_id: int,
        importer_id: int,
    ) -> ReceivedMonthImport:
        """Parse the workbook and stage the result. Writes nothing to the ledger."""
        if len(content) > MAX_UPLOAD_BYTES:
            raise ScholarshipException(
                message="檔案過大 (上限 5MB)",
                status_code=413,
                error_code="FILE_TOO_LARGE",
            )

        await self._require_scholarship_type(db, scholarship_type_id)
        parse_result = self._parse(content)

        staged_rows = [self._row_to_dict(row) for row in parse_result.rows]
        import_run = ReceivedMonthImport(
            importer_id=importer_id,
            scholarship_type_id=scholarship_type_id,
            file_name=file_name,
            status=IMPORT_STATUS_PENDING,
            parsed_data={"headers": parse_result.headers, "rows": staged_rows},
            data_expires_at=datetime.now(timezone.utc) + timedelta(days=PARSED_DATA_TTL_DAYS),
            total_rows=len(parse_result.rows),
            valid_rows=len(parse_result.valid_rows),
            warning_rows=parse_result.warning_count,
            error_rows=parse_result.error_count,
        )
        db.add(import_run)
        await db.commit()
        await db.refresh(import_run)
        return import_run

    async def confirm(self, db: AsyncSession, import_id: int, importer_id: int) -> Dict[str, Any]:
        """Upsert every valid staged row into the ledger."""
        import_run = await self._require_pending_run(db, import_id)

        staged = (import_run.parsed_data or {}).get("rows", [])
        valid_rows = [row for row in staged if not row.get("error")]
        if not valid_rows:
            raise ScholarshipException(
                message="沒有可匯入的有效資料列",
                status_code=400,
                error_code="NO_VALID_ROWS",
            )

        existing = await self._existing_records(
            db,
            scholarship_type_id=import_run.scholarship_type_id,
            student_numbers=[row["student_number"] for row in valid_rows],
        )

        created = 0
        updated = 0
        for row in valid_rows:
            record = existing.get(row["student_number"])
            if record is None:
                db.add(
                    StudentReceivedMonthRecord(
                        student_number=row["student_number"],
                        scholarship_type_id=import_run.scholarship_type_id,
                        months=row["months"],
                        award_start_month=row.get("award_start_month"),
                        award_current_month=row.get("award_current_month"),
                        raw_row=row.get("raw_row"),
                        import_id=import_run.id,
                    )
                )
                created += 1
            else:
                record.months = row["months"]
                record.award_start_month = row.get("award_start_month")
                record.award_current_month = row.get("award_current_month")
                record.raw_row = row.get("raw_row")
                record.import_id = import_run.id
                updated += 1

        import_run.status = IMPORT_STATUS_COMPLETED
        import_run.confirmed_at = datetime.now(timezone.utc)
        # The staged copy has served its purpose; the ledger now holds each row.
        import_run.parsed_data = None
        import_run.data_expires_at = None

        await db.commit()
        logger.info(
            "Received-months import %s confirmed by user %s: %s created, %s updated",
            import_run.id,
            importer_id,
            created,
            updated,
        )
        return {"import_id": import_run.id, "created": created, "updated": updated}

    async def cancel(self, db: AsyncSession, import_id: int) -> None:
        """Discard a staged run and its parsed rows."""
        import_run = await self._require_pending_run(db, import_id)
        import_run.status = IMPORT_STATUS_CANCELLED
        import_run.parsed_data = None
        import_run.data_expires_at = None
        await db.commit()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _parse(content: bytes):
        import openpyxl

        try:
            workbook = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)
        except Exception as exc:
            raise ScholarshipException(
                message=f"無法讀取 Excel 檔案，請確認格式正確 ({type(exc).__name__})",
                status_code=400,
                error_code="INVALID_FILE",
            ) from exc

        try:
            worksheet = workbook.active
            rows = list(worksheet.iter_rows(values_only=True))
        finally:
            workbook.close()

        try:
            return parse_received_months_workbook(rows)
        except ValueError as exc:
            # File-level problem (no header row, no data rows) — actionable by
            # the admin, so surface the parser's own message.
            raise ScholarshipException(
                message=str(exc),
                status_code=400,
                error_code="INVALID_FILE",
            ) from exc

    @staticmethod
    def _row_to_dict(row: ParsedRow) -> Dict[str, Any]:
        return {
            "row_number": row.row_number,
            "student_number": row.student_number,
            "months": row.months,
            "award_start_month": row.award_start_month,
            "award_current_month": row.award_current_month,
            "award_start_label": format_roc_month(row.award_start_month),
            "award_current_label": format_roc_month(row.award_current_month),
            "raw_row": row.raw_row,
            "warning": row.warning,
            "error": row.error,
        }

    @staticmethod
    async def _require_scholarship_type(db: AsyncSession, scholarship_type_id: int) -> ScholarshipType:
        result = await db.execute(select(ScholarshipType).where(ScholarshipType.id == scholarship_type_id))
        scholarship_type = result.scalar_one_or_none()
        if scholarship_type is None:
            raise ScholarshipException(
                message=f"找不到獎學金類型: {scholarship_type_id}",
                status_code=404,
                error_code="NOT_FOUND",
            )
        return scholarship_type

    @staticmethod
    async def _require_pending_run(db: AsyncSession, import_id: int) -> ReceivedMonthImport:
        result = await db.execute(select(ReceivedMonthImport).where(ReceivedMonthImport.id == import_id))
        import_run = result.scalar_one_or_none()
        if import_run is None:
            raise ScholarshipException(
                message=f"找不到匯入紀錄: {import_id}",
                status_code=404,
                error_code="NOT_FOUND",
            )
        if import_run.status != IMPORT_STATUS_PENDING:
            raise ScholarshipException(
                message=f"匯入紀錄狀態為 {import_run.status}，無法再次處理",
                status_code=400,
                error_code="INVALID_STATE",
            )
        return import_run

    @staticmethod
    async def _existing_records(
        db: AsyncSession,
        *,
        scholarship_type_id: int,
        student_numbers: List[str],
    ) -> Dict[str, StudentReceivedMonthRecord]:
        if not student_numbers:
            return {}
        result = await db.execute(
            select(StudentReceivedMonthRecord).where(
                StudentReceivedMonthRecord.scholarship_type_id == scholarship_type_id,
                StudentReceivedMonthRecord.student_number.in_(student_numbers),
            )
        )
        return {record.student_number: record for record in result.scalars().all()}


async def get_student_imported_records(db: AsyncSession, student_number: str) -> List[Dict[str, Any]]:
    """Every imported ledger row for a student, newest scholarship type first.

    Used by 學生領獎紀錄查詢 to render the「已領月份數」card and its
    「檔案明細」expander.
    """
    result = await db.execute(
        select(StudentReceivedMonthRecord, ScholarshipType, ReceivedMonthImport)
        .join(ScholarshipType, ScholarshipType.id == StudentReceivedMonthRecord.scholarship_type_id)
        .outerjoin(ReceivedMonthImport, ReceivedMonthImport.id == StudentReceivedMonthRecord.import_id)
        .where(StudentReceivedMonthRecord.student_number == student_number)
        .order_by(StudentReceivedMonthRecord.scholarship_type_id)
    )

    records: List[Dict[str, Any]] = []
    for record, scholarship_type, import_run in result.all():
        records.append(
            {
                "scholarship_type_id": record.scholarship_type_id,
                "scholarship_name": scholarship_type.name,
                "months": record.months,
                "award_start_month": format_roc_month(record.award_start_month),
                "award_current_month": format_roc_month(record.award_current_month),
                "raw_row": record.raw_row or {},
                "file_name": import_run.file_name if import_run else None,
                "imported_at": _isoformat(import_run.confirmed_at if import_run else None),
                "updated_at": _isoformat(record.updated_at),
            }
        )
    return records


def _isoformat(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None
