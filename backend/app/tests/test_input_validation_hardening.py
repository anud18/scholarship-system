"""Regression tests for the ZAP-driven input-validation hardening.

Covers the three changes that removed the Medium/High findings of the
2026-08-11 authenticated active scan:

1. Database errors are classified by SQLSTATE, so an unrepresentable value
   surfaces as 422 and a genuine conflict as 409 — while a broken server-side
   invariant (not-null, check, division-by-zero) stays a 500.
2. String schemas cap length at the DB column width, so over-length payloads are
   rejected at the boundary instead of by Postgres.
3. Mock SSO defaults to OFF, so dropping the env var cannot expose the
   credential-free account-minting endpoints.
"""

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError

from app.core.db_errors import is_constraint_violation_error, is_invalid_input_error, sqlstate_of
from app.schemas.application_field import ApplicationDocumentCreate, ApplicationFieldCreate
from app.schemas.common import SystemSettingSchema


class _Psycopg2Error(Exception):
    """psycopg2 exposes the SQLSTATE as .pgcode; asyncpg as .sqlstate."""

    def __init__(self, pgcode: str):
        super().__init__(f"psycopg2 error {pgcode}")
        self.pgcode = pgcode


def _asyncpg_error(name: str):
    """Build the driver exception asyncpg would raise, by class name."""
    import asyncpg.exceptions

    return getattr(asyncpg.exceptions, name)("driver error")


def _dbapi_error(orig: BaseException) -> DBAPIError:
    """Wrap a driver exception the way SQLAlchemy's asyncpg dialect does."""
    return DBAPIError("SELECT 1", {}, orig)


def _wrapped(orig: BaseException) -> DBAPIError:
    """asyncpg path: the driver error hides one level down, under the wrapper."""
    wrapper = Exception("dialect wrapper")
    wrapper.__cause__ = orig
    return _dbapi_error(wrapper)


class TestSqlstateExtraction:
    def test_reads_sqlstate_from_asyncpg_through_cause_chain(self):
        assert sqlstate_of(_wrapped(_asyncpg_error("StringDataRightTruncationError"))) == "22001"

    def test_reads_sqlstate_from_direct_orig(self):
        assert sqlstate_of(_dbapi_error(_asyncpg_error("UniqueViolationError"))) == "23505"

    def test_reads_pgcode_from_psycopg2(self):
        assert sqlstate_of(_dbapi_error(_Psycopg2Error("22001"))) == "22001"

    def test_non_dbapi_exception_has_no_sqlstate(self):
        assert sqlstate_of(ValueError("boom")) is None

    def test_self_referential_cause_chain_terminates(self):
        """A cyclic __cause__ must not hang the handler."""
        looping = Exception("loop")
        looping.__cause__ = looping
        assert sqlstate_of(_dbapi_error(looping)) is None


class TestIsInvalidInputError:
    @pytest.mark.parametrize(
        "driver_error_name",
        [
            "StringDataRightTruncationError",  # 22001 — value longer than the column
            "InvalidTextRepresentationError",  # 22P02 — unknown enum label
            "NumericValueOutOfRangeError",  # 22003
            "InvalidDatetimeFormatError",  # 22007
        ],
    )
    def test_unrepresentable_value_is_invalid_input(self, driver_error_name):
        assert is_invalid_input_error(_wrapped(_asyncpg_error(driver_error_name))) is True

    def test_psycopg2_truncation_is_invalid_input(self):
        assert is_invalid_input_error(_dbapi_error(_Psycopg2Error("22001"))) is True

    def test_division_by_zero_stays_a_server_error(self):
        """Server-side arithmetic is not the client's fault — must remain a 500."""
        assert is_invalid_input_error(_wrapped(_asyncpg_error("DivisionByZeroError"))) is False

    def test_connection_failure_is_not_invalid_input(self):
        """Operational problems must keep their 503, not become a 422."""
        exc = OperationalError("SELECT 1", {}, _Psycopg2Error("08006"))
        assert is_invalid_input_error(exc) is False

    def test_unrelated_exception_is_not_invalid_input(self):
        assert is_invalid_input_error(ValueError("boom")) is False


class TestIsConstraintViolationError:
    @pytest.mark.parametrize(
        "driver_error_name",
        [
            "UniqueViolationError",  # 23505
            "ForeignKeyViolationError",  # 23503
        ],
    )
    def test_genuine_conflict_is_a_constraint_violation(self, driver_error_name):
        assert is_constraint_violation_error(_wrapped(_asyncpg_error(driver_error_name))) is True

    def test_psycopg2_unique_violation_is_a_constraint_violation(self):
        exc = IntegrityError("INSERT ...", {}, _Psycopg2Error("23505"))
        assert is_constraint_violation_error(exc) is True

    @pytest.mark.parametrize(
        "driver_error_name",
        [
            "NotNullViolationError",  # 23502
            "CheckViolationError",  # 23514
        ],
    )
    def test_broken_invariant_stays_a_server_error(self, driver_error_name):
        """A service that omits a NOT NULL column is a backend bug, not a conflict:
        answering 409 would lie to the client and hide it from 5xx alerting."""
        exc = _wrapped(_asyncpg_error(driver_error_name))
        assert is_constraint_violation_error(exc) is False
        assert is_invalid_input_error(exc) is False

    def test_data_error_is_not_a_constraint_violation(self):
        """The two classes must stay disjoint so each keeps its own status code."""
        exc = _wrapped(_asyncpg_error("StringDataRightTruncationError"))
        assert is_constraint_violation_error(exc) is False
        assert is_invalid_input_error(exc) is True

    def test_connection_failure_is_not_a_constraint_violation(self):
        exc = OperationalError("SELECT 1", {}, _Psycopg2Error("08006"))
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

    def test_document_name_over_column_width_is_rejected(self):
        """The document schemas share the router the field schemas were capped in."""
        with pytest.raises(ValidationError):
            ApplicationDocumentCreate(scholarship_type="phd_nstc", document_name="d" * 201)

    def test_document_description_is_unbounded_text(self):
        doc = ApplicationDocumentCreate(
            scholarship_type="phd_nstc",
            document_name="成績單",
            description="x" * 5000,
        )
        assert len(doc.description) == 5000


class TestSystemSettingKeyQueryCap:
    """GET /admin/system-setting echoes a missing key back through
    SystemSettingSchema, so the query param must be capped at the same width or
    response construction raises inside the handler and answers 500."""

    async def _get(self, key: str) -> int:
        from httpx import ASGITransport, AsyncClient

        from app.core.security import require_admin
        from app.db.deps import get_db
        from app.main import app

        async def _no_db():
            yield None

        app.dependency_overrides[get_db] = _no_db
        app.dependency_overrides[require_admin] = lambda: None
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/v1/admin/system-setting", params={"key": key})
            return response.status_code
        finally:
            app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_over_length_key_is_rejected_before_the_handler(self):
        assert await self._get("k" * 101) == 422


class TestMockSsoDefault:
    def test_mock_sso_defaults_to_disabled(self):
        """Dropping ENABLE_MOCK_SSO must disable, not enable, the dev endpoints.

        Asserts the declared default rather than instantiating Settings, which
        would need the whole required-env set and is sensitive to whatever the
        preceding test left in os.environ.
        """
        from app.core.config import Settings

        assert Settings.model_fields["enable_mock_sso"].default is False
