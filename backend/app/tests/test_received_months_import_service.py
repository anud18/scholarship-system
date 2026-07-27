"""
Tests for ReceivedMonthsImportService — the preview/confirm lifecycle.

Pinned behaviour:
- preview stages rows without touching the ledger
- confirm upserts: new students insert, existing (學號, type) rows update
- errored rows never reach the ledger
- a run can only be confirmed once
- students unknown to the system still import (no FK on student_number)
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.exceptions import ScholarshipException
from app.db.base_class import Base
from app.models.received_months import (
    IMPORT_STATUS_COMPLETED,
    IMPORT_STATUS_PENDING,
    ReceivedMonthImport,
    StudentReceivedMonthRecord,
)
from app.models.scholarship import ScholarshipType
from app.models.user import User
from app.services.received_months_import_service import ReceivedMonthsImportService

SCHOLARSHIP_TYPE_ID = 501
IMPORTER_ID = 601


def _build_workbook_bytes(rows):
    """Write an in-memory .xlsx shaped like 國科會's report."""
    from io import BytesIO

    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["國科會博士生獎學金-獲獎生已領月份統計表"])
    sheet.append(
        [
            "NO",
            "學院",
            "系所",
            "學號",
            "學生姓名",
            "領獎起始月份",
            "目前領獎月份",
            "領獎結束月份",
            "合計目前領獎月份數",
            "休學/退學/畢業",
            "備註",
        ]
    )
    for row in rows:
        sheet.append(row)

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _row(no, student_number, start, current, stated=None):
    return [no, "電機學院", "電機工程學系", student_number, "測試生", start, current, "", stated, "", ""]


