"""Map database driver errors onto the HTTP status they actually deserve.

Context: an authenticated OWASP ZAP active scan (2026-08-06, `main` @ e79d8f33)
produced 4,950 HTTP 500s across 54 production-reachable endpoints. Almost all of
them were the database rejecting *caller input* — an invalid enum literal, a
string longer than the column, a NUL byte — surfacing as an unhandled
`DBAPIError` and falling through to the generic 500 handler.

A 500 says "the server is broken". These are the client sending something the
schema cannot represent, which is a 4xx. Mapping them correctly also stops the
noise from burying real faults in monitoring.

Rather than enumerate driver exception classes (asyncpg and psycopg2 raise
different types for the same condition), match on the SQLSTATE code, which is
defined by the SQL standard and identical across drivers. The two-character
prefix is the "class" and is all we need:

    class 22 — data exception            → 400 Bad Request
    class 23 — integrity constraint      → 409 Conflict

Deliberately NOT mapped: class 08 (connection), 53 (insufficient resources),
57 (operator intervention) and friends are genuine server-side faults and must
keep returning 5xx. `main.py` already routes `OperationalError`/`TimeoutError`
to 503 ahead of this.
"""

from __future__ import annotations

from typing import Optional

# SQLSTATE class → (HTTP status, user-facing message).
# Messages are deliberately generic: they must not echo the driver's text back
# to the caller, which can contain column names, SQL fragments or the offending
# value.
_SQLSTATE_CLASS_MAP: dict[str, tuple[int, str]] = {
    "22": (400, "輸入資料格式不正確"),
    "23": (409, "資料衝突：違反唯一性或關聯限制"),
}


def _extract_sqlstate(exc: BaseException) -> Optional[str]:
    """Pull the SQLSTATE off a SQLAlchemy wrapper or a raw driver error.

    SQLAlchemy wraps driver errors and exposes the original on `.orig`. asyncpg
    spells the code `sqlstate`; psycopg2 spells it `pgcode`. Check the wrapper
    itself too, so a bare driver exception still resolves.
    """
    for candidate in (getattr(exc, "orig", None), exc):
        if candidate is None:
            continue
        for attr in ("sqlstate", "pgcode"):
            code = getattr(candidate, attr, None)
            if isinstance(code, str) and len(code) >= 2:
                return code
    return None


def map_db_exception(exc: BaseException) -> Optional[tuple[int, str]]:
    """Return `(status_code, message)` for a caller-input DB error, else None.

    None means "not a client-input problem" — the caller should fall through to
    its existing 5xx handling.
    """
    sqlstate = _extract_sqlstate(exc)
    if not sqlstate:
        return None
    return _SQLSTATE_CLASS_MAP.get(sqlstate[:2])
