import enum
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict

import pytest
from pydantic import BaseModel, Field

from app.core.schema_validation import (
    SchemaValidationError,
    convert_sqlalchemy_to_response_dict,
    create_response_converter,
    debug_response_schema_mismatch,
    serialize_value,
    validate_response_data,
    validate_response_schema,
)


class DummyEnum(enum.Enum):
    ACTIVE = "active"


class DummyColumn:
    def __init__(self, name: str):
        self.name = name


class DummyTable:
    def __init__(self, columns):
        self.columns = columns


class DummyModel:
    def __init__(self, extra: Dict[str, Any] | None = None):
        self.__table__ = DummyTable(
            [
                DummyColumn("identifier"),
                DummyColumn("created_at"),
                DummyColumn("amount"),
                DummyColumn("status"),
            ]
        )
        self.identifier = 101
        self.created_at = datetime(2024, 2, 1, tzinfo=timezone.utc)
        self.amount = Decimal("42.00")
        self.status = DummyEnum.ACTIVE
        self.notes = [DummyEnum.ACTIVE, Decimal("1.5")]
        if extra:
            for key, value in extra.items():
                setattr(self, key, value)


class SampleSchema(BaseModel):
    identifier: int
    status: str


class ExtendedSchema(BaseModel):
    id: int
    status: str
    amount: float
    created_at: datetime
    notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def test_validate_response_data_accepts_valid_payload():
    payload = [{"identifier": 1, "status": "approved"}]
    assert validate_response_data(payload, SampleSchema)


def test_validate_response_data_reraises_validation_errors():
    payload = {"identifier": "bad"}
    with pytest.raises(SchemaValidationError) as exc:
        validate_response_data(payload, SampleSchema)

    assert "Schema validation failed" in str(exc.value)


def test_convert_sqlalchemy_to_response_dict_serializes_supported_values():
    dummy = DummyModel(extra={"ignored": "value"})
    converted = convert_sqlalchemy_to_response_dict(dummy)

    assert converted["identifier"] == 101
    assert converted["amount"] == pytest.approx(42.0)
    assert converted["status"] == DummyEnum.ACTIVE.value
    assert converted["created_at"] == dummy.created_at.isoformat()

    without_status = convert_sqlalchemy_to_response_dict(dummy, exclude_fields=["status"])
    assert "status" not in without_status


def test_create_response_converter_applies_mapping_and_defaults():
    dummy = DummyModel()
    converter = create_response_converter(
        DummyModel,
        ExtendedSchema,
        field_mapping={"identifier": "id"},
        custom_converters={"status": lambda value: value.upper()},
    )

    result = converter(dummy)

    assert isinstance(result, ExtendedSchema)
    assert result.id == 101
    assert result.status == DummyEnum.ACTIVE.value.upper()
    assert result.notes == []
    assert result.warnings == []


def test_debug_response_schema_mismatch_logs_details(caplog):
    with caplog.at_level("ERROR"):
        debug_response_schema_mismatch({"id": 5}, ExtendedSchema)

    assert "Missing fields" in caplog.text
    assert "Schema validation failed" in caplog.text


@pytest.fixture
def debug_settings(monkeypatch):
    from app.core.config import settings as config_settings

    monkeypatch.setattr(config_settings, "debug", True)
    monkeypatch.setattr(config_settings, "environment", "development")


@pytest.mark.asyncio
async def test_validate_response_schema_decorator_allows_valid_payload(debug_settings):
    @validate_response_schema(ExtendedSchema)
    async def endpoint():
        return {
            "id": 3,
            "status": "approved",
            "amount": 1.5,
            "created_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
        }

    response = await endpoint()
    assert response["id"] == 3


@pytest.mark.asyncio
async def test_validate_response_schema_decorator_raises_on_invalid_payload(debug_settings):
    @validate_response_schema(ExtendedSchema)
    async def endpoint():
        return {"id": 3}

    with pytest.raises(SchemaValidationError):
        await endpoint()


def test_serialize_value_handles_decimal_and_enum():
    assert serialize_value(Decimal("2.5")) == pytest.approx(2.5)
    assert serialize_value(DummyEnum.ACTIVE) == "active"
