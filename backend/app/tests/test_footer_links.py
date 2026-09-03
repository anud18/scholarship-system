"""Tests for the admin-editable footer 相關連結 feature.

Covers the schema-level URL guard (stored-XSS prevention), the admin-only
mutation surface, the url/file payload split, and the visibility rules for
inactive links.
"""

from io import BytesIO
from typing import AsyncGenerator
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, require_admin
from app.db.deps import get_db
from app.main import app
from app.models.footer_link import FooterLink, FooterLinkType
from app.models.user import User, UserRole, UserType
from app.schemas.footer_link import FooterLinkCreate, FooterLinkUpdate

# ─── Pure schema tests (unit lane) ───────────────────────────────────────


@pytest.mark.parametrize(
    "bad_url",
    [
        "javascript:alert(1)",
        "JavaScript:alert(1)",
        "data:text/html;base64,PHNjcmlwdD4=",
        "vbscript:msgbox(1)",
        "file:///etc/passwd",
        "ftp://example.com/x",
        "not-a-url",
        "https://",
    ],
)
def test_create_rejects_non_http_urls(bad_url):
    """A footer link renders as <a href>; permitting javascript:/data: would
    make the admin form a stored-XSS vector for every site visitor."""
    with pytest.raises(ValidationError):
        FooterLinkCreate(title_zh="惡意", url=bad_url)


@pytest.mark.parametrize(
    "good_url",
    [
        "https://www.nycu.edu.tw",
        "http://aa.nycu.edu.tw/path?q=1",
        "https://portal.nycu.edu.tw/",
    ],
)
def test_create_accepts_http_and_https(good_url):
    link = FooterLinkCreate(title_zh="連結", url=good_url)
    assert link.url == good_url


def test_create_strips_titles_and_blanks_title_en_to_none():
    link = FooterLinkCreate(title_zh="  教務處  ", title_en="   ", url="https://x.nycu.edu.tw")
    assert link.title_zh == "教務處"
    assert link.title_en is None


def test_create_rejects_whitespace_only_title_zh():
    with pytest.raises(ValidationError):
        FooterLinkCreate(title_zh="   ", url="https://x.nycu.edu.tw")


def test_update_requires_at_least_one_field():
    with pytest.raises(ValidationError):
        FooterLinkUpdate()


def test_update_allows_single_field():
    assert FooterLinkUpdate(is_active=False).is_active is False


# ─── Endpoint fixtures ───────────────────────────────────────────────────


