"""
Tests for `serialize_value` + `auto_convert_response` decorator on
`app.core.auto_response_converter`.

Wave 6rr covered convert_to_response_model + sqlalchemy_to_dict +
create_response_instance + get_default_value_for_field +
auto_convert_and_validate. This wave fills the two remaining
helpers:

  - **serialize_value(value)**: Recursive serializer used to turn
    SQLAlchemy column values into Pydantic-friendly shapes.
    Critical because:
      * Enums → .value (the wire shape) — frontend will get
        UPPERCASE enum names instead of lowercase values otherwise
      * Decimal → float (Pydantic v2 sometimes refuses bare
        Decimals on response coercion)
      * Recurses through list / dict — pin so nested student_data
        JSON gets enum-flattened all the way down

  - **auto_convert_response(response_model)**: Decorator factory
    used by FastAPI endpoints. Pin:
      * None passthrough (endpoints can return None for 204 cases)
      * Calls convert_to_response_model on non-None results
      * Preserves async function semantics via @wraps

13 cases.
"""

import enum
from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import BaseModel

from app.core.auto_response_converter import auto_convert_response, serialize_value


class _Status(enum.Enum):
    SUBMITTED = "submitted"
    APPROVED = "approved"


# ─── serialize_value ─────────────────────────────────────────────────


def test_serialize_none_returns_none():
    # Pin: None passes through unchanged. JSON `null` is the wire
    # representation Pydantic expects.
    assert serialize_value(None) is None


def test_serialize_enum_returns_value_not_name():
    # Pin: returns .value ("submitted"), not the name
    # ("SUBMITTED"). The CLAUDE.md §4 wire contract is lowercase
    # values; a regression to name would break frontend enum
    # mapping.
    assert serialize_value(_Status.SUBMITTED) == "submitted"


def test_serialize_decimal_returns_float():
    # Pin: Decimal → float. Pydantic v2 sometimes refuses bare
    # Decimal in response models because JSON has no Decimal type.
    # Pin so a refactor doesn't accidentally drop the float
    # coercion.
    out = serialize_value(Decimal("12.50"))
    assert isinstance(out, float)
    assert out == 12.5


def test_serialize_datetime_passthrough():
    # Pin: datetime objects pass through unchanged (Pydantic v2
    # serializes datetime to ISO 8601 itself via its own
    # JSON encoder).
    dt = datetime(2026, 5, 13, 10, 30, 0)
    assert serialize_value(dt) is dt


def test_serialize_list_recurses():
    # Pin: lists are recursively serialized. Each element is
    # transformed independently — pinned so a refactor doesn't
    # accidentally drop the recursion (would silently leave enum
    # objects in the response list).
    out = serialize_value([_Status.SUBMITTED, _Status.APPROVED, "x", None])
    assert out == ["submitted", "approved", "x", None]


def test_serialize_dict_recurses():
    # Pin: dicts recurse on values (keys passed through). This is
    # how the student_data JSON gets enum-flattened.
    out = serialize_value({"status": _Status.SUBMITTED, "amount": Decimal("5.0")})
    assert out == {"status": "submitted", "amount": 5.0}


def test_serialize_nested_list_in_dict():
    # Pin: nested structure full-depth recursion.
    out = serialize_value({"statuses": [_Status.SUBMITTED, _Status.APPROVED]})
    assert out == {"statuses": ["submitted", "approved"]}


def test_serialize_primitive_passthrough():
    # Pin: int / str / float / bool unchanged.
    assert serialize_value(42) == 42
    assert serialize_value("hello") == "hello"
    assert serialize_value(3.14) == 3.14
    assert serialize_value(True) is True
    assert serialize_value(False) is False


def test_serialize_empty_collections():
    # Pin: empty list / dict return empty list / dict (not None).
    assert serialize_value([]) == []
    assert serialize_value({}) == {}


# ─── auto_convert_response decorator ────────────────────────────────


class _Item(BaseModel):
    id: int
    name: str


@pytest.mark.asyncio
async def test_decorator_passes_none_through_unchanged():
    # Pin: None result skips conversion. Endpoints returning None
    # (e.g., 204 No Content delete handlers) must not trigger an
    # attempt to coerce None into an _Item — that would raise.
    @auto_convert_response(_Item)
    async def handler():
        return None

    result = await handler()
    assert result is None


@pytest.mark.asyncio
async def test_decorator_converts_dict_result_to_model():
    # Pin: dict result is fed through convert_to_response_model
    # and returned as an _Item instance.
    @auto_convert_response(_Item)
    async def handler():
        return {"id": 1, "name": "x"}

    result = await handler()
    assert isinstance(result, _Item)
    assert result.id == 1
    assert result.name == "x"


@pytest.mark.asyncio
async def test_decorator_preserves_async_function_name():
    # Pin: @wraps preserves __name__ so logging / introspection /
    # FastAPI route-name detection still works.
    @auto_convert_response(_Item)
    async def my_handler():
        return None

    assert my_handler.__name__ == "my_handler"


@pytest.mark.asyncio
async def test_decorator_passes_args_kwargs():
    # Pin: wrapped function gets positional + keyword args
    # transparently. FastAPI dependency injection relies on this.
    @auto_convert_response(_Item)
    async def handler(a, b, c=None):
        return {"id": a + b, "name": c or "default"}

    result = await handler(1, 2, c="custom")
    assert result.id == 3
    assert result.name == "custom"
