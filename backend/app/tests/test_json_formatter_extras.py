"""JsonFormatter must surface `extra={...}` fields (issue #1223 A).

The formatter built a fixed four-key dict and never looked at the record's extra
attributes, so every `logger.warning(..., extra={...})` in the codebase (~105 call
sites) emitted a bare message. That silently gutted the SECURITY audit warnings
added for cross-college access — they logged "college user attempted
cross-college application delete" with no user_id, no college codes and no
application_id, i.e. nothing an incident responder could act on.
"""

import json
import logging

import pytest

from app.main import JsonFormatter


def _record(msg="msg", level=logging.WARNING, **extra):
    record = logging.LogRecord(
        name="app.test", level=level, pathname=__file__, lineno=1, msg=msg, args=(), exc_info=None
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_extra_fields_are_emitted():
    out = json.loads(
        JsonFormatter().format(
            _record(
                "SECURITY: college user attempted cross-college application delete",
                user_id=13,
                user_college="C",
                owner_college="E",
                application_id=5,
            )
        )
    )
    assert out["extra"] == {
        "user_id": 13,
        "user_college": "C",
        "owner_college": "E",
        "application_id": 5,
    }


def test_standard_fields_still_present():
    out = json.loads(JsonFormatter().format(_record("hello")))
    assert out["message"] == "hello"
    assert out["level"] == "WARNING"
    assert out["name"] == "app.test"
    assert "timestamp" in out


def test_no_extra_key_when_none_supplied():
    """A plain log line must not grow a noisy empty object."""
    assert "extra" not in json.loads(JsonFormatter().format(_record("plain")))


def test_caller_key_cannot_clobber_a_standard_field():
    """Nesting under `extra` is what guarantees this — a flat merge would let a
    caller key overwrite `level`/`message`/`name` and corrupt log parsing.

    `message` and `levelname` are reserved LogRecord names (Python's logging
    rejects them in `extra=` anyway), so they are filtered out entirely rather
    than surfaced — either way the real values survive.
    """
    out = json.loads(JsonFormatter().format(_record("real message", level=logging.ERROR, message="spoofed")))
    assert out["message"] == "real message"
    assert out["level"] == "ERROR"
    assert "message" not in out.get("extra", {})

    # A NON-reserved caller key is surfaced, and still cannot reach the top level.
    out2 = json.loads(JsonFormatter().format(_record("m", timestamp="spoofed-ts", user_id=7)))
    assert out2["extra"] == {"timestamp": "spoofed-ts", "user_id": 7}
    assert out2["timestamp"] != "spoofed-ts"


def test_non_serialisable_value_degrades_instead_of_raising():
    """A raise inside the logging path would lose the record entirely — worse than
    an imprecise value, especially for a SECURITY warning."""

    class Opaque:
        def __repr__(self):
            return "<opaque>"

    out = json.loads(JsonFormatter().format(_record("m", thing=Opaque())))
    assert out["extra"]["thing"] == "<opaque>"


def test_exception_info_still_captured():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord(
            name="app.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="failed",
            args=(),
            exc_info=sys.exc_info(),
        )
    out = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in out["exception"]


@pytest.mark.parametrize("reserved", ["name", "levelname", "pathname", "lineno", "msg", "args", "exc_info"])
def test_reserved_logrecord_attributes_are_not_leaked_as_extras(reserved):
    """Internal LogRecord plumbing must not show up as if the caller sent it."""
    out = json.loads(JsonFormatter().format(_record("m", user_id=1)))
    assert reserved not in out.get("extra", {})