@pytest_asyncio.fixture
async def admin_user(db: AsyncSession) -> User:
    user = User(
        nycu_id="footer_admin",
        name="Footer Admin",
        email="footer_admin@university.edu",
        user_type=UserType.employee,
        role=UserRole.admin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def student_user(db: AsyncSession) -> User:
    user = User(
        nycu_id="footer_student",
        name="Footer Student",
        email="footer_student@university.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _client_for(db: AsyncSession, user: User, *, is_admin: bool):
    async def override_get_db():
        yield db

    async def override_get_current_user():
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    if is_admin:

        async def override_require_admin():
            return user

        app.dependency_overrides[require_admin] = override_require_admin

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest_asyncio.fixture
async def admin_client(db: AsyncSession, admin_user: User) -> AsyncGenerator[AsyncClient, None]:
    try:
        async with _client_for(db, admin_user, is_admin=True) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def student_client(db: AsyncSession, student_user: User) -> AsyncGenerator[AsyncClient, None]:
    try:
        async with _client_for(db, student_user, is_admin=False) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def fake_minio():
    """Patch the module-level binding in the endpoint (it imports the
    singleton at module scope, so patching the service module is a no-op)."""
    with patch("app.api.v1.endpoints.footer_links.minio_service") as mock_service:
        mock_service.default_bucket = "test-bucket"
        mock_service.client = MagicMock()
        yield mock_service


# ─── Endpoint tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_and_list_url_link(admin_client: AsyncClient):
    res = await admin_client.post(
        "/api/v1/footer-links",
        json={"title_zh": "教務處", "title_en": "Academic Affairs", "url": "https://aa.nycu.edu.tw/"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is True
    assert body["data"]["link_type"] == "url"
    assert body["data"]["url"] == "https://aa.nycu.edu.tw/"

    listed = await admin_client.get("/api/v1/footer-links")
    assert listed.status_code == 200
    titles = [item["title_zh"] for item in listed.json()["data"]]
    assert "教務處" in titles


@pytest.mark.asyncio
async def test_create_rejects_javascript_url_at_api_boundary(admin_client: AsyncClient):
    res = await admin_client.post(
        "/api/v1/footer-links",
        json={"title_zh": "惡意", "url": "javascript:alert(document.cookie)"},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_new_links_append_to_end_of_order(admin_client: AsyncClient):
    first = await admin_client.post("/api/v1/footer-links", json={"title_zh": "第一", "url": "https://a.nycu.edu.tw"})
    second = await admin_client.post("/api/v1/footer-links", json={"title_zh": "第二", "url": "https://b.nycu.edu.tw"})
    assert second.json()["data"]["sort_order"] > first.json()["data"]["sort_order"]


@pytest.mark.asyncio
async def test_section_defaults_to_related_and_is_persisted(admin_client: AsyncClient):
    related = await admin_client.post(
        "/api/v1/footer-links", json={"title_zh": "教務處", "url": "https://a.nycu.edu.tw"}
    )
    policy = await admin_client.post(
        "/api/v1/footer-links",
        json={"title_zh": "隱私權政策", "url": "https://p.nycu.edu.tw", "section": "policy"},
    )
    assert related.json()["data"]["section"] == "related"
    assert policy.json()["data"]["section"] == "policy"


@pytest.mark.asyncio
async def test_list_filters_by_section_and_returns_both_when_omitted(admin_client: AsyncClient):
    await admin_client.post("/api/v1/footer-links", json={"title_zh": "教務處", "url": "https://a.nycu.edu.tw"})
    await admin_client.post(
        "/api/v1/footer-links",
        json={"title_zh": "使用條款", "url": "https://t.nycu.edu.tw", "section": "policy"},
    )

    everything = await admin_client.get("/api/v1/footer-links")
    assert {item["section"] for item in everything.json()["data"]} == {"related", "policy"}

    only_policy = await admin_client.get("/api/v1/footer-links?section=policy")
    assert [item["title_zh"] for item in only_policy.json()["data"]] == ["使用條款"]

    bogus = await admin_client.get("/api/v1/footer-links?section=nope")
    assert bogus.status_code == 422


@pytest.mark.asyncio
async def test_sort_order_is_independent_per_section(admin_client: AsyncClient):
    """Each block is its own list: a new policy link starts at 0 even when
    the related list already holds entries."""
    await admin_client.post("/api/v1/footer-links", json={"title_zh": "A", "url": "https://a.nycu.edu.tw"})
    await admin_client.post("/api/v1/footer-links", json={"title_zh": "B", "url": "https://b.nycu.edu.tw"})
    policy = await admin_client.post(
        "/api/v1/footer-links",
        json={"title_zh": "隱私權政策", "url": "https://p.nycu.edu.tw", "section": "policy"},
    )
    assert policy.json()["data"]["sort_order"] == 0


@pytest.mark.asyncio
async def test_upload_accepts_section(admin_client: AsyncClient, fake_minio):
    res = await admin_client.post(
        "/api/v1/footer-links/upload",
        data={"title_zh": "無障礙聲明", "section": "policy"},
        files={"file": ("a11y.pdf", BytesIO(b"%PDF-1.4 test"), "application/pdf")},
    )
    assert res.status_code == 200, res.text
    assert res.json()["data"]["section"] == "policy"
    assert res.json()["data"]["link_type"] == "file"


@pytest.mark.asyncio
async def test_inactive_link_hidden_from_students_and_visible_to_admin(db: AsyncSession, admin_client: AsyncClient):
    created = await admin_client.post(
        "/api/v1/footer-links", json={"title_zh": "草稿連結", "url": "https://draft.nycu.edu.tw"}
    )
    link_id = created.json()["data"]["id"]

    hidden = await admin_client.patch(f"/api/v1/footer-links/{link_id}", json={"is_active": False})
    assert hidden.status_code == 200
    assert hidden.json()["data"]["is_active"] is False

    # Default list excludes it for everyone.
    default_list = await admin_client.get("/api/v1/footer-links")
    assert link_id not in [item["id"] for item in default_list.json()["data"]]

    # Admin may opt in.
    admin_all = await admin_client.get("/api/v1/footer-links?include_inactive=true")
    assert link_id in [item["id"] for item in admin_all.json()["data"]]


@pytest.mark.asyncio
async def test_student_cannot_reveal_inactive_links_via_query_param(
    db: AsyncSession, admin_user: User, student_user: User
):
    link = FooterLink(
        title_zh="隱藏連結",
        link_type=FooterLinkType.url,
        url="https://hidden.nycu.edu.tw",
        sort_order=0,
        is_active=False,
        created_by=admin_user.id,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)

    try:
        async with _client_for(db, student_user, is_admin=False) as ac:
            res = await ac.get("/api/v1/footer-links?include_inactive=true")
    finally:
        app.dependency_overrides.clear()

    assert res.status_code == 200
    assert link.id not in [item["id"] for item in res.json()["data"]]


@pytest.mark.asyncio
async def test_upload_creates_file_link(admin_client: AsyncClient, fake_minio):
    res = await admin_client.post(
        "/api/v1/footer-links/upload",
        files={"file": ("guide.pdf", BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
        data={"title_zh": "獎學金申請指南", "title_en": "Scholarship Guide"},
    )
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["link_type"] == "file"
    assert data["url"] is None
    assert data["original_filename"] == "guide.pdf"
    assert data["object_name"].startswith("footer-links/link_")
    assert data["object_name"].endswith(".pdf")
    fake_minio.client.put_object.assert_called_once()


@pytest.mark.asyncio
async def test_upload_rejects_disallowed_extension(admin_client: AsyncClient, fake_minio):
    res = await admin_client.post(
        "/api/v1/footer-links/upload",
        files={"file": ("evil.exe", BytesIO(b"MZ"), "application/octet-stream")},
        data={"title_zh": "壞檔案"},
    )
    # validate_upload_file rejects a disallowed extension with 415.
    assert res.status_code == 415
    fake_minio.client.put_object.assert_not_called()


@pytest.mark.asyncio
async def test_cannot_set_url_on_a_file_link(admin_client: AsyncClient, fake_minio):
    created = await admin_client.post(
        "/api/v1/footer-links/upload",
        files={"file": ("manual.pdf", BytesIO(b"%PDF-1.4"), "application/pdf")},
        data={"title_zh": "系統操作手冊"},
    )
    link_id = created.json()["data"]["id"]

    res = await admin_client.patch(f"/api/v1/footer-links/{link_id}", json={"url": "https://evil.example.com"})
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_delete_removes_stored_object(admin_client: AsyncClient, fake_minio):
    created = await admin_client.post(
        "/api/v1/footer-links/upload",
        files={"file": ("faq.pdf", BytesIO(b"%PDF-1.4"), "application/pdf")},
        data={"title_zh": "常見問題"},
    )
    data = created.json()["data"]

    res = await admin_client.delete(f"/api/v1/footer-links/{data['id']}")
    assert res.status_code == 200
    fake_minio.client.remove_object.assert_called_once_with("test-bucket", data["object_name"])

    gone = await admin_client.patch(f"/api/v1/footer-links/{data['id']}", json={"title_zh": "x"})
    assert gone.status_code == 404


@pytest.mark.asyncio
async def test_reorder_persists_new_positions(admin_client: AsyncClient):
    a = await admin_client.post("/api/v1/footer-links", json={"title_zh": "A", "url": "https://a.nycu.edu.tw"})
    b = await admin_client.post("/api/v1/footer-links", json={"title_zh": "B", "url": "https://b.nycu.edu.tw"})
    a_id, b_id = a.json()["data"]["id"], b.json()["data"]["id"]

    res = await admin_client.patch(
        "/api/v1/footer-links/reorder",
        json={"items": [{"id": b_id, "sort_order": 0}, {"id": a_id, "sort_order": 1}]},
    )
    assert res.status_code == 200

    listed = await admin_client.get("/api/v1/footer-links")
    ordered = [item["id"] for item in listed.json()["data"] if item["id"] in (a_id, b_id)]
    assert ordered == [b_id, a_id]


@pytest.mark.asyncio
async def test_reorder_rejects_unknown_id(admin_client: AsyncClient):
    res = await admin_client.patch(
        "/api/v1/footer-links/reorder",
        json={"items": [{"id": 999999, "sort_order": 0}]},
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_stream_file_returns_content_length(admin_client: AsyncClient, fake_minio):
    payload = b"%PDF-1.4 streamed body"
    created = await admin_client.post(
        "/api/v1/footer-links/upload",
        files={"file": ("doc.pdf", BytesIO(payload), "application/pdf")},
        data={"title_zh": "文件"},
    )
    link_id = created.json()["data"]["id"]

    minio_response = MagicMock()
    minio_response.read.return_value = payload
    fake_minio.client.get_object.return_value = minio_response

    res = await admin_client.get(f"/api/v1/footer-links/{link_id}/file")
    assert res.status_code == 200
    # Missing Content-Length makes the frontend PDF viewer report a bogus
    # "password protected" error — pin it.
    assert res.headers["content-length"] == str(len(payload))
    assert res.headers["x-content-type-options"] == "nosniff"


@pytest.mark.asyncio
async def test_title_en_can_be_cleared(admin_client: AsyncClient):
    """A blank title_en normalizes to None but is a legitimate 'clear the
    English label' request — it must not be rejected as an empty payload."""
    created = await admin_client.post(
        "/api/v1/footer-links",
        json={"title_zh": "校務系統", "title_en": "Campus", "url": "https://x.nycu.edu.tw"},
    )
    link_id = created.json()["data"]["id"]

    res = await admin_client.patch(f"/api/v1/footer-links/{link_id}", json={"title_en": ""})
    assert res.status_code == 200, res.text
    assert res.json()["data"]["title_en"] is None


@pytest.mark.asyncio
async def test_update_with_no_fields_is_rejected(admin_client: AsyncClient):
    created = await admin_client.post("/api/v1/footer-links", json={"title_zh": "X", "url": "https://x.nycu.edu.tw"})
    link_id = created.json()["data"]["id"]

    res = await admin_client.patch(f"/api/v1/footer-links/{link_id}", json={})
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_stored_content_type_ignores_client_declared_value(admin_client: AsyncClient, fake_minio):
    """The multipart Content-Type is attacker-controlled and this document is
    later streamed back inline from our own origin, so a .pdf declared
    text/html must not be persisted or echoed."""
    created = await admin_client.post(
        "/api/v1/footer-links/upload",
        files={"file": ("guide.pdf", BytesIO(b"<html><body>spoof</body></html>"), "text/html")},
        data={"title_zh": "偽裝檔案"},
    )
    assert created.status_code == 200, created.text
    assert created.json()["data"]["content_type"] == "application/pdf"

    link_id = created.json()["data"]["id"]
    minio_response = MagicMock()
    minio_response.read.return_value = b"<html><body>spoof</body></html>"
    fake_minio.client.get_object.return_value = minio_response

    streamed = await admin_client.get(f"/api/v1/footer-links/{link_id}/file")
    assert streamed.headers["content-type"].startswith("application/pdf")


# ─── Negative authorization: every mutation is admin-only ────────────────


@pytest.mark.asyncio
async def test_student_cannot_create_link(student_client: AsyncClient):
    res = await student_client.post(
        "/api/v1/footer-links", json={"title_zh": "駭客連結", "url": "https://evil.example.com"}
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_student_cannot_upload_file(student_client: AsyncClient):
    res = await student_client.post(
        "/api/v1/footer-links/upload",
        files={"file": ("x.pdf", BytesIO(b"%PDF-1.4"), "application/pdf")},
        data={"title_zh": "x"},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_student_cannot_update_link(db: AsyncSession, student_client: AsyncClient, admin_user: User):
    link = FooterLink(
        title_zh="原標題",
        link_type=FooterLinkType.url,
        url="https://ok.nycu.edu.tw",
        sort_order=0,
        is_active=True,
        created_by=admin_user.id,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)

    res = await student_client.patch(f"/api/v1/footer-links/{link.id}", json={"title_zh": "被竄改"})
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_student_cannot_delete_link(db: AsyncSession, student_client: AsyncClient, admin_user: User):
    link = FooterLink(
        title_zh="待刪",
        link_type=FooterLinkType.url,
        url="https://ok.nycu.edu.tw",
        sort_order=0,
        is_active=True,
        created_by=admin_user.id,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)

    res = await student_client.delete(f"/api/v1/footer-links/{link.id}")
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_student_cannot_reorder_links(student_client: AsyncClient):
    res = await student_client.patch("/api/v1/footer-links/reorder", json={"items": [{"id": 1, "sort_order": 0}]})
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_stream_rejects_url_link(admin_client: AsyncClient):
    created = await admin_client.post("/api/v1/footer-links", json={"title_zh": "外部", "url": "https://x.nycu.edu.tw"})
    link_id = created.json()["data"]["id"]

    res = await admin_client.get(f"/api/v1/footer-links/{link_id}/file")
    assert res.status_code == 404
