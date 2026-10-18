"""統計各學院學生獲獎人數 — shared loader/renderer for the award-count sheet.

獲獎人數 means the students on the 分發名單 (allocated ranking items) — or, for
one monthly 造冊, the students included in that roster. Both endpoints hand
over one ``StatsRecord`` per awarded slot (see ``award_record``); this module
resolves the scholarship's sub-type columns, tallies per college and renders
the workbook.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.scholarship import ScholarshipType
from app.services.college_stats_export_service import (
    AWARD_COUNT_LABEL,
    AWARD_REPORT_NAME,
    StatsRecord,
    build_workbook,
    scholarship_stats_columns,
    tally_college_counts,
)
from app.utils.application_helpers import get_academy_code_from_data
from app.utils.export_download import sanitise_filename_part


@dataclass(frozen=True)
class AwardStatsExport:
    payload: bytes
    filename: str
    record_count: int


def award_record(user_id: int, student_data: Optional[Mapping[str, Any]], sub_type: Optional[str]) -> StatsRecord:
    """One awarded slot: the student, their college, and the sub-type they were awarded.

    College is API 1's ``std_academyno`` first (``get_academy_code_from_data``) —
    the same precedence the 分發結果名單 panel and the 造冊明細 use — so a student
    sits in the same college row here as in the list the admin is looking at.
    """
    return StatsRecord(
        user_id=user_id,
        academy_code=get_academy_code_from_data(student_data or {}),
        sub_type_codes=(sub_type,) if sub_type else (),
    )


async def build_award_stats_export(
    db: AsyncSession,
    *,
    scholarship_type_id: int,
    records: Sequence[StatsRecord],
    title_prefix: str,
    filename_stem: Optional[str] = None,
) -> AwardStatsExport:
    """Render 統計各學院學生獲獎人數 for ``records``.

    ``title_prefix`` precedes the scholarship name in the sheet title (e.g.
    ``115學年度``); ``filename_stem`` defaults to ``{title_prefix}{scholarship}``.
    """
    # scalar_one(): callers reach here through rows that FK onto this
    # scholarship type, so a miss is a broken invariant, not a 404.
    scholarship = (
        await db.execute(
            select(ScholarshipType)
            .options(selectinload(ScholarshipType.sub_type_configs))
            .where(ScholarshipType.id == scholarship_type_id)
        )
    ).scalar_one()

    columns = scholarship_stats_columns(scholarship, records, single_column_label=AWARD_COUNT_LABEL)
    scholarship_name = scholarship.name or scholarship.code
    payload = build_workbook(
        title=f"{title_prefix}{scholarship_name} {AWARD_REPORT_NAME}",
        columns=columns,
        rows=tally_college_counts(records, columns),
        sheet_name=AWARD_REPORT_NAME,
    )
    stem = filename_stem or f"{title_prefix}{scholarship_name}"
    return AwardStatsExport(
        payload=payload,
        filename=f"{sanitise_filename_part(stem)}_{AWARD_REPORT_NAME}.xlsx",
        record_count=len(records),
    )
