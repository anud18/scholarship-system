"""
Tests for `app.utils.endpoint_decorators.handle_college_review_errors`.

This decorator translates 7 exception classes into specific HTTP status
codes. The mapping is a load-bearing API contract — every college-review
endpoint relies on it for consistent error responses. A regression in
the mapping (e.g., RankingNotFoundError accidentally yielding a 500
instead of a 404) would silently break the frontend's error-handling
branches.

Coverage:
- ReviewPermissionError → 403
- RankingNotFoundError → 404
- RankingModificationError → 400
- ValueError → 400 (with "Invalid request data:" prefix)
- IntegrityError → 409
- DatabaseError → 503
- Unknown Exception → 500 (with exc_info=True logging)
- Happy path: the wrapper passes return values through

Wave 2e — fifth pure-function test coverage PR.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException, status
from sqlalchemy.exc import DatabaseError, IntegrityError

from app.services.college_review_service import (
    RankingModificationError,
    RankingNotFoundError,
    ReviewPermissionError,
)
from app.utils.endpoint_decorators import handle_college_review_errors

pytestmark = pytest.mark.smoke


def _wrap_raiser(exc: Exception):
    """
    Helper: produce a decorated async function that immediately raises the
    supplied exception. Lets each test focus on one branch of the decorator's
    exception mapping.
    """

    @handle_college_review_errors
    async def _inner():
        raise exc

    return _inner


# ---------------------------------------------------------------------------
# Domain exceptions → specific HTTP statuses
# ---------------------------------------------------------------------------


class TestDomainExceptionMapping:
    @pytest.mark.asyncio
    async def test_review_permission_error_to_403(self) -> None:
        with pytest.raises(HTTPException) as excinfo:
            await _wrap_raiser(ReviewPermissionError("user cannot edit"))()
        assert excinfo.value.status_code == status.HTTP_403_FORBIDDEN
        assert excinfo.value.detail == "user cannot edit"

    @pytest.mark.asyncio
    async def test_ranking_not_found_to_404(self) -> None:
        with pytest.raises(HTTPException) as excinfo:
            await _wrap_raiser(RankingNotFoundError("ranking 42 not found"))()
        assert excinfo.value.status_code == status.HTTP_404_NOT_FOUND
        assert excinfo.value.detail == "ranking 42 not found"

    @pytest.mark.asyncio
    async def test_ranking_modification_to_400(self) -> None:
        with pytest.raises(HTTPException) as excinfo:
            await _wrap_raiser(RankingModificationError("ranking already finalized"))()
        assert excinfo.value.status_code == status.HTTP_400_BAD_REQUEST
        assert excinfo.value.detail == "ranking already finalized"


# ---------------------------------------------------------------------------
# Standard exceptions → HTTP statuses
# ---------------------------------------------------------------------------


class TestStandardExceptionMapping:
    @pytest.mark.asyncio
    async def test_value_error_to_400_with_prefix(self) -> None:
        """ValueError gets a documented prefix in detail so the frontend can
        distinguish input-validation failures from domain errors."""
        with pytest.raises(HTTPException) as excinfo:
            await _wrap_raiser(ValueError("bad field 'foo'"))()
        assert excinfo.value.status_code == status.HTTP_400_BAD_REQUEST
        assert excinfo.value.detail == "Invalid request data: bad field 'foo'"

    @pytest.mark.asyncio
    async def test_integrity_error_to_409(self) -> None:
        """IntegrityError gets a sanitised generic message — never leak SQL
        details to the API consumer."""
        with pytest.raises(HTTPException) as excinfo:
            await _wrap_raiser(IntegrityError("stmt", {}, Exception("UNIQUE constraint failed")))()
        assert excinfo.value.status_code == status.HTTP_409_CONFLICT
        assert excinfo.value.detail == "The request conflicts with existing data"

    @pytest.mark.asyncio
    async def test_database_error_to_503(self) -> None:
        """DatabaseError signals infrastructure failure; 503 lets the client
        retry. Again, sanitised detail."""
        with pytest.raises(HTTPException) as excinfo:
            await _wrap_raiser(DatabaseError("stmt", {}, Exception("connection refused")))()
        assert excinfo.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert excinfo.value.detail == "Database service temporarily unavailable"

    @pytest.mark.asyncio
    async def test_unknown_exception_to_500(self) -> None:
        """Anything else → 500 with sanitised message. The original exception
        is logged with exc_info=True (verified by reading the source); not
        re-tested here to avoid coupling to logger internals."""
        with pytest.raises(HTTPException) as excinfo:
            await _wrap_raiser(RuntimeError("something exploded"))()
        assert excinfo.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert excinfo.value.detail == "An unexpected error occurred"


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_return_value_passes_through(self) -> None:
        """When the wrapped function succeeds, the return value is propagated
        unchanged. No surprise wrapping."""

        @handle_college_review_errors
        async def _ok():
            return {"data": "result", "count": 42}

        result = await _ok()
        assert result == {"data": "result", "count": 42}

    @pytest.mark.asyncio
    async def test_args_and_kwargs_forwarded(self) -> None:
        """The decorator forwards *args and **kwargs verbatim."""

        @handle_college_review_errors
        async def _echo(a, b, *, c=None):
            return (a, b, c)

        assert await _echo(1, 2, c=3) == (1, 2, 3)


# ---------------------------------------------------------------------------
# Exception precedence
# ---------------------------------------------------------------------------


class TestExceptionPrecedence:
    """The decorator catches specific exception types BEFORE the generic
    Exception handler, so a domain exception that happens to subclass Exception
    still routes to the right status code. (All Python exceptions ultimately
    subclass Exception, so this is the default chain.)"""

    @pytest.mark.asyncio
    async def test_review_permission_not_caught_as_generic(self) -> None:
        """If precedence broke and ReviewPermissionError went to the Exception
        branch, we'd see 500 + the sanitised message instead of 403 + the
        original. Guard against that regression."""
        with pytest.raises(HTTPException) as excinfo:
            await _wrap_raiser(ReviewPermissionError("specific message"))()
        assert excinfo.value.status_code != status.HTTP_500_INTERNAL_SERVER_ERROR
        assert excinfo.value.detail == "specific message"
