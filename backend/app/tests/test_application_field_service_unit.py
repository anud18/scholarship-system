from datetime import datetime
from types import SimpleNamespace
from itertools import count
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.application_field import ApplicationDocumentUpdate, ApplicationFieldUpdate
from app.services.application_field_service import ApplicationFieldService


class _FakeScalarResult:
    def __init__(self, items=None):
        self._items = list(items or [])

    def scalar_one_or_none(self):
        return self._items[0] if self._items else None


@pytest.fixture
def dummy_session():
    class DummySession:
        def __init__(self):
            self.execute = AsyncMock()
            self.commit = AsyncMock()
            self.refresh = AsyncMock()
            self.add = MagicMock()

    return DummySession()


def _build_field(**overrides):
    now = datetime.utcnow()
    defaults = dict(
        id=1,
        scholarship_type="NSTC",
        field_name="gpa",
        field_label="GPA",
        field_label_en="GPA",
        field_type="text",
        is_required=False,
        placeholder=None,
        placeholder_en=None,
        max_length=None,
        min_value=None,
        max_value=None,
        step_value=None,
        field_options=None,
        display_order=1,
        is_active=True,
        help_text=None,
        help_text_en=None,
        validation_rules=None,
        conditional_rules=None,
        created_at=now,
        updated_at=now,
        created_by=10,
        updated_by=10,
        is_fixed=False,
        prefill_value=None,
        bank_code=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _build_document(**overrides):
    now = datetime.utcnow()
    defaults = dict(
        id=5,
        scholarship_type="NSTC",
        document_name="Transcript",
        document_name_en="Transcript",
        description=None,
        description_en=None,
        is_required=True,
        accepted_file_types=["PDF"],
        max_file_size="5MB",
        max_file_count=1,
        display_order=1,
        is_active=True,
        upload_instructions=None,
        upload_instructions_en=None,
        validation_rules=None,
        created_at=now,
        updated_at=now,
        created_by=21,
        updated_by=21,
        is_fixed=False,
        existing_file_url=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@pytest.mark.asyncio
async def test_update_field_updates_attributes_and_sets_updated_by(dummy_session):
    existing_field = _build_field(field_label="Old Label", placeholder="Old")
    dummy_session.execute.return_value = _FakeScalarResult([existing_field])

    service = ApplicationFieldService(dummy_session)

    update_payload = ApplicationFieldUpdate(field_label="New Label", placeholder="Updated")

    response = await service.update_field(field_id=1, field_data=update_payload, updated_by=99)

    assert existing_field.field_label == "New Label"
    assert existing_field.placeholder == "Updated"
    assert existing_field.updated_by == 99

    dummy_session.commit.assert_awaited_once()
    dummy_session.refresh.assert_awaited_once_with(existing_field)

    assert response.field_label == "New Label"
    assert response.updated_by == 99


@pytest.mark.asyncio
async def test_bulk_update_fields_replaces_existing_entries(dummy_session):
    id_counter = count(start=100)

    async def fake_refresh(obj):
        if getattr(obj, "id", None) is None:
            obj.id = next(id_counter)
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.utcnow()
        if getattr(obj, "is_active", None) is None:
            obj.is_active = True
        obj.updated_at = datetime.utcnow()

    dummy_session.refresh.side_effect = fake_refresh

    service = ApplicationFieldService(dummy_session)

    field_payloads = [
        dict(
            field_name="gpa",
            field_label="GPA",
            field_label_en="GPA",
            field_type="number",
            is_required=True,
            display_order=1,
        ),
        dict(
            field_name="research_topic",
            field_label="研究主題",
            field_label_en="Research Topic",
            field_type="text",
            is_required=False,
            display_order=2,
        ),
    ]

    result = await service.bulk_update_fields("NSTC", field_payloads, updated_by=7)

    # Delete issued once, commit performed, refresh called for each field
    dummy_session.execute.assert_awaited()
    dummy_session.commit.assert_awaited_once()
    assert dummy_session.refresh.await_count == len(field_payloads)
    assert dummy_session.add.call_count == len(field_payloads)

    # Responses echo the payloads and gained ids
    assert [field.field_name for field in result] == ["gpa", "research_topic"]
    assert all(field.id is not None for field in result)
    assert all(field.scholarship_type == "NSTC" for field in result)


@pytest.mark.asyncio
async def test_update_document_returns_response(dummy_session):
    existing_doc = _build_document(document_name="Transcript", is_required=True)
    dummy_session.execute.return_value = _FakeScalarResult([existing_doc])

    service = ApplicationFieldService(dummy_session)

    update_payload = ApplicationDocumentUpdate(document_name="Updated Transcript", is_required=False)

    response = await service.update_document(document_id=5, document_data=update_payload, updated_by=44)

    assert existing_doc.document_name == "Updated Transcript"
    assert existing_doc.is_required is False
    assert existing_doc.updated_by == 44

    dummy_session.commit.assert_awaited_once()
    dummy_session.refresh.assert_awaited_once_with(existing_doc)

    assert response.document_name == "Updated Transcript"
    assert response.is_required is False
