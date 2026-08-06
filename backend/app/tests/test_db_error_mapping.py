"""Regression tests for db_error_mapping.

Every case here corresponds to a driver error that the 2026-08-06 authenticated
ZAP active scan turned into an HTTP 500. See docs/security/zap-active-2026-08-06/.
"""

import pytest

from app.core.db_error_mapping import map_db_exception


class _FakeDriverError(Exception):
    """Stands in for an asyncpg exception (which carries `sqlstate`)."""

    def __init__(self, sqlstate):
        super().__init__(f"driver error {sqlstate}")
        self.sqlstate = sqlstate


class _FakePsycopgError(Exception):
    """Stands in for a psycopg2 exception (which spells it `pgcode`)."""

    def __init__(self, pgcode):
        super().__init__(f"driver error {pgcode}")
        self.pgcode = pgcode


class _FakeWrapper(Exception):
    """Stands in for sqlalchemy.exc.DBAPIError, which exposes `.orig`."""

    def __init__(self, orig):
        super().__init__("wrapped")
        self.orig = orig


@pytest.mark.parametrize(
    "sqlstate,expected_status",
    [
        ("22P02", 400),  # InvalidTextRepresentation - bad enum/int literal
        ("22001", 400),  # StringDataRightTruncation - value longer than column
        ("22021", 400),  # CharacterNotInRepertoire - NUL byte in text
        ("22000", 400),  # generic data exception
        ("23505", 409),  # UniqueViolation
        ("23503", 409),  # ForeignKeyViolation
        ("23502", 409),  # NotNullViolation
    ],
)
def test_client_input_errors_map_to_4xx(sqlstate, expected_status):
    """Caller-input errors must not surface as 500."""
    result = map_db_exception(_FakeWrapper(_FakeDriverError(sqlstate)))
    assert result is not None, f"{sqlstate} should be mapped"
    assert result[0] == expected_status


@pytest.mark.parametrize(
    "sqlstate",
    [
        "08006",  # connection_failure
        "53300",  # too_many_connections
        "57014",  # query_canceled
        "42P01",  # undefined_table - our bug, not the caller's
        "XX000",  # internal_error
    ],
)
def test_server_side_faults_are_not_mapped(sqlstate):
    """Genuine server faults must keep returning 5xx, not be laundered into 4xx."""
    assert map_db_exception(_FakeWrapper(_FakeDriverError(sqlstate))) is None


def test_psycopg_pgcode_is_read():
    """The sync engine's driver spells the code differently."""
    result = map_db_exception(_FakeWrapper(_FakePsycopgError("23505")))
    assert result is not None
    assert result[0] == 409


def test_bare_driver_exception_without_wrapper():
    """A driver error raised outside a SQLAlchemy wrapper still resolves."""
    result = map_db_exception(_FakeDriverError("22P02"))
    assert result is not None
    assert result[0] == 400


def test_unrelated_exception_returns_none():
    assert map_db_exception(ValueError("nothing to do with the database")) is None


def test_missing_sqlstate_returns_none():
    assert map_db_exception(_FakeWrapper(Exception("no code attribute"))) is None


def test_message_does_not_leak_driver_text():
    """The user-facing message must never echo the driver's error string.

    Driver text can contain column names, SQL fragments, or the offending value.
    """
    driver = _FakeDriverError("23505")
    driver.args = ('duplicate key value violates unique constraint "uq_secret_col"',)
    result = map_db_exception(_FakeWrapper(driver))
    assert result is not None
    _, message = result
    assert "uq_secret_col" not in message
    assert "duplicate key" not in message.lower()
