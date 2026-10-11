"""
Tests for the admin-edited copies of the built-in ("fixed") form items.

固定欄位 / 固定文件（系統預設）have no row of their own: the service builds
them in code and injects them into every form config. An admin edit in
審核管理 materialises a row carrying the same `fixed_key`, and from then on
`inject_fixed_fields` must serve that row instead of the code default —
otherwise the edit is silently discarded on the next page load.

Covered here:
- the materialised row replaces the built-in and is still flagged is_fixed
- the injected config carries no per-user value (it is cached and shared)
- a materialised advisor row disappears again when the scholarship stops
  requiring a professor recommendation, exactly as the injected copy would
- a DEACTIVATED materialised row is not treated as "never edited", which would
  resurrect the built-in for students
"""

import pytest

from app.services.application_field_service import (
    ADVISOR_HELP_TEXT_ZH,
    BANK_STATEMENT_DESCRIPTION_ZH,
    FIXED_KEY_ADVISOR_NAME,
    FIXED_KEY_BANK_STATEMENT,
    FIXED_KEY_POSTAL_ACCOUNT,
    ApplicationFieldService,
)


@pytest.fixture
def service():
    return ApplicationFieldService(db=None)  # type: ignore[arg-type]


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
async def test_builtin_defaults_are_the_student_facing_text(service, monkeypatch):
    """審核管理 pre-fills the edit form with the built-in's text, so the
    defaults must be exactly what the wizard shows a student — otherwise the
    admin edits one wording while students keep reading another."""
    _requires_advisor(service, monkeypatch, True)

    fields, documents = await service.inject_fixed_fields("phd", [], [])
    by_key = {f["fixed_key"]: f for f in fields}

    assert by_key[FIXED_KEY_POSTAL_ACCOUNT]["field_label"] == "郵局局號加帳號共 14 碼(限本人)"
    assert by_key[FIXED_KEY_POSTAL_ACCOUNT]["placeholder"] == "請輸入 14 碼郵局帳號"
    assert by_key[FIXED_KEY_ADVISOR_NAME]["field_label"] == "教授姓名"
    assert by_key[FIXED_KEY_ADVISOR_NAME]["help_text"] == ADVISOR_HELP_TEXT_ZH
    assert "主要指導教授" in ADVISOR_HELP_TEXT_ZH
    assert documents[0]["description"] == BANK_STATEMENT_DESCRIPTION_ZH


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
async def test_injected_config_carries_no_per_user_values(service, monkeypatch):
    """The config is cached and shared by every student, so neither the
    built-ins nor the admin's materialised rows may carry a profile value.
    A per-user prefill here once served one student's 郵局帳號 and 指導教授
    to everyone else (#1443)."""
    _requires_advisor(service, monkeypatch, True)

    edited = {"id": 7, "fixed_key": FIXED_KEY_POSTAL_ACCOUNT, "field_label": "郵局／玉山帳號"}

    fields, documents = await service.inject_fixed_fields("phd", [edited], [])

    assert fields[0]["field_label"] == "郵局／玉山帳號"
    for item in [*fields, *documents]:
        assert "prefill_value" not in item
        assert "existing_file_url" not in item


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


@pytest.mark.asyncio
async def test_deactivated_materialised_row_does_not_resurrect_the_builtin(service, monkeypatch):
    """A built-in item the admin switched off must stay off.

    The student view filters inactive rows. If that filtering happened before
    the merge, the deactivated row would be invisible to it and the code
    default would be injected in its place — active and required again.
    """
    _requires_advisor(service, monkeypatch, False)

    disabled = {
        "id": 42,
        "fixed_key": FIXED_KEY_BANK_STATEMENT,
        "document_name": "存摺封面",
        "display_order": 1,
        "is_active": False,
    }

    _fields, documents = await service.inject_fixed_fields("phd", [], [disabled])

    assert len(documents) == 1
    assert documents[0]["is_active"] is False
