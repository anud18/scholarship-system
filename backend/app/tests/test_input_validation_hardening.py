"""Regression tests for the ZAP-driven input-validation hardening.

Covers the three changes that removed the Medium/High findings of the
2026-08-11 authenticated active scan:

1. PostgreSQL data exceptions surface as 422, not 500 (``is_invalid_input_error``).
2. String schemas cap length at the DB column width, so over-length payloads are
   rejected at the boundary instead of by Postgres.
3. Mock SSO defaults to OFF, so dropping the env var cannot expose the
   credential-free account-minting endpoints.
"""

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import DataError, DBAPIError, IntegrityError, OperationalError

from app.core.db_errors import is_constraint_violation_error, is_invalid_input_error
from app.schemas.application_field import ApplicationFieldCreate
from app.schemas.common import SystemSettingSchema


def _asyncpg_data_error(message: str):
    """Build the driver exception asyncpg would raise for a class-22 error."""
    from asyncpg.exceptions import StringDataRightTruncationError

    return StringDataRightTruncationError(message)


def _dbapi_error(orig: BaseException) -> DBAPIError:
    """Wrap a driver exception the way SQLAlchemy's asyncpg dialect does."""
    return DBAPIError("SELECT 1", {}, orig)


class TestIsInvalidInputError:
    def test_sync_data_error_is_invalid_input(self):
        """psycopg2 path: SQLAlchemy already classifies it as DataError."""
        exc = DataError("INSERT ...", {}, Exception("value too long"))
        assert is_invalid_input_error(exc) is True

    def test_asyncpg_data_error_through_cause_chain(self):
        """asyncpg path: the driver error hides behind the dialect wrapper."""
        driver_error = _asyncpg_data_error("value too long for type character varying(100)")
        wrapper = Exception("dialect wrapper")
        wrapper.__cause__ = driver_error
        assert is_invalid_input_error(_dbapi_error(wrapper)) is True

    def test_asyncpg_data_error_as_direct_orig(self):
        driver_error = _asyncpg_data_error('invalid input value for enum semester: "semester"')
        assert is_invalid_input_error(_dbapi_error(driver_error)) is True

    def test_connection_failure_is_not_invalid_input(self):
        """Operational problems must keep their 503, not become a 422."""
        exc = OperationalError("SELECT 1", {}, Exception("connection refused"))
        assert is_invalid_input_error(exc) is False

    def test_unrelated_exception_is_not_invalid_input(self):
        assert is_invalid_input_error(ValueError("boom")) is False

    def test_self_referential_cause_chain_terminates(self):
        """A cyclic __cause__ must not hang the handler."""
        looping = Exception("loop")
        looping.__cause__ = looping
        assert is_invalid_input_error(_dbapi_error(looping)) is False


class TestIsConstraintViolationError:
    def test_sync_integrity_error_is_constraint_violation(self):
        exc = IntegrityError("INSERT ...", {}, Exception("duplicate key value"))
        assert is_constraint_violation_error(exc) is True

    def test_asyncpg_unique_violation_through_cause_chain(self):
        from asyncpg.exceptions import UniqueViolationError

        driver_error = UniqueViolationError("duplicate key value violates unique constraint")
        wrapper = Exception("dialect wrapper")
        wrapper.__cause__ = driver_error
        assert is_constraint_violation_error(_dbapi_error(wrapper)) is True

    def test_data_error_is_not_a_constraint_violation(self):
        """The two classes must stay disjoint so each keeps its own status code."""
        exc = _dbapi_error(_asyncpg_data_error("value too long"))
        assert is_constraint_violation_error(exc) is False
        assert is_invalid_input_error(exc) is True

    def test_connection_failure_is_not_a_constraint_violation(self):
        exc = OperationalError("SELECT 1", {}, Exception("connection refused"))
        assert is_constraint_violation_error(exc) is False


class TestSchemaLengthCaps:
    """ZAP's format-string payload is ~250 chars; these columns are 50-200."""

    def test_field_name_over_column_width_is_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            ApplicationFieldCreate(
                scholarship_type="phd_nstc",
                field_name="x" * 101,
                field_label="label",
            )
        assert "field_name" in str(exc_info.value)

    def test_scholarship_type_over_column_width_is_rejected(self):
        with pytest.raises(ValidationError):
            ApplicationFieldCreate(
                scholarship_type="x" * 51,
                field_name="zap",
                field_label="label",
            )

    def test_values_within_column_width_are_accepted(self):
        field = ApplicationFieldCreate(
            scholarship_type="x" * 50,
            field_name="y" * 100,
            field_label="z" * 200,
        )
        assert field.field_name == "y" * 100

    def test_system_setting_key_over_column_width_is_rejected(self):
        with pytest.raises(ValidationError):
            SystemSettingSchema(key="k" * 101, value="v")

    def test_system_setting_value_is_unbounded_text(self):
        """value is a Text column — long content must still be allowed."""
        setting = SystemSettingSchema(key="k", value="v" * 5000)
        assert len(setting.value) == 5000


class TestMockSsoDefault:
    def test_mock_sso_defaults_to_disabled(self, monkeypatch):
        """Dropping ENABLE_MOCK_SSO must disable, not enable, the dev endpoints."""
        monkeypatch.delenv("ENABLE_MOCK_SSO", raising=False)
        from app.core.config import Settings

        assert Settings(_env_file=None).enable_mock_sso is False
