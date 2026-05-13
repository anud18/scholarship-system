"""
Tests for `app.utils.endpoint_decorators.handle_college_review_errors`.

This decorator is wrapped around every college-review endpoint and
defines the **HTTP status code contract** between server and client.
A regression here would either:
- Leak 500s for expected errors (reviewer sees scary error page for
  a normal "not found" condition)
- Leak internal exception messages in responses (information disclosure)
- Map the wrong exception → wrong status code, breaking the frontend's
  error handler switch-on-status logic

7 exception types → 7 status codes (8 cases including success path).
Pure async, no DB / no network.
"""

import pytest
from fastapi import HTTPException, status
from sqlalchemy.exc import DatabaseError, IntegrityError

from app.services.college_review_service import (
    RankingModificationError,
    RankingNotFoundError,
    ReviewPermissionError,
)
from app.utils.endpoint_decorators import handle_college_review_errors

# ─── Success path passes through ─────────────────────────────────────


@pytest.mark.asyncio
async def test_success_returns_decorated_value():
    """Pin: when wrapped function succeeds, its return value passes
    through unchanged. Sanity check the wrapper isn't accidentally
    intercepting normal returns."""

    @handle_college_review_errors
    async def ok():
        return {"result": "success"}

    assert await ok() == {"result": "success"}


# ─── Exception mappings ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_review_permission_error_maps_to_403():
    """Pin: ReviewPermissionError → 403 Forbidden. Reviewer attempts
    to modify someone else's ranking → frontend shows 'permission
    denied' instead of a generic 500."""

    @handle_college_review_errors
    async def denied():
        raise ReviewPermissionError("Cannot edit other college's ranking")

    with pytest.raises(HTTPException) as exc:
        await denied()
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN
    assert "Cannot edit other college" in exc.value.detail


@pytest.mark.asyncio
async def test_ranking_not_found_maps_to_404():
    """Pin: RankingNotFoundError → 404. Frontend swaps to 'not found'
    placeholder UI based on this status."""

    @handle_college_review_errors
    async def missing():
        raise RankingNotFoundError("Ranking 999 not found")

    with pytest.raises(HTTPException) as exc:
        await missing()
    assert exc.value.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_ranking_modification_error_maps_to_400():
    """Pin: RankingModificationError → 400. E.g., trying to modify
    a ranking after the deadline."""

    @handle_college_review_errors
    async def bad_modify():
        raise RankingModificationError("Cannot modify after deadline")

    with pytest.raises(HTTPException) as exc:
        await bad_modify()
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "deadline" in exc.value.detail


@pytest.mark.asyncio
async def test_value_error_maps_to_400_with_invalid_request_prefix():
    """Pin: ValueError → 400 'Invalid request data: ...'. The prefix
    distinguishes validation errors from domain modification errors
    (both 400) for frontend logging."""

    @handle_college_review_errors
    async def bad_value():
        raise ValueError("rank must be positive")

    with pytest.raises(HTTPException) as exc:
        await bad_value()
    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc.value.detail.startswith("Invalid request data:")
    assert "rank must be positive" in exc.value.detail


@pytest.mark.asyncio
async def test_integrity_error_maps_to_409_with_generic_message():
    """SECURITY-ADJACENT: IntegrityError → 409. Pin: detail message is
    GENERIC, not the raw SQL exception (which might leak schema info)."""

    @handle_college_review_errors
    async def integrity():
        # SQLAlchemy IntegrityError takes (statement, params, orig)
        raise IntegrityError("UNIQUE constraint failed", {}, Exception("internal SQL leak"))

    with pytest.raises(HTTPException) as exc:
        await integrity()
    assert exc.value.status_code == status.HTTP_409_CONFLICT
    # Pin: generic message, NOT the raw SQL error
    assert exc.value.detail == "The request conflicts with existing data"
    assert "SQL" not in exc.value.detail


@pytest.mark.asyncio
async def test_database_error_maps_to_503_with_generic_message():
    """SECURITY-ADJACENT: DatabaseError → 503 with generic message.
    Pin so the raw connection-string / DB schema details don't leak."""

    @handle_college_review_errors
    async def db_err():
        raise DatabaseError("connection lost to host=prod-db-1.internal", {}, Exception("oops"))

    with pytest.raises(HTTPException) as exc:
        await db_err()
    assert exc.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    # Pin: generic message, internal host info NOT in detail
    assert exc.value.detail == "Database service temporarily unavailable"
    assert "prod-db" not in exc.value.detail


@pytest.mark.asyncio
async def test_generic_exception_maps_to_500_with_safe_message():
    """SECURITY-CRITICAL: catch-all maps to 500 with generic message.
    The exception details are LOGGED (via logger.error + exc_info=True)
    but NOT returned to the client. Pin so a refactor doesn't accidentally
    `detail=str(e)` and leak internal traceback fragments."""

    @handle_college_review_errors
    async def generic_err():
        raise RuntimeError("Internal secret: API_KEY=abc123")

    with pytest.raises(HTTPException) as exc:
        await generic_err()
    assert exc.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    # Pin: secret NOT leaked in response
    assert exc.value.detail == "An unexpected error occurred"
    assert "API_KEY" not in exc.value.detail


# ─── functools.wraps preserves function metadata ─────────────────────


@pytest.mark.asyncio
async def test_wraps_preserves_function_name():
    """Pin: @functools.wraps means the decorated function reports its
    original __name__. FastAPI's debug/error logging includes the
    handler name; a regression that drops wraps() would print
    'wrapper' everywhere instead of the actual endpoint name."""

    @handle_college_review_errors
    async def my_endpoint():
        pass

    assert my_endpoint.__name__ == "my_endpoint"
