"""
Tests for `app/schemas/common.py`.

This is the OTHER ApiResponse module — `app/schemas/response.py`
(covered by wave 6a63) defines the OpenAPI-facing generic envelope;
`common.py` is the older copy used by some endpoints + the
pagination machinery + error response. Both coexist intentionally
(per CLAUDE.md §5 the wire shape must auto-detect — they share the
`success/message/data` keys).

Three groups of invariants pinned:

  - **ApiResponse vs ErrorResponse opposite defaults**:
    ApiResponse.success=True (success is the happy path); ErrorResponse
    .success=False (the wire shape distinguishes errors from successes
    without scrutiny).
  - **PaginationParams bounds**: page ge=1, size ge=1 le=100,
    sort_order regex asc|desc. Same shape as StudentSearchParams
    (wave 6a70). Drift would expose endpoints to OOM (page-size 10k)
    or SQL OFFSET underflow.
  - **PaginatedResponse has_next/has_prev properties**: drive the
    pagination buttons. Edge cases (first page / last page / single
    page) all pinned.

15 cases.
"""

import pytest
from pydantic import ValidationError

from app.schemas.common import (
    ApiResponse,
    EmailTemplateUpdateSchema,
    ErrorResponse,
    PaginatedResponse,
    PaginationParams,
    ValidationErrorDetail,
)

# ─── ApiResponse vs ErrorResponse defaults ─────────────────────────


def test_api_response_success_defaults_true():
    # Pin: success is the happy path. ApiResponse(message="x") must
    # be valid with success=True implicitly.
    r = ApiResponse(message="ok")
    assert r.success is True


def test_error_response_success_defaults_false():
    # Pin: ErrorResponse is the error shape — flipping the default
    # would let buggy endpoints return ErrorResponse with success=True
    # and the frontend would happily render the error as a result.
    r = ErrorResponse(message="bad")
    assert r.success is False


# ─── PaginationParams ───────────────────────────────────────────────


def test_pagination_params_defaults():
    # Pin: page=1, size=20, sort_order="asc" by default. The default
    # 20-item page is what tables render initially.
    p = PaginationParams()
    assert p.page == 1
    assert p.size == 20
    assert p.sort_order == "asc"
    assert p.sort_by is None


def test_pagination_params_page_rejects_zero():
    # Pin: ge=1 — page 0 would compute OFFSET = -size in SQL.
    with pytest.raises(ValidationError):
        PaginationParams(page=0)


def test_pagination_params_size_rejects_zero():
    with pytest.raises(ValidationError):
        PaginationParams(size=0)


def test_pagination_params_size_max_100():
    # Pin: le=100 — prevents OOM on 10k-row responses.
    with pytest.raises(ValidationError):
        PaginationParams(size=101)


def test_pagination_params_sort_order_pattern():
    # Pin: only "asc" or "desc" — drift could allow SQL injection
    # via raw ORDER BY clauses.
    with pytest.raises(ValidationError):
        PaginationParams(sort_order="random()")


def test_pagination_params_sort_order_accepts_desc():
    p = PaginationParams(sort_order="desc")
    assert p.sort_order == "desc"


# ─── PaginatedResponse has_next / has_prev ──────────────────────────


def test_has_next_true_when_not_on_last_page():
    p = PaginatedResponse[int](items=[1, 2], total=20, page=1, size=2, pages=10)
    assert p.has_next is True
    assert p.has_prev is False  # first page


def test_has_prev_true_when_not_on_first_page():
    p = PaginatedResponse[int](items=[1, 2], total=20, page=5, size=2, pages=10)
    assert p.has_next is True
    assert p.has_prev is True


def test_has_next_false_on_last_page():
    p = PaginatedResponse[int](items=[19, 20], total=20, page=10, size=2, pages=10)
    assert p.has_next is False
    assert p.has_prev is True


def test_single_page_neither_next_nor_prev():
    # Pin: edge case — 1 page total, both navigation buttons hidden.
    p = PaginatedResponse[int](items=[1, 2], total=2, page=1, size=20, pages=1)
    assert p.has_next is False
    assert p.has_prev is False


def test_empty_pages_no_next_no_prev():
    # Pin: 0 pages (empty result set) — both False. Some endpoints
    # return pages=0 + page=1; navigation arrows hidden.
    p = PaginatedResponse[int](items=[], total=0, page=1, size=20, pages=0)
    assert p.has_next is False
    assert p.has_prev is False


# ─── ValidationErrorDetail ──────────────────────────────────────────


def test_validation_error_detail_required_fields():
    # Pin: field + message required (audit-trail expects both).
    with pytest.raises(ValidationError):
        ValidationErrorDetail(field="email")  # type: ignore[call-arg]


def test_validation_error_detail_value_defaults_none():
    v = ValidationErrorDetail(field="email", message="bad")
    assert v.value is None


# ─── EmailTemplateUpdateSchema ──────────────────────────────────────


def test_email_template_update_sending_type_defaults_single():
    # Pin: "single" default (one recipient at a time). Flipping to
    # "bulk" would silently change the dispatch mode for new
    # templates.
    s = EmailTemplateUpdateSchema(
        key="welcome",
        subject_template="Hi",
        body_template="Welcome",
    )
    assert s.sending_type == "single"
    assert s.requires_approval is False
