"""Classification of database errors by PostgreSQL SQLSTATE.

Some database errors are really *invalid input*: a value too long for a VARCHAR,
an unparseable enum label, a numeric overflow. Those are client errors and must
surface as 422 rather than 500. A unique or foreign-key violation is a 409.

Classification is by SQLSTATE rather than by exception class because the two
drivers disagree on shape:

* **asyncpg** — SQLAlchemy's dialect wraps the driver exception in its own
  ``Error`` class, so what is raised is a plain ``DBAPIError``, NOT
  ``sqlalchemy.exc.DataError``; the real ``asyncpg.exceptions`` object sits
  further down the ``__cause__`` chain and carries ``.sqlstate``.
* **psycopg2** (sync path) — SQLAlchemy classifies it correctly, and the driver
  error carries the same code as ``.pgcode``.

Matching the exact codes also keeps the mapping narrow. Deliberately excluded:

* ``23502`` not-null and ``23514`` check violations — a service that forgets to
  populate a ``nullable=False`` column is a server bug, and answering 409 would
  both lie to the client and hide it from 5xx alerting.
* ``22012`` division-by-zero and the rest of class 22 — server-side arithmetic,
  not request payload.
"""

from sqlalchemy.exc import DBAPIError

# Class 22 (data exception), limited to "this value cannot be represented".
INVALID_INPUT_SQLSTATES = frozenset(
    {
        "22001",  # string_data_right_truncation — value longer than the column
        "22003",  # numeric_value_out_of_range
        "22007",  # invalid_datetime_format
        "22008",  # datetime_field_overflow
        "22P02",  # invalid_text_representation — e.g. unknown enum label
    }
)

# Class 23 (integrity constraint violation), limited to genuine conflicts.
CONFLICT_SQLSTATES = frozenset(
    {
        "23503",  # foreign_key_violation
        "23505",  # unique_violation
    }
)

# Guard against a self-referential or pathologically long __cause__ chain.
_MAX_CAUSE_DEPTH = 10


def sqlstate_of(exc: BaseException) -> str | None:
    """Return the PostgreSQL SQLSTATE behind a SQLAlchemy ``DBAPIError``, if any."""
    if not isinstance(exc, DBAPIError):
        return None

    current = exc.orig
    for _ in range(_MAX_CAUSE_DEPTH):
        if current is None:
            return None
        # asyncpg exposes .sqlstate; psycopg2 exposes the same code as .pgcode.
        code = getattr(current, "sqlstate", None) or getattr(current, "pgcode", None)
        if code:
            return str(code)
        current = getattr(current, "__cause__", None)

    return None


def is_invalid_input_error(exc: BaseException) -> bool:
    """True when ``exc`` means the request carried an unrepresentable value."""
    return sqlstate_of(exc) in INVALID_INPUT_SQLSTATES


def is_constraint_violation_error(exc: BaseException) -> bool:
    """True when ``exc`` means the request conflicts with existing data."""
    return sqlstate_of(exc) in CONFLICT_SQLSTATES
