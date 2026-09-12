"""
Tests for the admin-edited copies of the built-in ("fixed") form items.

固定欄位 / 固定文件（系統預設）have no row of their own: the service builds
them in code and injects them into every form config. An admin edit in
審核管理 materialises a row carrying the same `fixed_key`, and from then on
`inject_fixed_fields` must serve that row instead of the code default —
otherwise the edit is silently discarded on the next page load.

Covered here:
- the materialised row replaces the built-in and is still flagged is_fixed
- per-user prefill still reaches the materialised row (it lives on the
  profile, not on the row)
- a materialised advisor row disappears again when the scholarship stops
  requiring a professor recommendation, exactly as the injected copy would
"""

import pytest

from app.services.application_field_service import (
    FIXED_KEY_ADVISOR_NAME,
    FIXED_KEY_BANK_STATEMENT,
    FIXED_KEY_POSTAL_ACCOUNT,
    ApplicationFieldService,
)


@pytest.fixture
def service(monkeypatch):
    svc = ApplicationFieldService(db=None)  # type: ignore[arg-type]

    async def no_profile(_user_id):
        return None

    monkeypatch.setattr(svc, "get_user_profile_data", no_profile)
    return svc


def _requires_advisor(service, monkeypatch, required: bool):
    async def check(_scholarship_type):
        return required

    monkeypatch.setattr(service, "check_requires_professor_recommendation", check)


@pytest.mark.asyncio
async def test_injects_builtin_when_no_row_exists(service, monkeypatch):
    _requires_advisor(service, monkeypatch, False)

    fields, documents = await service.inject_fixed_fields("phd", [], [])

    assert [f["fixed_key"] for f in fields] == [FIXED_KEY_POSTAL_ACCOUNT]
    assert [d["fixed_key"] for d in documents] == [FIXED_KEY_BANK_STATEMENT]
    assert documents[0]["document_name"] == "存摺封面"


@pytest.mark.asyncio
async def test_materialised_document_replaces_the_builtin(service, monkeypatch):
    """The admin renamed 存摺封面 — the built-in must not come back beside it."""
    _requires_advisor(service, monkeypatch, False)

    edited = {
        "id": 42,
        "fixed_key": FIXED_KEY_BANK_STATEMENT,
        "document_name": "存摺封面（正面）",
        "display_order": 3,
    }

    _fields, documents = await service.inject_fixed_fields("phd", [], [edited])

    assert len(documents) == 1
    assert documents[0]["document_name"] == "存摺封面（正面）"
    assert documents[0]["id"] == 42
    assert documents[0]["is_fixed"] is True


@pytest.mark.asyncio
async def test_materialised_field_still_gets_profile_prefill(service, monkeypatch):
    """prefill lives on the user profile, so it has to be re-applied to the
    admin's row — a materialised 郵局帳號 field that stopped prefilling would
    make every student retype an account number the system already holds."""
    _requires_advisor(service, monkeypatch, False)

    async def profile(_user_id):
        return {"account_number": "0001234567"}

    monkeypatch.setattr(service, "get_user_profile_data", profile)

    edited = {"id": 7, "fixed_key": FIXED_KEY_POSTAL_ACCOUNT, "field_label": "郵局／玉山帳號"}

    fields, _documents = await service.inject_fixed_fields("phd", [edited], [], user_id=1)

    assert len(fields) == 1
    assert fields[0]["field_label"] == "郵局／玉山帳號"
    assert fields[0]["prefill_value"] == "0001234567"


@pytest.mark.asyncio
async def test_materialised_advisor_field_replaces_the_builtin(service, monkeypatch):
    _requires_advisor(service, monkeypatch, True)

    edited = {"id": 9, "fixed_key": FIXED_KEY_ADVISOR_NAME, "field_label": "指導教授（中文姓名）"}

    fields, _documents = await service.inject_fixed_fields("phd", [edited], [])

    advisor_names = [f for f in fields if f["fixed_key"] == FIXED_KEY_ADVISOR_NAME]
    assert len(advisor_names) == 1
    assert advisor_names[0]["field_label"] == "指導教授（中文姓名）"
    assert advisor_names[0]["is_fixed"] is True


@pytest.mark.asyncio
async def test_materialised_advisor_field_dropped_when_not_required(service, monkeypatch):
    """The row outlives the setting that created it; the form must follow the
    current configuration, not the leftover row."""
    _requires_advisor(service, monkeypatch, False)

    edited = {"id": 9, "fixed_key": FIXED_KEY_ADVISOR_NAME, "field_label": "指導教授（中文姓名）"}

    fields, _documents = await service.inject_fixed_fields("phd", [edited], [])

    assert [f["fixed_key"] for f in fields] == [FIXED_KEY_POSTAL_ACCOUNT]


@pytest.mark.asyncio
async def test_admin_created_items_are_left_alone(service, monkeypatch):
    _requires_advisor(service, monkeypatch, False)

    own = {"id": 3, "fixed_key": None, "document_name": "研究計畫書", "display_order": 1}

    _fields, documents = await service.inject_fixed_fields("phd", [], [own])

    assert len(documents) == 2
    assert documents[0]["document_name"] == "研究計畫書"
    assert documents[0].get("is_fixed") is None
