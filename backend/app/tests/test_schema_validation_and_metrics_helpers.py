"""
Pure-helper tests for `app.core.schema_validation` and
`app.core.metrics.normalize_endpoint`.

`serialize_value` is the single coercion point for API response data —
enums → `.value`, datetimes → ISO 8601, Decimals → float. A regression
here would either ship raw enum objects to the JSON serializer
(TypeError at FastAPI response time) or lose precision on monetary
values.

`validate_response_data` formats Pydantic validation errors for the
schema-drift debug helper. The structured format (`Field 'x -> y': msg`)
is consumed by Sentry alerting — a format change would break alert
routing.

`normalize_endpoint` collapses path parameters to `:id` for Prometheus
metrics cardinality control. Without it, every `/applications/123`
becomes a separate label value → Prometheus storage runs out of memory.
Static paths (`/health`, `/metrics`) must NOT be collapsed (oncall
relies on distinct labels for them).

3 helpers covered (18 cases). Pure, no I/O.
"""

import enum
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import BaseModel, Field

from app.core.metrics import normalize_endpoint
from app.core.schema_validation import (
    SchemaValidationError,
    serialize_value,
    validate_response_data,
)

# ─── serialize_value (Pydantic-friendly coercion) ─────────────────────


def test_serialize_none_passes_through():
    assert serialize_value(None) is None


def test_serialize_enum_returns_value_string():
    """Pin: enum → .value (string), not the enum object itself.
    Otherwise FastAPI's JSON encoder would crash on the enum repr."""

    class Status(enum.Enum):
        ACTIVE = "active"
        ARCHIVED = "archived"

    assert serialize_value(Status.ACTIVE) == "active"
    assert serialize_value(Status.ARCHIVED) == "archived"


def test_serialize_datetime_iso8601():
    """Pin: datetime → ISO 8601 string (includes timezone). The frontend
    expects this format for date parsing."""
    dt = datetime(2024, 6, 1, 12, 30, 45, tzinfo=timezone.utc)
    result = serialize_value(dt)
    assert result == "2024-06-01T12:30:45+00:00"


def test_serialize_decimal_to_float():
    """Pin: Decimal → float. Precision loss is documented (JSON has no
    decimal type). For monetary values stored as Decimal, the conversion
    preserves enough precision for display but downstream code MUST
    re-fetch from DB for arithmetic."""
    assert serialize_value(Decimal("123.45")) == 123.45
    assert serialize_value(Decimal("0")) == 0.0


def test_serialize_object_with_isoformat_uses_it():
    """Pin: anything with `.isoformat()` (date objects, custom types)
    uses that. Defensive — covers date.date instances."""
    from datetime import date

    assert serialize_value(date(2024, 6, 1)) == "2024-06-01"


def test_serialize_primitive_passthrough():
    """Pin: int, str, bool, float, list, dict → unchanged."""
    assert serialize_value(42) == 42
    assert serialize_value("hello") == "hello"
    assert serialize_value(True) is True
    assert serialize_value([1, 2, 3]) == [1, 2, 3]
    assert serialize_value({"k": "v"}) == {"k": "v"}


# ─── validate_response_data (Pydantic wrapper) ───────────────────────


class _SampleSchema(BaseModel):
    id: int
    name: str = Field(..., min_length=1)


def test_validate_single_dict_passes():
    assert validate_response_data({"id": 1, "name": "ok"}, _SampleSchema) is True


def test_validate_list_of_dicts_all_must_pass():
    """Pin: each item validated separately. If ANY item fails, the
    whole call raises — defends against partial-success leakage."""
    data = [{"id": 1, "name": "ok"}, {"id": 2, "name": "also"}]
    assert validate_response_data(data, _SampleSchema) is True


def test_validate_raises_schema_validation_error_with_formatted_message():
    """Pin: SchemaValidationError raised with formatted message
    'Field 'x -> y': msg'. Sentry alert routing depends on this format
    to extract the field path."""
    with pytest.raises(SchemaValidationError) as exc:
        validate_response_data({"id": "not_an_int", "name": ""}, _SampleSchema)
    msg = str(exc.value)
    assert "Schema validation failed for _SampleSchema" in msg
    # Field path is present in the formatted error
    assert "Field '" in msg


def test_validate_list_with_one_bad_item_raises():
    data = [{"id": 1, "name": "ok"}, {"id": "bad", "name": ""}]
    with pytest.raises(SchemaValidationError):
        validate_response_data(data, _SampleSchema)


# ─── normalize_endpoint (Prometheus cardinality) ──────────────────────


def test_normalize_numeric_id_collapsed():
    """Pin: /applications/123 → /applications/:id.
    Without this, every application creates a distinct Prometheus label."""
    assert normalize_endpoint("/api/v1/applications/123") == "/api/v1/applications/:id"


def test_normalize_uuid_collapsed():
    """Pin: UUIDs collapsed (case-insensitive)."""
    assert normalize_endpoint("/api/v1/scholarships/550e8400-e29b-41d4-a716-446655440000") == "/api/v1/scholarships/:id"
    # Upper-case UUID also normalized (re.IGNORECASE)
    assert normalize_endpoint("/api/v1/scholarships/550E8400-E29B-41D4-A716-446655440000") == "/api/v1/scholarships/:id"


def test_normalize_long_alphanumeric_collapsed():
    """Pin: alphanumeric segments ≥ 8 chars treated as IDs (e.g.,
    Mongo-style ObjectIds, application_code like APP-113-1-00001)."""
    assert normalize_endpoint("/api/v1/applications/abcdef12345") == "/api/v1/applications/:id"


def test_normalize_short_alphanumeric_segments_preserved():
    """Pin: short segments (< 8 chars) treated as route names, NOT IDs.
    Otherwise '/users/me' would collapse to '/users/:id' and lose
    semantic meaning."""
    assert normalize_endpoint("/users/me") == "/users/me"
    assert normalize_endpoint("/api/v1/health") == "/api/v1/health"


def test_normalize_static_paths_preserved():
    """Pin: /health, /metrics, /docs, /openapi.json never normalized.
    Oncall pages on health checks rely on the literal path label."""
    for static in ("/health", "/metrics", "/docs", "/openapi.json"):
        assert normalize_endpoint(static) == static


def test_normalize_already_normalized_short_circuits():
    """Pin: if ':id' is already in the path, no further processing.
    Defensive against double-normalization breaking the path further."""
    assert normalize_endpoint("/api/v1/applications/:id/files") == "/api/v1/applications/:id/files"


def test_normalize_multiple_ids_in_path():
    """Pin: /users/123/applications/456 → /users/:id/applications/:id.
    Both numeric IDs collapsed in one pass."""
    assert normalize_endpoint("/users/123/applications/456") == "/users/:id/applications/:id"


def test_normalize_mixed_numeric_and_uuid():
    """Pin: mixed-ID paths handled correctly."""
    result = normalize_endpoint("/users/550e8400-e29b-41d4-a716-446655440000/applications/123")
    assert result == "/users/:id/applications/:id"
