import enum
from datetime import datetime, timezone
from decimal import Decimal
from typing import List

import pytest
from pydantic import BaseModel, Field

import app.core.auto_response_converter as converter_module
from app.core.auto_response_converter import (
    auto_convert_and_validate,
    convert_to_response_model,
    create_response_instance,
    get_default_value_for_field,
    sqlalchemy_to_dict,
)


class DummyEnum(enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class DummyColumn:
    def __init__(self, name: str):
        self.name = name


class DummyTable:
    def __init__(self, columns):
        self.columns = columns


class DummyModel:
    def __init__(self):
        self.__table__ = DummyTable(
            [
                DummyColumn("identifier"),
                DummyColumn("amount"),
                DummyColumn("created_at"),
                DummyColumn("status"),
            ]
        )
        self.identifier = 42
        self.amount = Decimal("12.50")
        self.created_at = datetime(2024, 1, 2, tzinfo=timezone.utc)
        self.status = DummyEnum.ACTIVE
        self.notes = [DummyEnum.INACTIVE, Decimal("1.25")]
        self.metadata = {"score": Decimal("0.5")}
        self.ignore_me = lambda: None  # pragma: no cover - accessed via dir but filtered


class ExampleResponse(BaseModel):
    identifier: int
    amount: float | None = None
    created_at: datetime | None = None
    status: str = ""
    eligible_sub_types: List[str] = Field(default_factory=list)
    passed: List[str] = Field(default_factory=list)
    name_en: str = ""
    optional_flag: bool = False


def test_convert_to_response_model_handles_typing_list():
    raw = [{"identifier": 1, "status": "ok"}]
    result = convert_to_response_model(raw, List[ExampleResponse])

    assert isinstance(result, list)
    assert isinstance(result[0], ExampleResponse)
    assert result[0].identifier == 1


def test_convert_to_response_model_wraps_single_item_list_return():
    raw = [{"identifier": 5, "status": "queued"}]
    result = convert_to_response_model(raw, ExampleResponse)

    assert isinstance(result, list)
    assert result[0].status == "queued"


def test_sqlalchemy_to_dict_serializes_supported_types():
    dummy = DummyModel()
    data = sqlalchemy_to_dict(dummy)

    assert data["identifier"] == 42
    assert data["amount"] == pytest.approx(12.5)
    assert data["status"] == DummyEnum.ACTIVE.value
    # Nested values are serialized recursively
    assert data["metadata"] == {"score": pytest.approx(0.5)}
    assert data["notes"][0] == DummyEnum.INACTIVE.value


def test_create_response_instance_populates_defaults():
    data = {
        "identifier": 7,
        "status": "processed",
        "sub_type_list": ["merit"],
    }
    instance = create_response_instance(data, ExampleResponse)

    assert instance.eligible_sub_types == ["merit"]
    assert instance.passed == []
    assert instance.name_en == ""
    assert instance.optional_flag is False


def test_get_default_value_falls_back_to_type_defaults():
    field_info = ExampleResponse.model_fields["optional_flag"]
    default = get_default_value_for_field("optional_flag", field_info, {})

    assert default is False


@pytest.fixture
def debug_settings(monkeypatch):
    from app.core.config import settings as config_settings

    monkeypatch.setattr(config_settings, "debug", True)
    monkeypatch.setattr(config_settings, "environment", "development")


@pytest.mark.asyncio
async def test_auto_convert_and_validate_returns_converted_instance(debug_settings):
    @auto_convert_and_validate(ExampleResponse)
    async def sample_endpoint():
        return {"identifier": 9, "status": "complete"}

    result = await sample_endpoint()

    assert isinstance(result, ExampleResponse)
    assert result.identifier == 9


@pytest.mark.asyncio
async def test_auto_convert_and_validate_raises_on_validation_failure(monkeypatch, debug_settings):
    async def sample_result():
        return {"identifier": 11}

    @auto_convert_and_validate(ExampleResponse)
    async def sample_endpoint():
        return await sample_result()

    monkeypatch.setattr(
        converter_module,
        "convert_to_response_model",
        lambda *_args, **_kwargs: {"unexpected": True},
    )

    with pytest.raises(ValueError):
        await sample_endpoint()
