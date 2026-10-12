"""統計各學院學生獲獎人數 — shared loader/renderer for the award-count sheet.

獲獎人數 means the students on the 分發名單 (allocated ranking items) — or, for
one monthly 造冊, the students included in that roster. Both endpoints hand
over ``(application, awarded sub-type)`` pairs; this module resolves the
scholarship's sub-type columns, tallies per college and renders the workbook.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.application import Application
from app.models.scholarship import ScholarshipType
from app.services.college_stats_export_service import AWARD_REPORT_NAME, StatsRecord, build_award_stats_workbook
from app.utils.application_helpers import get_academy_code_from_data
from app.utils.export_download import sanitise_filename_part


@dataclass(frozen=True)
class AwardStatsExport:
    payload: bytes
    filename: str
    record_count: int


def award_record(application: Application, sub_type: Optional[str]) -> StatsRecord:
    """One awarded slot: the student, their college, and the sub-type they were awarded."""
    return StatsRecord(
        user_id=application.user_id,
        academy_code=get_academy_code_from_data(application.student_data or {}),
        sub_type_codes=(sub_type,) if sub_type else (),
    )


async def build_award_stats_export(
    db: AsyncSession,
    *,
    scholarship_type_id: int,
    awards: Iterable[Tuple[Application, Optional[str]]],
    title_prefix: str,
    filename_stem: Optional[str] = None,
) -> AwardStatsExport:
    """Render 統計各學院學生獲獎人數 for ``awards``.

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

    records = [award_record(app, sub_type) for app, sub_type in awards]
    scholarship_name = scholarship.name or scholarship.code
    payload = build_award_stats_workbook(
        title=f"{title_prefix}{scholarship_name} {AWARD_REPORT_NAME}",
        records=records,
        sub_type_configs=[(c.sub_type_code, c.name) for c in scholarship.get_active_sub_type_configs()],
        known_names={c.sub_type_code: c.name for c in scholarship.sub_type_configs},
    )
    stem = filename_stem or f"{title_prefix}{scholarship_name}"
    return AwardStatsExport(
        payload=payload,
        filename=f"{sanitise_filename_part(stem)}_{AWARD_REPORT_NAME}.xlsx",
        record_count=len(records),
    )
