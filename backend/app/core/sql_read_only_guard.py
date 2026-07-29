"""Read-only SQL guard for admin-configured statements (issue #1223 finding A).

``email_automation_rules.condition_query`` is free-form SQL authored by an
administrator and executed verbatim by ``EmailAutomationService._get_recipients``.
Validating it only at write time is not enough: rows are also written by seeds,
by Alembic migrations, by ``PATCH /email-automation/{id}/toggle`` (which activates
a rule without re-validating it) and — in an incident — by direct DB access. The
same guard therefore runs again immediately before execution.

The guard is deliberately conservative. A statement must be:
  * exactly one statement,
  * starting with ``SELECT`` (or ``WITH ... SELECT``),
  * free of any keyword that can write, change schema, or change session state,
  * free of dollar-quoting, which can hide arbitrary text from the scanner,
  * free of the PostgreSQL functions that read the filesystem or execute a string.

That last group matters more than it looks: ``transaction_read_only`` does NOT
stop ``pg_read_file`` / ``pg_ls_dir``, and this application connects as a
PostgreSQL superuser — so without the identifier deny-list, "read-only" would
still mean "arbitrary server file read", exfiltrated through the resolved
recipient list.

Keyword matching runs on a MASKED copy in which string literals, quoted
identifiers and comments are replaced by spaces, and uses word boundaries — so
``created_at``, ``updated_at`` and ``OFFSET`` are not mistaken for CREATE /
UPDATE / SET, and a ``';'`` inside a literal is not mistaken for a statement
separator. The mask is the SAME LENGTH as the input, so callers can use it to
locate constructs by offset in the original string.

This is one layer, not two: because literals are masked before scanning, the
keyword list cannot see a payload hidden inside a string. The load-bearing
controls are the SELECT-only shape, the identifier deny-list, and the read-only
savepoint the caller wraps execution in.
"""

from __future__ import annotations

import re
from typing import Final, Optional

MAX_QUERY_LENGTH: Final[int] = 5000

# Keywords that can write, change schema or change session state.
# UNION / INTERSECT / EXCEPT are intentionally NOT here: they are read-only set
# operators, the shipped recipient query for application_submitted_student uses
# UNION, and blocking them buys nothing against an author who already controls
# the whole SELECT.
FORBIDDEN_KEYWORDS: Final[tuple[str, ...]] = (
    "ALTER",
    "ANALYZE",
    "CALL",
    "CHECKPOINT",
    "CLUSTER",
    "COMMENT",
    "COPY",
    "CREATE",
    "DEALLOCATE",
    "DELETE",
    "DISCARD",
    "DO",
    "DROP",
    "EXEC",
    "EXECUTE",
    "GRANT",
    "IMPORT",
    "INSERT",
    "INTO",
    "LISTEN",
    "LOAD",
    "LOCK",
    "MERGE",
    "MOVE",
    "NOTIFY",
    "PREPARE",
    "REASSIGN",
    "REFRESH",
    "REINDEX",
    "RESET",
    "REVOKE",
    "SET",
    "TRUNCATE",
    "UNLISTEN",
    "UPDATE",
    "VACUUM",
    "WAITFOR",
)

# Functions that read/write the filesystem, execute a string as SQL, or otherwise
# escape a read-only transaction. `SET LOCAL transaction_read_only = ON` does not
# stop any of these, and the app's DB role is a superuser.
FORBIDDEN_IDENTIFIERS: Final[tuple[str, ...]] = (
    "DBLINK",
    "DBLINK_EXEC",
    "LO_EXPORT",
    "LO_FROM_BYTEA",
    "LO_IMPORT",
    "LOAD_FILE",
    "PG_CANCEL_BACKEND",
    "PG_LOGDIR_LS",
    "PG_LS_DIR",
    "PG_LS_LOGDIR",
    "PG_LS_WALDIR",
    "PG_READ_BINARY_FILE",
    "PG_READ_FILE",
    "PG_RELOAD_CONF",
    "PG_SLEEP",
    "PG_STAT_FILE",
    "PG_TERMINATE_BACKEND",
    "QUERY_TO_XML",
)

# Plain alternation of literals with word boundaries: linear-time, no nested
# quantifiers, so this is not a ReDoS vector. \b handles the underscores
# correctly — \bPG_READ_FILE\b matches, and \bLOAD\b does not match LOAD_FILE.
_FORBIDDEN_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:" + "|".join(FORBIDDEN_KEYWORDS + FORBIDDEN_IDENTIFIERS) + r")\b", re.IGNORECASE
)
_STATEMENT_START_RE: Final[re.Pattern[str]] = re.compile(r"^\s*(?:SELECT|WITH)\b", re.IGNORECASE)


class UnsafeConditionQueryError(ValueError):
    """Raised when a stored SQL string is not a single read-only SELECT.

    Every message this module raises is CURATED and safe to show the admin who
    authored the query — it names the rejected construct and nothing about server
    internals. That is a deliberate part of this module's contract; see
    :func:`describe_if_unsafe` for the client-facing accessor.
    """