@pytest.fixture
async def db():
    """In-memory SQLite session with the schema and a scholarship type seeded."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        session.add(
            ScholarshipType(
                id=SCHOLARSHIP_TYPE_ID,
                code="phd_nstc",
                name="國科會博士生獎學金",
            )
        )
        session.add(
            User(
                id=IMPORTER_ID,
                nycu_id="admin601",
                email="admin601@nycu.edu.tw",
                name="Admin",
            )
        )
        await session.commit()
        yield session

    await engine.dispose()


async def _preview(db, rows):
    service = ReceivedMonthsImportService()
    return service, await service.preview(
        db,
        content=_build_workbook_bytes(rows),
        file_name="nstc_received.xlsx",
        scholarship_type_id=SCHOLARSHIP_TYPE_ID,
        importer_id=IMPORTER_ID,
    )


async def _ledger(db):
    result = await db.execute(select(StudentReceivedMonthRecord))
    return {record.student_number: record for record in result.scalars().all()}


class TestPreview:
    async def test_preview_stages_without_writing_to_the_ledger(self, db):
        _, run = await _preview(db, [_row(1, "310460031", "113年9月", "115年8月", 24)])

        assert run.status == IMPORT_STATUS_PENDING
        assert run.total_rows == 1
        assert run.valid_rows == 1
        assert run.error_rows == 0
        assert await _ledger(db) == {}, "preview must not touch the ledger"

    async def test_preview_counts_warnings_and_errors_separately(self, db):
        _, run = await _preview(
            db,
            [
                _row(1, "310460031", "113年9月", "115年8月", 24),  # clean
                _row(2, "310460032", "113年9月", "115年8月", 22),  # 合計 mismatch
                _row(3, "310460033", "", "115年8月", 12),  # unparseable start
            ],
        )

        assert (run.total_rows, run.valid_rows, run.warning_rows, run.error_rows) == (3, 2, 1, 1)

    async def test_unknown_scholarship_type_is_rejected(self, db):
        service = ReceivedMonthsImportService()
        with pytest.raises(ScholarshipException) as exc:
            await service.preview(
                db,
                content=_build_workbook_bytes([_row(1, "310460031", "113年9月", "115年8月")]),
                file_name="x.xlsx",
                scholarship_type_id=999999,
                importer_id=IMPORTER_ID,
            )
        assert exc.value.status_code == 404

    async def test_unreadable_file_is_a_400(self, db):
        service = ReceivedMonthsImportService()
        with pytest.raises(ScholarshipException) as exc:
            await service.preview(
                db,
                content=b"not-a-workbook",
                file_name="x.xlsx",
                scholarship_type_id=SCHOLARSHIP_TYPE_ID,
                importer_id=IMPORTER_ID,
            )
        assert exc.value.status_code == 400


class TestConfirm:
    async def test_confirm_inserts_valid_rows_and_skips_errored_ones(self, db):
        service, run = await _preview(
            db,
            [
                _row(1, "310460031", "113年9月", "115年8月", 24),
                _row(2, "310460032", "", "115年8月", 12),  # errored
            ],
        )

        result = await service.confirm(db, run.id, importer_id=IMPORTER_ID)

        assert result["created"] == 1
        assert result["updated"] == 0
        ledger = await _ledger(db)
        assert set(ledger) == {"310460031"}, "errored rows must never reach the ledger"
        assert ledger["310460031"].months == 24
        assert ledger["310460031"].award_start_month == 11309
        assert ledger["310460031"].award_current_month == 11508

    async def test_confirm_stores_the_verbatim_source_row(self, db):
        service, run = await _preview(db, [_row(1, "310460031", "113年9月", "115年8月", 24)])
        await service.confirm(db, run.id, importer_id=IMPORTER_ID)

        raw = (await _ledger(db))["310460031"].raw_row
        assert raw["學號"] == "310460031"
        assert raw["領獎起始月份"] == "113年9月"
        assert raw["合計目前領獎月份數"] == "24"
        assert raw["學院"] == "電機學院"

    async def test_reimport_updates_the_existing_row_rather_than_duplicating(self, db):
        service, first = await _preview(db, [_row(1, "310460031", "113年9月", "115年8月", 24)])
        await service.confirm(db, first.id, importer_id=IMPORTER_ID)

        service, second = await _preview(db, [_row(1, "310460031", "113年9月", "115年10月", 26)])
        result = await service.confirm(db, second.id, importer_id=IMPORTER_ID)

        assert (result["created"], result["updated"]) == (0, 1)
        ledger = await _ledger(db)
        assert len(ledger) == 1, "UNIQUE(學號, type) — one live row per student"
        assert ledger["310460031"].months == 26
        assert ledger["310460031"].import_id == second.id

    async def test_a_warned_row_still_imports_with_the_derived_value(self, db):
        service, run = await _preview(db, [_row(1, "310460031", "113年9月", "115年8月", 22)])
        await service.confirm(db, run.id, importer_id=IMPORTER_ID)

        assert (await _ledger(db))["310460031"].months == 24, "F→G wins over 合計"

    async def test_student_unknown_to_the_system_still_imports(self, db):
        # No application, no user, no roster item — the ledger has no FK on
        # student_number precisely so this works.
        service, run = await _preview(db, [_row(1, "999999999", "114年1月", "114年3月", 3)])
        await service.confirm(db, run.id, importer_id=IMPORTER_ID)

        assert (await _ledger(db))["999999999"].months == 3

    async def test_confirm_marks_the_run_completed_and_clears_staged_data(self, db):
        service, run = await _preview(db, [_row(1, "310460031", "113年9月", "115年8月", 24)])
        await service.confirm(db, run.id, importer_id=IMPORTER_ID)

        refreshed = (await db.execute(select(ReceivedMonthImport).where(ReceivedMonthImport.id == run.id))).scalar_one()
        assert refreshed.status == IMPORT_STATUS_COMPLETED
        assert refreshed.confirmed_at is not None
        assert refreshed.parsed_data is None, "staged PII must not linger after confirm"

    async def test_a_run_cannot_be_confirmed_twice(self, db):
        service, run = await _preview(db, [_row(1, "310460031", "113年9月", "115年8月", 24)])
        await service.confirm(db, run.id, importer_id=IMPORTER_ID)

        with pytest.raises(ScholarshipException) as exc:
            await service.confirm(db, run.id, importer_id=IMPORTER_ID)
        assert exc.value.status_code == 400

    async def test_confirm_with_only_errored_rows_is_rejected(self, db):
        service, run = await _preview(db, [_row(1, "310460031", "", "", None)])

        with pytest.raises(ScholarshipException) as exc:
            await service.confirm(db, run.id, importer_id=IMPORTER_ID)
        assert exc.value.status_code == 400
        assert await _ledger(db) == {}

    async def test_confirming_an_unknown_run_is_a_404(self, db):
        service = ReceivedMonthsImportService()
        with pytest.raises(ScholarshipException) as exc:
            await service.confirm(db, 987654, importer_id=IMPORTER_ID)
        assert exc.value.status_code == 404


class TestCancel:
    async def test_cancel_discards_staged_rows_without_writing(self, db):
        service, run = await _preview(db, [_row(1, "310460031", "113年9月", "115年8月", 24)])

        await service.cancel(db, run.id)

        refreshed = (await db.execute(select(ReceivedMonthImport).where(ReceivedMonthImport.id == run.id))).scalar_one()
        assert refreshed.status == "cancelled"
        assert refreshed.parsed_data is None
        assert await _ledger(db) == {}

    async def test_a_cancelled_run_cannot_then_be_confirmed(self, db):
        service, run = await _preview(db, [_row(1, "310460031", "113年9月", "115年8月", 24)])
        await service.cancel(db, run.id)

        with pytest.raises(ScholarshipException):
            await service.confirm(db, run.id, importer_id=IMPORTER_ID)
