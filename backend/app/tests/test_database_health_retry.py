"""
Tests for `handle_database_operation_with_retry` in
`app.core.database_health`.

This retry wrapper is used around service-level DB operations that may
hit `InvalidCachedStatementError` after schema migrations. A regression
in the retry logic would cause:
- Transient errors on first attempt becoming permanent failures (loss of
  fault tolerance after migration)
- Non-recoverable errors silently retried 3x (multiplies user-facing
  latency on real errors)
- Wrong exception re-raised after retries exhausted (caller's error
  handler sees the wrong type)

Pure async logic — `recover_from_cached_statement_error` is mocked.
6 cases (no DB).
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.database_health import handle_database_operation_with_retry

# ─── Success path ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_success_on_first_attempt_returns_result():
    """Pin: when operation succeeds, no recovery is attempted."""
    call_count = 0

    async def op():
        nonlocal call_count
        call_count += 1
        return "ok"

    result = await handle_database_operation_with_retry(op)
    assert result == "ok"
    assert call_count == 1


@pytest.mark.asyncio
async def test_args_kwargs_forwarded():
    """Pin: positional + keyword args passed through to operation_func."""

    async def op(a, b, *, c):
        return (a, b, c)

    result = await handle_database_operation_with_retry(op, 3, 1, 2, c=3)
    # max_retries=3 is the second positional arg of the wrapper
    assert result == (1, 2, 3)


# ─── Non-recoverable error: short-circuit ────────────────────────────


@pytest.mark.asyncio
async def test_non_cached_error_raises_immediately_no_retry():
    """Pin: non-cached errors (e.g., ValueError, IntegrityError) raise
    on first attempt — no retry, no recovery attempt. Otherwise users
    wait 3x as long for legitimate failures."""
    call_count = 0

    async def op():
        nonlocal call_count
        call_count += 1
        raise ValueError("regular error, not a cache issue")

    with pytest.raises(ValueError) as exc:
        await handle_database_operation_with_retry(op)
    assert "regular error" in str(exc.value)
    assert call_count == 1


# ─── Cached statement error: retry with recovery ─────────────────────


@pytest.mark.asyncio
async def test_cached_statement_error_recovers_and_retries():
    """Pin: 'InvalidCachedStatementError' in message → recovery called,
    then retry. Success on retry returns the result."""
    call_count = 0

    async def op():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("InvalidCachedStatementError: cached plan invalidated")
        return "recovered"

    with patch(
        "app.core.database_health.recover_from_cached_statement_error",
        new=AsyncMock(return_value=True),
    ) as mock_recover:
        result = await handle_database_operation_with_retry(op)

    assert result == "recovered"
    assert call_count == 2  # first attempt + retry
    mock_recover.assert_awaited_once()


@pytest.mark.asyncio
async def test_alternate_cached_error_message_also_triggers_recovery():
    """Pin: alt message 'cached statement plan is invalid' (asyncpg
    wording) ALSO triggers recovery. Defensive — the driver might
    emit either string."""
    call_count = 0

    async def op():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("error: cached statement plan is invalid")
        return "ok"

    with patch(
        "app.core.database_health.recover_from_cached_statement_error",
        new=AsyncMock(return_value=True),
    ):
        result = await handle_database_operation_with_retry(op)

    assert result == "ok"
    assert call_count == 2


# ─── Exhausted retries: raise last exception ─────────────────────────


@pytest.mark.asyncio
async def test_exhausted_retries_raises_last_exception():
    """Pin: after max_retries attempts all fail, the LAST exception is
    re-raised (not a generic 'all retries failed' wrapper). Caller's
    exception handler can inspect the original error."""
    call_count = 0

    async def always_fail():
        nonlocal call_count
        call_count += 1
        raise RuntimeError(f"InvalidCachedStatementError attempt {call_count}")

    with patch(
        "app.core.database_health.recover_from_cached_statement_error",
        new=AsyncMock(return_value=True),
    ):
        with pytest.raises(RuntimeError) as exc:
            await handle_database_operation_with_retry(always_fail, max_retries=2)

    # max_retries=2 → 3 total attempts (0, 1, 2)
    assert call_count == 3
    # Last exception's message visible
    assert "attempt 3" in str(exc.value)


@pytest.mark.asyncio
async def test_recovery_failure_still_retries():
    """Pin: even if recovery returns False, the loop still iterates to
    the next attempt — recovery failure isn't fatal on its own. The
    operation may have transient issues that resolve on the next call
    regardless of recovery's success."""
    call_count = 0

    async def op():
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise RuntimeError("InvalidCachedStatementError")
        return "third-time-lucky"

    with patch(
        "app.core.database_health.recover_from_cached_statement_error",
        new=AsyncMock(return_value=False),  # recovery always fails
    ) as mock_recover:
        result = await handle_database_operation_with_retry(op, max_retries=3)

    assert result == "third-time-lucky"
    assert call_count == 3
    # Recovery was attempted at least once
    assert mock_recover.await_count >= 1
