"""
Tests for `app.db.session.handle_cached_statement_error`.

This is the per-operation retry wrapper used around individual session
queries when the asyncpg `InvalidCachedStatementError` may fire (after
schema migrations). Distinct from the broader
`handle_database_operation_with_retry` (wave 6a34) which runs multiple
retries against a fresh connection; this helper does ONE retry on the
same session after invalidating it.

Bugs cause:
- Non-cache errors silently retried → multiplies user-facing latency
- Cache errors not invalidating the session → infinite retry loop
  against the same broken cached plan
- Retry success not propagating result → caller sees None instead of
  the actual query result

5 cases. Pure async, session mocked.
"""

from unittest.mock import AsyncMock

import pytest
from asyncpg.exceptions import InvalidCachedStatementError

from app.db.session import handle_cached_statement_error


def _fake_session():
    """A mock AsyncSession exposing invalidate() and rollback() as awaitables."""
    session = AsyncMock()
    session.invalidate = AsyncMock()
    session.rollback = AsyncMock()
    return session


# Helper to build an InvalidCachedStatementError. It takes a message arg.
def _cache_error():
    return InvalidCachedStatementError("cached statement plan is invalid")


# ─── Success on first attempt ────────────────────────────────────────


@pytest.mark.asyncio
async def test_success_on_first_attempt_returns_result():
    """Pin: when the wrapped op succeeds, no retry, no invalidate.
    The session's invalidate() and rollback() must NOT be called on
    the happy path."""
    session = _fake_session()
    call_count = 0

    async def op():
        nonlocal call_count
        call_count += 1
        return "ok"

    result = await handle_cached_statement_error(session, op)

    assert result == "ok"
    assert call_count == 1
    session.invalidate.assert_not_awaited()
    session.rollback.assert_not_awaited()


# ─── InvalidCachedStatementError → invalidate + rollback + retry ─────


@pytest.mark.asyncio
async def test_cache_error_invalidates_session_and_retries():
    """Pin: on InvalidCachedStatementError, the session is invalidated,
    rolled back, then the op is retried. Success on retry returns
    the result."""
    session = _fake_session()
    call_count = 0

    async def op():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise _cache_error()
        return "recovered"

    result = await handle_cached_statement_error(session, op)

    assert result == "recovered"
    assert call_count == 2  # one initial + one retry
    session.invalidate.assert_awaited_once()
    session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_cache_error_then_retry_failure_reraises():
    """Pin: if retry also fails (any exception, not just cache error),
    the retry exception bubbles up. Caller sees the actual failure
    rather than getting None or stuck in another retry loop."""
    session = _fake_session()
    call_count = 0

    async def op():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise _cache_error()
        raise RuntimeError("retry failure")

    with pytest.raises(RuntimeError) as exc:
        await handle_cached_statement_error(session, op)

    assert "retry failure" in str(exc.value)
    assert call_count == 2
    session.invalidate.assert_awaited_once()


# ─── Non-cache exception: no retry, immediate re-raise ───────────────


@pytest.mark.asyncio
async def test_non_cache_error_reraises_without_retry():
    """SECURITY/PERF: non-cache errors (e.g., IntegrityError, ValueError)
    must NOT trigger the invalidate-and-retry path. Otherwise users
    wait 2x as long for legitimate failures, AND the session gets
    invalidated unnecessarily."""
    session = _fake_session()
    call_count = 0

    async def op():
        nonlocal call_count
        call_count += 1
        raise ValueError("regular validation failure")

    with pytest.raises(ValueError) as exc:
        await handle_cached_statement_error(session, op)

    assert "regular validation failure" in str(exc.value)
    assert call_count == 1
    # No invalidate/rollback for non-cache errors
    session.invalidate.assert_not_awaited()
    session.rollback.assert_not_awaited()


# ─── Args/kwargs forwarded ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_args_kwargs_forwarded_to_op():
    """Pin: positional + keyword args passed through to the wrapped op."""
    session = _fake_session()

    async def op(a, b, *, c):
        return (a, b, c)

    result = await handle_cached_statement_error(session, op, 1, 2, c=3)
    assert result == (1, 2, 3)
