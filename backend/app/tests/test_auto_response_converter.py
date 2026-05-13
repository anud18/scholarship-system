"""
Pure-function tests for `app.core.auto_response_converter`.

This module is the bridge between SQLAlchemy ORM rows and Pydantic
response models — it serializes raw values (enums, Decimals, lists)
into JSON-friendly types, and fills in defaults for fields that the
ORM row doesn't have.

A regression here either:
- Crashes API responses (serialization error on Decimal/Enum).
- Silently fills wrong defaults (e.g., shows passed=[] when source had
  errors), leaking incorrect data to the frontend.

2 helpers covered (16 cases):
- `serialize_value`            : enum/Decimal/list/dict/None coercion
- `get_default_value_for_field`: name-based + type-based defaults
"""

import enum
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import List

import pytest

from app.core.auto_response_converter import get_default_value_for_field, serialize_value

# ─── serialize_value ─────────────────────────────────────────────────


def test_serialize_none_is_none():
    """None passes through — Pydantic accepts None for Optional fields."""
    assert serialize_value(None) is None


def test_serialize_enum_returns_value():
    """Enum.value (e.g., 'first') is what JSON consumers expect, NOT
    the Enum object itself."""

    class Sem(enum.Enum):
        FIRST = "first"
        SECOND = "second"

    assert serialize_value(Sem.FIRST) == "first"


def test_serialize_decimal_to_float():
    """Decimal → float for JSON serialization. Note: loses precision
    on long decimals, but Pydantic models in this codebase store
    money/GPA as float, so the conversion is intentional."""
    assert serialize_value(Decimal("3.85")) == 3.85
    assert isinstance(serialize_value(Decimal("3.85")), float)


def test_serialize_datetime_passthrough():
    """datetime is passed through — Pydantic handles ISO serialization
    downstream. Pin so we don't accidentally convert to string here
    and double-serialize."""
    dt = datetime(2025, 3, 15)
    assert serialize_value(dt) is dt


def test_serialize_list_recurses():
    """Lists serialize element-by-element — enum inside list becomes
    its value."""

    class Status(enum.Enum):
        OK = "ok"
        FAIL = "fail"

    result = serialize_value([Status.OK, Decimal("1.5"), None, "raw"])
    assert result == ["ok", 1.5, None, "raw"]


def test_serialize_dict_recurses():
    """Dicts serialize value-by-value, preserving keys."""

    class Color(enum.Enum):
        RED = "red"

    result = serialize_value({"color": Color.RED, "ratio": Decimal("0.5"), "nested": {"x": Color.RED}})
    assert result == {"color": "red", "ratio": 0.5, "nested": {"x": "red"}}


def test_serialize_primitive_passthrough():
    """str/int/bool unchanged."""
    assert serialize_value("hi") == "hi"
    assert serialize_value(42) == 42
    assert serialize_value(True) is True


def test_serialize_object_with_isoformat_passthrough():
    """Objects with .isoformat() (like date) are passed through —
    Pydantic handles them. Pin so we don't accidentally strigify
    here when Pydantic expects a date."""

    class _Faux:
        def isoformat(self):
            return "2025-03-15"

    obj = _Faux()
    assert serialize_value(obj) is obj


# ─── get_default_value_for_field ─────────────────────────────────────


def test_default_eligible_sub_types_reads_sub_type_list():
    """Special-case: eligible_sub_types defaults to source.sub_type_list,
    falling back to ['general']."""
    result = get_default_value_for_field("eligible_sub_types", None, {"sub_type_list": ["nstc", "moe_1w"]})
    assert result == ["nstc", "moe_1w"]


def test_default_eligible_sub_types_fallback_to_general():
    """Missing sub_type_list ⇒ ['general'] (the canonical default)."""
    assert get_default_value_for_field("eligible_sub_types", None, {}) == ["general"]


def test_default_passed_warnings_errors_are_empty_lists():
    """The triplet of eligibility-result list fields default to [] —
    pin so the frontend never gets undefined for these (depends on
    .map() / .length over them)."""
    for field in ("passed", "warnings", "errors"):
        assert get_default_value_for_field(field, None, {}) == []


def test_default_name_en_falls_back_to_name():
    """If the response model expects name_en but source only has name
    (common in zh-only data), fall back to name."""
    assert get_default_value_for_field("name_en", None, {"name": "Alice"}) == "Alice"
    # Missing both → '' (not None — Pydantic str field doesn't accept None).
    assert get_default_value_for_field("name_en", None, {}) == ""


def test_default_uses_field_info_default():
    """Pydantic field's .default is used when set. Pin precedence:
    name_en special case wins over field_info, but other fields use
    field_info if set."""

    field_info = SimpleNamespace(default="DEFAULT_VAL")
    assert get_default_value_for_field("some_field", field_info, {}) == "DEFAULT_VAL"


def test_default_type_based_str_int_bool_list_dict():
    """When neither name special-case nor field_info default applies,
    fall back to type-based defaults: '' / 0 / False / [] / {}."""

    def make_info(annotation):
        return SimpleNamespace(default=None, annotation=annotation)

    assert get_default_value_for_field("x", make_info(str), {}) == ""
    assert get_default_value_for_field("x", make_info(int), {}) == 0
    assert get_default_value_for_field("x", make_info(bool), {}) is False
    assert get_default_value_for_field("x", make_info(list), {}) == []
    assert get_default_value_for_field("x", make_info(dict), {}) == {}


def test_default_generic_list_origin_returns_empty_list():
    """Generic types like List[int] have origin=list — also default to []."""
    field_info = SimpleNamespace(default=None, annotation=List[int])
    assert get_default_value_for_field("x", field_info, {}) == []


def test_default_unknown_type_returns_none():
    """No annotation, no field default, no special case → None.
    Pydantic Optional fields accept this."""
    field_info = SimpleNamespace(default=None, annotation=None)
    assert get_default_value_for_field("unknown", field_info, {}) is None
