"""
Pure-function tests for `app.core.cache._default`, `_dumps`, `_loads`.

These three helpers encode values into JSON before storing them in
Redis and decode them on read. If a value type can't serialize, the
cache write throws and the calling endpoint either errors or skips
caching — silently losing the perf benefit.

Type fallback chain (in order):
- Pydantic v2 BaseModel → .model_dump()
- Pydantic v1 BaseModel → .dict()
- datetime/date → .isoformat()
- Decimal → str(...) (string-preserving precision)
- set → list

Anything else raises TypeError — pin so a future refactor doesn't
silently start accepting unsupported types.

3 helpers covered (11 cases).
"""

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core.cache import _default, _dumps, _loads

# ─── _default ────────────────────────────────────────────────────────


def test_default_pydantic_v2_uses_model_dump():
    """Anything with .model_dump() → call it (Pydantic v2 path)."""

    class _V2:
        def model_dump(self):
            return {"a": 1, "b": "x"}

    assert _default(_V2()) == {"a": 1, "b": "x"}


def test_default_pydantic_v1_uses_dict():
    """Anything with callable .dict() → call it (Pydantic v1 fallback).
    Must skip if it also has .model_dump (v2 wins)."""

    class _V1:
        def dict(self):
            return {"a": 1}

    assert _default(_V1()) == {"a": 1}


def test_default_datetime_to_isoformat():
    dt = datetime(2025, 3, 15, 14, 30, 0)
    assert _default(dt) == "2025-03-15T14:30:00"


def test_default_date_to_isoformat():
    d = date(2025, 3, 15)
    assert _default(d) == "2025-03-15"


def test_default_decimal_to_string():
    """Decimal → str() not float() — preserve precision in cache."""
    assert _default(Decimal("3.85")) == "3.85"


def test_default_set_to_list():
    """set is not JSON-serialisable; convert to list. Order isn't
    guaranteed since sets are unordered — assert as set after the
    fact."""
    result = _default({1, 2, 3})
    assert isinstance(result, list)
    assert set(result) == {1, 2, 3}


def test_default_unsupported_type_raises():
    """Any object that doesn't match the chain raises TypeError with
    the type name — pin so the cache write fails LOUDLY rather than
    silently dropping data."""

    class _Unknown:
        pass

    with pytest.raises(TypeError, match="not JSON-serialisable"):
        _default(_Unknown())


# ─── _dumps / _loads (round-trip) ────────────────────────────────────


def test_dumps_loads_round_trip_simple_dict():
    """Plain dict round-trips losslessly."""
    obj = {"a": 1, "b": "x", "c": [1, 2, 3], "d": None}
    assert _loads(_dumps(obj)) == obj


def test_dumps_uses_default_for_decimal():
    """Decimals get stringified during dump, so the loaded value is a
    string. Pin: caller must know to coerce back to Decimal on read."""
    blob = _dumps({"price": Decimal("3.85")})
    assert _loads(blob) == {"price": "3.85"}


def test_dumps_uses_compact_separators():
    """Compact ',', ':' separators reduce cache payload size — pin so
    a future refactor doesn't switch to pretty-print default which
    would inflate cache memory."""
    blob = _dumps({"a": 1, "b": 2})
    # Should NOT contain spaces between keys/values.
    assert b", " not in blob
    assert b": " not in blob


def test_dumps_returns_bytes_for_redis_compatibility():
    """Redis stores bytes, not str — pin the bytes return type so a
    refactor to .encode() removal doesn't silently break redis writes."""
    blob = _dumps({"x": 1})
    assert isinstance(blob, bytes)
