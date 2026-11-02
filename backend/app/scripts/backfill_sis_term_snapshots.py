"""
Backfill the SIS term data (系所 / 年級 …) of application snapshots stored without it.

Background
----------
``Application.student_data`` is taken once, when the draft is created. When the
SIS term API (API 2) timed out or failed at that moment, the snapshot was saved
with ``_term_data_status != "success"`` and no ``trm_*`` fields — so the
學生資料彙整表 and every other export reading ``trm_depname`` / ``trm_termcount``
show a blank 系所 / 年級 for that student (e.g. prod 2026-10-06: the term-2 query
timed out and term 1 was never tried).

What this script does
---------------------
For every non-draft application whose snapshot has ``_term_data_status`` other
than ``success`` (drafts are refreshed at submit), re-fetch the term data for the
application's own 學號 / academic year / semester straight from SIS (cache
bypassed) and merge ONLY the ``trm_*`` fields + term metadata into the snapshot.
``std_*`` and all non-SIS keys are kept.

Safety properties
-----------------
* **Dry-run by default.** Without ``--apply`` nothing is written; the run lists
  the applications that WOULD be re-synced (it still queries SIS, read-only).
* **Never degrades a snapshot.** When SIS still has no term data the row is left
  untouched and reported as ``still_missing``.
* **Idempotent.** A re-synced row has ``success`` / ``partial`` status; ``success``
  rows are skipped on the next run.
* **Safe alongside the admin 重新同步 button.** Each row is re-read under a row lock
  after its SIS answer arrives, so a concurrent write is merged into, never
  overwritten, and a row completed meanwhile is left alone.
* **Gentle on SIS.** Applications are processed one at a time with ``--delay``
  seconds between SIS lookups; each applied row is committed on its own.

Usage
-----
    # from the backend/ directory (or inside the backend container)
    python -m app.scripts.backfill_sis_term_snapshots --academic-year 115              # dry run
    python -m app.scripts.backfill_sis_term_snapshots --academic-year 115 --apply
    python -m app.scripts.backfill_sis_term_snapshots --app-id APP-115-0-00182 --apply
"""

import argparse
import asyncio
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from sqlalchemy import select

from app.core.exceptions import ScholarshipException
from app.db.session import AsyncSessionLocal
from app.models.application import Application
from app.models.enums import ApplicationStatus
from app.services.student_service import StudentService
from app.services.student_snapshot_resync import (
    ALREADY_COMPLETE_MESSAGE,
    TERM_STATUS_ERROR,
    TERM_STATUS_KEY,
    needs_term_resync,
    resync_application_term_data,
)

logger = logging.getLogger("backfill_sis_term_snapshots")

DEFAULT_DELAY_SECONDS = 0.5


@dataclass
class Stats:
    candidates: int = 0
    resynced: List[str] = field(default_factory=list)
    still_missing: List[str] = field(default_factory=list)
    already_complete: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class Candidate:
    id: int
    app_id: str
    term_status: Optional[str]


async def _load_candidates(session, academic_year: Optional[int], app_ids: List[str]) -> List[Candidate]:
    """Plain values, not ORM rows: each one is re-read (and locked) when it is processed."""
    stmt = select(Application.id, Application.app_id, Application.student_data).where(
        Application.status != ApplicationStatus.draft.value
    )
    if academic_year is not None:
        stmt = stmt.where(Application.academic_year == academic_year)
    if app_ids:
        stmt = stmt.where(Application.app_id.in_(app_ids))
    rows = (await session.execute(stmt.order_by(Application.id))).all()
    # JSON status filtered in Python: portable across Postgres / SQLite
    return [
        Candidate(row.id, row.app_id, (row.student_data or {}).get(TERM_STATUS_KEY))
        for row in rows
        if needs_term_resync(row.student_data)
    ]


async def _process(session, candidate: Candidate, student_service: StudentService, apply: bool, stats: Stats) -> None:
    app_id = candidate.app_id
    try:
        result = await resync_application_term_data(session, candidate.id, student_service)
    except ScholarshipException:
        await session.rollback()
        logger.warning(f"{app_id}: SIS lookup failed (was {candidate.term_status})", exc_info=True)
        stats.failed.append(app_id)
        return

    if not result.updated:
        await session.rollback()  # releases the row lock of a concurrently completed row
        if result.error_message == ALREADY_COMPLETE_MESSAGE:
            logger.info(f"{app_id}: completed meanwhile — left untouched")
            stats.already_complete.append(app_id)
        else:
            logger.info(f"{app_id}: SIS returned no term data ({result.error_message}) — left untouched")
            stats.still_missing.append(app_id)
        return

    if apply:
        await session.commit()
        logger.info(f"{app_id}: re-synced ({result.previous_status} -> {result.new_status})")
    else:
        await session.rollback()
        logger.info(f"{app_id}: WOULD re-sync ({result.previous_status} -> {result.new_status})")
    stats.resynced.append(app_id)


async def run(academic_year: Optional[int], app_ids: List[str], apply: bool, delay: float) -> Stats:
    stats = Stats()
    student_service = StudentService()
    async with AsyncSessionLocal() as session:
        candidates = await _load_candidates(session, academic_year, app_ids)
        stats.candidates = len(candidates)
        logger.info(f"{stats.candidates} application(s) with incomplete SIS term data")
        for index, candidate in enumerate(candidates):
            await _process(session, candidate, student_service, apply, stats)
            if delay and index < len(candidates) - 1:
                await asyncio.sleep(delay)
    return stats


def _report(stats: Stats, apply: bool) -> None:
    verb = "re-synced" if apply else "would re-sync"
    print(f"\ncandidates      : {stats.candidates}")
    print(f"{verb:<16}: {len(stats.resynced)}")
    print(f"still missing   : {len(stats.still_missing)}  (SIS {TERM_STATUS_ERROR}; left untouched)")
    print(f"already complete: {len(stats.already_complete)}  (completed meanwhile; left untouched)")
    print(f"SIS failures    : {len(stats.failed)}  (re-run later)")
    for label, ids in (("still missing", stats.still_missing), ("SIS failures", stats.failed)):
        if ids:
            print(f"  {label}: {', '.join(ids)}")
    if not apply:
        print("\nDry run — nothing written. Re-run with --apply to update the snapshots.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--academic-year", type=int, help="Only applications of this 學年度 (e.g. 115)")
    parser.add_argument("--app-id", action="append", default=[], help="Only this app_id (repeatable)")
    parser.add_argument("--apply", action="store_true", help="Write the re-synced snapshots (default: dry run)")
    parser.add_argument(
        "--delay", type=float, default=DEFAULT_DELAY_SECONDS, help="Seconds between SIS lookups (default 0.5)"
    )
    args = parser.parse_args()
    if args.delay < 0:
        parser.error("--delay must be >= 0")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stats = asyncio.run(run(args.academic_year, args.app_id, args.apply, args.delay))
    _report(stats, args.apply)


if __name__ == "__main__":
    main()
