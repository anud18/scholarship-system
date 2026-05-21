"""Helpers for filtering pending-review listings by renewal vs general phase.

Educators (professors and college reviewers) should only see applications
appropriate for the *current* review phase:

- During a configuration's **renewal_{role}_review** window: only renewal
  applications (``is_renewal=True``) for that configuration.
- During the general **{role}_review** window: only non-renewal applications
  (``is_renewal=False``) for that configuration.

The renewal review windows live on :class:`ScholarshipConfiguration`
(``renewal_professor_review_*``, ``renewal_college_review_*``), and so do
the general windows (``professor_review_*``, ``college_review_*``).

This module is intentionally a tiny pure-SQL builder so both the professor
listing endpoint and the college listing endpoint can reuse the same filter
without inheriting any service state.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import and_, or_
from sqlalchemy.orm import aliased
from sqlalchemy.sql import Select

from app.models.application import Application
from app.models.scholarship import ScholarshipConfiguration

ReviewRole = Literal["professor", "college"]


def _now_utc() -> datetime:
    """UTC-aware "now"; isolated for easy patching in tests."""
    return datetime.now(timezone.utc)


def _config_fields_for_role(cfg, role: ReviewRole):
    """Return (renewal_start, renewal_end, general_start, general_end)
    columns on the supplied :class:`ScholarshipConfiguration` (or alias)
    matching ``role``.
    """
    if role == "professor":
        return (
            cfg.renewal_professor_review_start,
            cfg.renewal_professor_review_end,
            cfg.professor_review_start,
            cfg.professor_review_end,
        )
    if role == "college":
        return (
            cfg.renewal_college_review_start,
            cfg.renewal_college_review_end,
            cfg.college_review_start,
            cfg.college_review_end,
        )
    raise ValueError(f"Unknown review role: {role!r}")


def apply_renewal_phase_filter(
    stmt: Select,
    *,
    role: ReviewRole,
    now: datetime | None = None,
    alias_name: str = "renewal_phase_cfg",
) -> Select:
    """Restrict ``stmt`` to applications whose review-phase membership matches
    the current time.

    The caller is expected to have already constrained ``stmt`` to "pending"
    rows (typically ``status == under_review``); this filter overlays the
    renewal-vs-general phase split.

    Join strategy:
      - We join an *aliased* :class:`ScholarshipConfiguration` on
        ``(scholarship_type_id, academic_year)`` so this composes cleanly with
        callers that already join ``Application.scholarship_configuration``
        through the FK relationship.
      - Semester is intentionally NOT part of the join because renewal review
        windows are configured at the year level — matching on semester would
        silently drop yearly-only configurations.

    Args:
        stmt:       A ``select(Application)``-style statement to constrain.
        role:       Which review role's windows to consider ("professor" /
                    "college").
        now:        Override "current time" — for tests. Naive datetimes are
                    treated as UTC, mirroring ``renewal.py:_to_utc_aware``.
        alias_name: Alias for the joined ScholarshipConfiguration; override if
                    the caller already uses this alias name.

    Returns:
        A new ``Select`` with the join + WHERE applied.
    """
    if now is None:
        now = _now_utc()
    elif now.tzinfo is None:
        # Treat naive datetimes as UTC for consistency with the rest of the codebase
        # (see api/v1/endpoints/renewal.py `_to_utc_aware`).
        now = now.replace(tzinfo=timezone.utc)

    cfg = aliased(ScholarshipConfiguration, name=alias_name)
    renewal_start, renewal_end, general_start, general_end = _config_fields_for_role(cfg, role)

    stmt = stmt.join(
        cfg,
        and_(
            Application.scholarship_type_id == cfg.scholarship_type_id,
            Application.academic_year == cfg.academic_year,
        ),
    )

    stmt = stmt.where(
        or_(
            and_(
                Application.is_renewal.is_(True),
                renewal_start.isnot(None),
                renewal_end.isnot(None),
                renewal_start <= now,
                renewal_end >= now,
            ),
            and_(
                Application.is_renewal.is_(False),
                general_start.isnot(None),
                general_end.isnot(None),
                general_start <= now,
                general_end >= now,
            ),
        )
    )

    return stmt
