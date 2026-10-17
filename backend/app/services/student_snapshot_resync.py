"""Re-sync the SIS term data (API 2, ``trm_*``) of an application's snapshot.

An application's ``student_data`` is taken once, when the draft is created. When
the SIS term API failed at that moment (timeout, outage) the snapshot is stored
with ``_term_data_status != "success"`` and no ``trm_*`` fields, so every export
reading ``trm_depname`` / ``trm_termcount`` (系所 / 年級) comes out blank.

This module re-fetches ONLY the term part for such an application:
``std_*`` (API 1) and any non-SIS keys of the snapshot stay as they were, so a
submitted application keeps its 申請當時 basic data while gaining the missing
term data. Used by the admin 重新同步 endpoint and the backfill script.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.college_mappings import ORIGINAL_ACADEMY_CODES_KEY
from app.core.exceptions import NotFoundError, ValidationError
from app.models.application import Application
from app.services.student_service import StudentService

logger = logging.getLogger(__name__)

TERM_STATUS_KEY = "_term_data_status"
TERM_ERROR_KEY = "_term_error_message"
TERM_RESYNCED_AT_KEY = "_term_resynced_at"
TERM_STATUS_SUCCESS = "success"
TERM_STATUS_ERROR = "error"
TERM_FIELD_PREFIX = "trm_"
ALREADY_COMPLETE_MESSAGE = "學期資料已由其他操作補齊"


@dataclass(frozen=True)
class TermResyncResult:
    app_id: str
    previous_status: Optional[str]
    new_status: Optional[str]
    updated: bool
    error_message: Optional[str] = None


def needs_term_resync(student_data: Optional[Dict[str, Any]]) -> bool:
    """True when the snapshot's term data is missing or incomplete (error / partial / never fetched)."""
    return (student_data or {}).get(TERM_STATUS_KEY) != TERM_STATUS_SUCCESS


def drop_term_fields(student_data: Dict[str, Any]) -> Dict[str, Any]:
    """A copy of a snapshot without its ``trm_*`` fields and raw academy codes (for a full refresh)."""
    return {
        k: v for k, v in student_data.items() if not k.startswith(TERM_FIELD_PREFIX) and k != ORIGINAL_ACADEMY_CODES_KEY
    }


def merge_term_snapshot(current: Dict[str, Any], fresh: Dict[str, Any], resynced_at: str) -> Dict[str, Any]:
    """Return a new snapshot: ``current`` with its term block replaced by the one of ``fresh``.

    The old ``trm_*`` fields are dropped first, so a ``partial`` (other-term) snapshot
    never mixes stale fields of one term with fresh fields of another.
    """
    term_fields = {k: v for k, v in fresh.items() if k.startswith(TERM_FIELD_PREFIX)}
    merged = {
        **drop_term_fields(current),
        **term_fields,
        TERM_STATUS_KEY: fresh.get(TERM_STATUS_KEY),
        TERM_ERROR_KEY: fresh.get(TERM_ERROR_KEY),
        TERM_RESYNCED_AT_KEY: resynced_at,
    }
    # Raw codes normalization replaced, keyed by field: keep the basic ones, take the term ones fresh
    original_codes = {
        **{
            k: v
            for k, v in (current.get(ORIGINAL_ACADEMY_CODES_KEY) or {}).items()
            if not k.startswith(TERM_FIELD_PREFIX)
        },
        **{k: v for k, v in (fresh.get(ORIGINAL_ACADEMY_CODES_KEY) or {}).items() if k.startswith(TERM_FIELD_PREFIX)},
    }
    if original_codes:
        merged[ORIGINAL_ACADEMY_CODES_KEY] = original_codes
    return merged


def application_student_code(application: Application) -> str:
    """The SIS 學號 the application belongs to (from its snapshot — never the caller's)."""
    student_code = ((application.student_data or {}).get("std_stdcode") or "").strip()
    if not student_code:
        raise ValidationError(f"申請 {application.app_id} 的學生資料缺少學號，無法向學籍系統查詢")
    return student_code


async def fetch_application_snapshot(student_service: StudentService, application: Application) -> Dict[str, Any]:
    """Fetch a live SIS snapshot for the application's own student, academic year and semester.

    Bypasses the SIS cache. SIS failures (ServiceUnavailableError / NotFoundError) propagate.
    """
    return await student_service.get_student_snapshot(
        application_student_code(application),
        academic_year=str(application.academic_year),
        semester=getattr(application.semester, "value", application.semester),
        fresh=True,
    )


async def _lock_application(db: AsyncSession, application_id: int) -> Application:
    """Re-read the row under ``FOR UPDATE``, overwriting any stale copy in the session."""
    stmt = (
        select(Application)
        .where(Application.id == application_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return (await db.execute(stmt)).scalar_one()


async def resync_application_term_data(
    db: AsyncSession, application_id: int, student_service: Optional[StudentService] = None
) -> TermResyncResult:
    """Re-fetch the term data of one application and merge it into its snapshot (caller commits).

    SIS is asked without holding a lock; the row is then locked and re-read, so the
    merge builds on the LATEST snapshot (a concurrent write is never overwritten by
    a stale copy) and a snapshot completed meanwhile is left alone. The snapshot is
    also left untouched when SIS returned no term data — a resync never degrades it.
    Raises NotFoundError for an unknown id; SIS basic-data failures propagate.
    """
    application = await db.get(Application, application_id)
    if application is None:
        raise NotFoundError(f"Application {application_id} not found")
    app_id = application.app_id
    previous_status = (application.student_data or {}).get(TERM_STATUS_KEY)

    fresh = await fetch_application_snapshot(student_service or StudentService(), application)
    new_status = fresh.get(TERM_STATUS_KEY)
    if new_status == TERM_STATUS_ERROR:
        # Term lookup failed or SIS has no record for the year — the reason says which
        logger.warning(f"SIS term resync for {app_id} got no term data: {fresh.get(TERM_ERROR_KEY)}")
        return TermResyncResult(
            app_id, previous_status, new_status, updated=False, error_message=fresh.get(TERM_ERROR_KEY)
        )

    locked = await _lock_application(db, application_id)
    latest = locked.student_data or {}
    if not needs_term_resync(latest):
        logger.info(f"SIS term resync for {app_id} skipped: completed concurrently")
        return TermResyncResult(
            app_id, previous_status, latest.get(TERM_STATUS_KEY), updated=False, error_message=ALREADY_COMPLETE_MESSAGE
        )

    locked.student_data = merge_term_snapshot(latest, fresh, datetime.now(timezone.utc).isoformat())
    logger.info(f"SIS term resync for {app_id}: {previous_status} -> {new_status}")
    return TermResyncResult(app_id, previous_status, new_status, updated=True)
