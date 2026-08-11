"""Classification of database errors that are really *invalid input*.

PostgreSQL class-22 errors ("data exception": value too long for a VARCHAR,
unparseable enum label, numeric overflow, bad date literal) are raised when a
request carries a value the column cannot represent. Those are client errors,
not server faults, so they must surface as 422 rather than 500.

The async path makes this non-obvious: SQLAlchemy's asyncpg dialect wraps the
driver exception in its own ``Error`` class, so the raised object is a plain
``DBAPIError`` and NOT ``sqlalchemy.exc.DataError`` the way psycopg2 (sync
path) produces. The real ``asyncpg.exceptions.DataError`` sits further down the
``__cause__`` chain, which is why this walks it instead of a single isinstance.
"""

from sqlalchemy.exc import DataError, DBAPIError, IntegrityError

try:  # pragma: no cover - asyncpg is always installed in the app image
    from asyncpg.exceptions import DataError as AsyncpgDataError
    from asyncpg.exceptions import IntegrityConstraintViolationError as AsyncpgIntegrityError
except ImportError:  # pragma: no cover
    AsyncpgDataError = None
    AsyncpgIntegrityError = None

# Guard against a self-referential or pathologically long __cause__ chain.
_MAX_CAUSE_DEPTH = 10


def _driver_error_matches(exc: BaseException, driver_error_type) -> bool:
    """Walk the ``__cause__`` chain under a DBAPIError looking for a driver error."""
    if not isinstance(exc, DBAPIError) or driver_error_type is None:
        return False

    current = exc.orig
    for _ in range(_MAX_CAUSE_DEPTH):
        if current is None:
            return False
        if isinstance(current, driver_error_type):
            return True
        current = getattr(current, "__cause__", None)

    return False


def is_invalid_input_error(exc: BaseException) -> bool:
    """True when ``exc`` is a PostgreSQL data exception caused by request input."""
    # Sync path (psycopg2): SQLAlchemy classifies it correctly on its own.
    if isinstance(exc, DataError):
        return True
    # Async path (asyncpg): unwrap the dialect's wrapper to find the driver error.
    return _driver_error_matches(exc, AsyncpgDataError)


def is_constraint_violation_error(exc: BaseException) -> bool:
    """True when ``exc`` is a PostgreSQL integrity-constraint violation.

    Class-23 errors (unique, foreign key, check, not-null) mean the request
    conflicts with data that already exists or with a declared invariant — a
    409, not a server fault. The full traceback is still logged before this is
    consulted, so a genuine server-side bug that trips a constraint stays
    diagnosable in the logs.
    """
    if isinstance(exc, IntegrityError):
        return True
    return _driver_error_matches(exc, AsyncpgIntegrityError)
