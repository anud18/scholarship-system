"""
Tests for `app/schemas/response.py` — the three generic API-response
envelope schemas the system exposes.

Why pin these?

The frontend `api.ts` auto-detect path checks `if ("success" in data &&
"message" in data)` (CLAUDE.md §5) to decide whether to unwrap the
envelope. A regression that:

  - made `success` or `message` *optional* — auto-detect would miss
    valid envelopes intermittently.
  - renamed `data` — every payload through the wrapper would surface as
    `null` on the client.
  - dropped Generic[DataType] support — types in the OpenAPI schema
    would lose their inner shape.
  - widened the optional fields silently — e.g. `data` becoming
    required would break every endpoint that returns just a message
    (delete/update with no body).

15 cases pinning the envelope contracts that downstream consumers
depend on.
"""

from typing import List

import pytest
from pydantic import BaseModel, ValidationError

from app.schemas.response import (
    ApiResponse,
    DetailedApiResponse,
    PaginatedApiResponse,
    ValidationError as ResponseValidationError,
)


class _Item(BaseModel):
    """Tiny payload type used to exercise the generic parameter."""

    id: int
    name: str


# ─── ApiResponse ─────────────────────────────────────────────────────


def test_apiresponse_requires_success_and_message():
    # Pin: both fields are non-optional. Auto-detect on the frontend
    # depends on BOTH keys being present (CLAUDE.md §5).
    with pytest.raises(ValidationError):
        ApiResponse()  # type: ignore[call-arg]


def test_apiresponse_optional_fields_default_to_none():
    # Pin: data/errors/trace_id all default to None. A message-only
    # response (DELETE / PATCH with no body) must validate cleanly.
    r = ApiResponse(success=True, message="ok")
    assert r.data is None
    assert r.errors is None
    assert r.trace_id is None


def test_apiresponse_generic_carries_inner_type():
    # Pin: Generic[DataType] flows through validation so OpenAPI schema
    # exposes the inner shape.
    r = ApiResponse[_Item](success=True, message="ok", data={"id": 7, "name": "x"})  # type: ignore[arg-type]
    assert isinstance(r.data, _Item)
    assert r.data.id == 7
    assert r.data.name == "x"


def test_apiresponse_generic_list_payload():
    r = ApiResponse[List[_Item]](
        success=True,
        message="ok",
        data=[{"id": 1, "name": "a"}, {"id": 2, "name": "b"}],  # type: ignore[arg-type]
    )
    assert isinstance(r.data, list)
    assert all(isinstance(it, _Item) for it in r.data)


def test_apiresponse_round_trip_via_model_dump():
    # Pin: model_dump round-trip preserves the envelope shape. This is
    # the exact code path used everywhere we manually wrap responses
    # per CLAUDE.md §5 ("Pydantic v2 — model_dump preferred").
    src = ApiResponse[_Item](
        success=False,
        message="failed",
        data={"id": 1, "name": "x"},  # type: ignore[arg-type]
        errors=["bad input"],
        trace_id="trace-abc",
    )
    dumped = src.model_dump()
    assert dumped["success"] is False
    assert dumped["message"] == "failed"
    assert dumped["errors"] == ["bad input"]
    assert dumped["trace_id"] == "trace-abc"
    assert dumped["data"] == {"id": 1, "name": "x"}


def test_apiresponse_from_attributes_config_enabled():
    # Pin: from_attributes=True so direct ORM-model passthrough works.
    # Drop in a SimpleNamespace-like object with the right attrs.
    class _OrmRow:
        def __init__(self):
            self.success = True
            self.message = "from orm"
            self.data = None
            self.errors = None
            self.trace_id = None

    r = ApiResponse.model_validate(_OrmRow())
    assert r.success is True
    assert r.message == "from orm"


# ─── ValidationError (inner type used by DetailedApiResponse) ────────


def test_validationerror_requires_field_and_message():
    with pytest.raises(ValidationError):
        ResponseValidationError(field="x")  # type: ignore[call-arg]


def test_validationerror_optional_code_defaults_to_none():
    ve = ResponseValidationError(field="email", message="not an email")
    assert ve.code is None


def test_validationerror_with_code():
    ve = ResponseValidationError(field="email", message="not an email", code="invalid_email")
    assert ve.code == "invalid_email"


# ─── DetailedApiResponse ─────────────────────────────────────────────


def test_detailed_response_carries_validation_errors_list():
    # Pin: validation_errors is a List[ValidationError]. The frontend
    # field-error rendering depends on this shape — flattening or
    # renaming would lose the per-field highlight.
    r = DetailedApiResponse[_Item](
        success=False,
        message="validation failed",
        validation_errors=[
            {"field": "email", "message": "required"},  # type: ignore[list-item]
            {"field": "age", "message": "must be > 0", "code": "min"},  # type: ignore[list-item]
        ],
    )
    assert r.validation_errors is not None
    assert len(r.validation_errors) == 2
    assert all(isinstance(v, ResponseValidationError) for v in r.validation_errors)
    assert r.validation_errors[1].code == "min"


def test_detailed_response_validation_errors_optional():
    r = DetailedApiResponse(success=True, message="ok")
    assert r.validation_errors is None


# ─── PaginatedApiResponse ────────────────────────────────────────────


def test_paginated_response_carries_pagination_fields():
    # Pin: the 4-field pagination contract (total/page/size/pages) is
    # what the frontend pagination component reads. A regression that
    # renamed any of these would break every paginated table.
    r = PaginatedApiResponse[_Item](
        success=True,
        message="ok",
        data=[{"id": 1, "name": "a"}],  # type: ignore[arg-type]
        total=42,
        page=1,
        size=20,
        pages=3,
    )
    assert r.total == 42
    assert r.page == 1
    assert r.size == 20
    assert r.pages == 3


def test_paginated_response_data_is_list_typed():
    # Pin: data is Optional[List[DataType]] — passing a bare dict must
    # fail, so frontends never have to handle both shapes.
    with pytest.raises(ValidationError):
        PaginatedApiResponse[_Item](
            success=True,
            message="ok",
            data={"id": 1, "name": "a"},  # type: ignore[arg-type]
        )


def test_paginated_response_all_pagination_fields_optional():
    # Pin: page/size/total/pages all optional. Some endpoints return
    # the envelope without pagination metadata (e.g. small static
    # lists) — they must not be forced to fabricate counts.
    r = PaginatedApiResponse[_Item](success=True, message="ok")
    assert r.total is None
    assert r.page is None
    assert r.size is None
    assert r.pages is None
    assert r.data is None


def test_paginated_round_trip_preserves_pages():
    r = PaginatedApiResponse[_Item](
        success=True,
        message="ok",
        data=[],
        total=0,
        page=1,
        size=10,
        pages=0,
    )
    d = r.model_dump()
    assert d["pages"] == 0
    assert d["total"] == 0
    assert d["data"] == []