def _mask(sql: str, *, mask_quoted_identifiers: bool) -> str:
    """Shared same-length masker. See :func:`mask_literals` for the contract.

    ``mask_quoted_identifiers`` selects between the two views the guard needs:

    * ``True``  — double-quoted identifiers are blanked too. Used for STRUCTURAL
      checks (statement shape, ``;`` counting) and for placeholder offsets, where
      a ``;`` or ``{`` inside ``"an identifier"`` must not be misread.
    * ``False`` — double-quoted identifier CONTENT is preserved (only the quote
      characters become spaces). Used for the forbidden-name scan, because
      PostgreSQL resolves ``"pg_read_file"`` to exactly the same function as
      ``pg_read_file``. Blanking those would let every entry in
      FORBIDDEN_IDENTIFIERS be bypassed by simply quoting the name.
    """
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if ch == "$":
            # Dollar-quoting can hide arbitrary text from every scanner below.
            raise UnsafeConditionQueryError("cannot use dollar-quoted strings")
        if ch in ("'", '"'):
            quote = ch
            start = i
            i += 1
            while True:
                if i >= n:
                    raise UnsafeConditionQueryError("contains an unterminated quoted string")
                if sql[i] == quote:
                    if i + 1 < n and sql[i + 1] == quote:  # doubled quote = escaped quote
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            if quote == '"' and not mask_quoted_identifiers:
                # Keep the identifier text, blank only the surrounding quotes, so
                # \b word boundaries still match and the length is preserved.
                out.append(" " + sql[start + 1 : i - 1] + " ")
            else:
                out.append(" " * (i - start))
            continue
        if sql.startswith("--", i):
            newline = sql.find("\n", i)
            end = n if newline == -1 else newline
            out.append(" " * (end - i))
            i = end
            continue
        if sql.startswith("/*", i):
            start = i
            depth, i = 1, i + 2
            while depth:
                if i >= n:
                    raise UnsafeConditionQueryError("contains an unterminated block comment")
                if sql.startswith("/*", i):
                    depth, i = depth + 1, i + 2
                elif sql.startswith("*/", i):
                    depth, i = depth - 1, i + 2
                else:
                    i += 1
            out.append(" " * (i - start))
            continue
        out.append(ch)
        i += 1
    masked = "".join(out)
    # Invariant the placeholder rewriter depends on. NOT an `assert`: asserts are
    # compiled out under python -O, and a collapsed mask would make
    # bind_placeholders splice ":key" into the middle of a string literal.
    if len(masked) != len(sql):  # pragma: no cover - defensive
        raise UnsafeConditionQueryError("could not be safely parsed")
    return masked


def mask_literals(sql: str) -> str:
    """Return a SAME-LENGTH copy of *sql* with literals, identifiers and comments blanked.

    Same length is the point: :func:`~app.services.email_automation_service.bind_placeholders`
    rewrites ``{placeholder}`` occurrences by offset in the ORIGINAL string, and
    must not rewrite one that sits inside a string literal. A collapsing mask
    would misalign those offsets.
    """
    return _mask(sql, mask_quoted_identifiers=True)


def assert_read_only_select(sql: str) -> None:
    """Raise :class:`UnsafeConditionQueryError` unless *sql* is a single read-only SELECT.

    Messages are phrased so callers can prefix them with a field name, e.g.
    ``f"condition_query {exc}"``.
    """
    if len(sql) > MAX_QUERY_LENGTH:
        raise UnsafeConditionQueryError(f"exceeds maximum length of {MAX_QUERY_LENGTH} characters")

    # Structural view: quoted identifiers blanked, so a ';' inside "an identifier"
    # is not miscounted as a statement separator.
    structural = mask_literals(sql).strip()
    if structural.endswith(";"):
        structural = structural[:-1].rstrip()

    if not _STATEMENT_START_RE.match(structural):
        raise UnsafeConditionQueryError("must be a SELECT statement (a single read-only query)")

    if ";" in structural:
        raise UnsafeConditionQueryError("cannot contain multiple SQL statements")

    # Name view: quoted identifier CONTENT preserved. PostgreSQL resolves
    # "pg_read_file" to the same function as pg_read_file, so scanning the
    # structural view here would let every forbidden name be bypassed by quoting
    # it. A column legitimately named "select" is rejected as a result — that is
    # the fail-closed direction, and no shipped query does it.
    names = _mask(sql, mask_quoted_identifiers=False)
    forbidden = _FORBIDDEN_RE.search(names)
    if forbidden:
        keyword = forbidden.group(0).upper()
        # Deliberately NO "quote it instead" hint: quoting does not make the name
        # safe, it only used to hide it from this scan.
        raise UnsafeConditionQueryError(f"contains forbidden keyword: {keyword}")


def describe_if_unsafe(sql: str) -> Optional[str]:
    """Return a client-safe rejection reason for *sql*, or ``None`` when it is safe.

    Use this at API boundaries instead of interpolating a caught exception into a
    response body. The strings returned here are a documented, curated part of
    this module's contract — they name only the rejected SQL construct, never
    server internals — which is exactly the distinction
    ``test_no_exception_leak_in_endpoints`` exists to enforce. Routing the message
    through an explicit return value rather than ``str(exc)`` also means a future
    unexpected exception inside this module can never reach a client body.
    """
    try:
        assert_read_only_select(sql)
    except UnsafeConditionQueryError as exc:
        return str(exc)
    return None
