"""
Tests for the notification `action_url` allowlist (stored-XSS fix).

The notification panel navigates to action_url when a recipient clicks
"查看", so an admin-supplied `javascript:` value executed in every
recipient's browser (ZAP 40014 flagged the persisted payload). Only a
same-site path or an http(s) URL may be stored.
"""

import re

import pytest
from pydantic import ValidationError

from app.core.url_safety import ACTION_URL_ERROR, validate_action_url
from app.models.notification import Notification
from app.schemas.notification import NotificationCreate, NotificationUpdate

ALLOWED = [
    "/dashboard",
    "/applications/12/documents",
    "/admin/rosters?tab=locked#top",
    "https://www.nycu.edu.tw/news",
    "http://intranet.nycu.edu.tw/page",
    "HTTPS://www.nycu.edu.tw/",
    # Non-ASCII spaces are percent-encoded by browsers, not stripped: harmless.
    "https://www.nycu.edu.tw/search?q=獎學金\u3000申請",
]

REJECTED = [
    "javascript:alert(document.cookie)",
    "JavaScript:alert(1)",
    "data:text/html,<script>alert(1)</script>",
    "vbscript:msgbox(1)",
    "//evil.example/phish",
    "/\\evil.example",
    "/\t/evil.example",
    "java\nscript:alert(1)",
    "https:///no-host",
    "ftp://files.example/x",
    "www.nycu.edu.tw",
    "applications/1",
]


@pytest.mark.parametrize("url", ALLOWED)
def test_allowed_action_urls_pass_unchanged(url):
    assert validate_action_url(url) == url
    assert NotificationCreate(title="t", message="m", action_url=url).action_url == url
    assert NotificationUpdate(action_url=url).action_url == url


@pytest.mark.parametrize("url", REJECTED)
def test_unsafe_action_urls_are_rejected_on_create_and_update(url):
    with pytest.raises(ValidationError):
        NotificationCreate(title="t", message="m", action_url=url)
    with pytest.raises(ValidationError):
        NotificationUpdate(action_url=url)


@pytest.mark.parametrize("url", [None, "", "   "])
def test_empty_action_url_normalises_to_none(url):
    assert NotificationCreate(title="t", message="m", action_url=url).action_url is None
    assert NotificationUpdate(action_url=url).action_url is None


def test_surrounding_whitespace_is_trimmed():
    assert validate_action_url("  /dashboard  ") == "/dashboard"


@pytest.mark.parametrize("url", REJECTED)
def test_error_message_is_user_facing_zh_tw(url):
    with pytest.raises(ValueError, match=re.escape(ACTION_URL_ERROR)):
        validate_action_url(url)


@pytest.mark.parametrize("column", ["action_url", "href"])
def test_model_rejects_unsafe_link_from_any_writer(column):
    """Service-layer writers bypass the request schemas; the model still refuses."""
    with pytest.raises(ValueError):
        Notification(title="t", message="m", **{column: "javascript:alert(1)"})
    assert getattr(Notification(title="t", message="m", **{column: "/applications/1"}), column) == "/applications/1"
