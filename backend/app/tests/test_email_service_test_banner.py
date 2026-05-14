"""
Tests for `EmailService._add_test_banner_to_body` + `_add_test_headers`.

Wave 6e covered schedule_email; the email-service pure-helper wave
covered _html_to_text + _transform_recipients_for_test. This wave
fills:

  - **_add_test_banner_to_body(body, html_content, original)**:
    when the system runs in test-mode (intercept all outgoing
    mail to a dev mailbox), this prepends a warning banner so the
    test recipient knows the mail was intended for someone else.
    Returns (text_body, html_body_or_None).

  - **_add_test_headers(msg, original, session_id)**: stamps
    X-Test-Mode / X-Test-Session-ID / X-Original-To/CC/BCC headers
    onto the EmailMessage. Audit / forensics depend on these for
    proving "this email was a test interception".

13 cases. Pure helpers via EmailService instance with mocked deps.
"""

from email.message import EmailMessage
from unittest.mock import MagicMock

import pytest

from app.services.email_service import EmailService


@pytest.fixture
def service():
    # EmailService accepts an optional db argument
    return EmailService(db=MagicMock())


# ─── _add_test_banner_to_body ───────────────────────────────────────


def test_banner_prepended_to_plain_body(service):
    # Pin: banner inserted BEFORE the original body (not after).
    new_body, _ = service._add_test_banner_to_body(
        body="Original body",
        html_content=None,
        original_recipients={"original_to": ["real@x.com"]},
    )
    assert new_body.endswith("Original body")
    assert "⚠️ 郵件測試模式 ⚠️" in new_body


def test_banner_includes_original_to(service):
    new_body, _ = service._add_test_banner_to_body(
        body="x",
        html_content=None,
        original_recipients={"original_to": ["alice@x.com", "bob@y.com"]},
    )
    assert "alice@x.com" in new_body
    assert "bob@y.com" in new_body


def test_banner_includes_cc_when_present(service):
    # Pin: CC line ONLY when original_cc present. Otherwise the
    # banner omits the line (no "原副本:" with empty value).
    new_body, _ = service._add_test_banner_to_body(
        body="",
        html_content=None,
        original_recipients={
            "original_to": ["a@b.com"],
            "original_cc": ["cc1@x.com", "cc2@y.com"],
        },
    )
    assert "原副本: cc1@x.com, cc2@y.com" in new_body


def test_banner_includes_bcc_when_present(service):
    new_body, _ = service._add_test_banner_to_body(
        body="",
        html_content=None,
        original_recipients={
            "original_to": ["a@b.com"],
            "original_bcc": ["bcc@x.com"],
        },
    )
    assert "原密件副本: bcc@x.com" in new_body


def test_banner_omits_cc_line_when_missing(service):
    # Pin: no CC field → no CC line in banner. Prevents "原副本: "
    # rendering with no value.
    new_body, _ = service._add_test_banner_to_body(
        body="",
        html_content=None,
        original_recipients={"original_to": ["a@b.com"]},
    )
    assert "原副本" not in new_body


def test_banner_html_returns_none_when_no_html_content(service):
    # Pin: HTML banner only generated when html_content is supplied.
    # The endpoint can pass None for plain-text-only emails.
    _, new_html = service._add_test_banner_to_body(
        body="x",
        html_content=None,
        original_recipients={"original_to": ["a@b.com"]},
    )
    assert new_html is None


def test_banner_html_prepended_when_html_content_supplied(service):
    # Pin: HTML banner div prepended to existing HTML body.
    _, new_html = service._add_test_banner_to_body(
        body="x",
        html_content="<p>Original HTML</p>",
        original_recipients={"original_to": ["a@b.com"]},
    )
    assert new_html is not None
    assert "<p>Original HTML</p>" in new_html
    assert "⚠️ 郵件測試模式 ⚠️" in new_html
    # Banner is before original
    assert new_html.index("⚠️") < new_html.index("Original HTML")


def test_banner_html_styled_with_warning_colors(service):
    # Pin: warning color #ffc107 + light-yellow background — pinned
    # so admins clearly see the test marker (orange banner).
    _, new_html = service._add_test_banner_to_body(
        body="x",
        html_content="<p>x</p>",
        original_recipients={"original_to": ["a@b.com"]},
    )
    assert "#ffc107" in new_html
    assert "#fff3cd" in new_html


def test_banner_empty_body_still_includes_banner(service):
    # Pin: empty body input still produces a banner (no Bug where
    # empty body skips the banner).
    new_body, _ = service._add_test_banner_to_body(
        body="",
        html_content=None,
        original_recipients={"original_to": ["a@b.com"]},
    )
    assert "⚠️ 郵件測試模式 ⚠️" in new_body
    assert "=" * 60 in new_body  # the "=" * 60 separator


# ─── _add_test_headers ──────────────────────────────────────────────


def test_test_headers_x_test_mode_set(service):
    msg = EmailMessage()
    service._add_test_headers(
        msg,
        original_recipients={"original_to": ["a@b.com"]},
        session_id="session-xyz",
    )
    assert msg["X-Test-Mode"] == "true"
    assert msg["X-Test-Session-ID"] == "session-xyz"


def test_test_headers_x_original_to_comma_separated(service):
    msg = EmailMessage()
    service._add_test_headers(
        msg,
        original_recipients={"original_to": ["a@b.com", "b@y.com"]},
        session_id="s",
    )
    # Pin: comma-space separator (not just comma). Forensics tools
    # parse this header.
    assert msg["X-Original-To"] == "a@b.com, b@y.com"


def test_test_headers_omits_cc_bcc_when_absent(service):
    # Pin: X-Original-CC and X-Original-BCC are NOT added when the
    # recipient lists are empty. Pin so SMTP doesn't get empty
    # header lines.
    msg = EmailMessage()
    service._add_test_headers(
        msg,
        original_recipients={"original_to": ["a@b.com"]},
        session_id="s",
    )
    assert "X-Original-CC" not in msg
    assert "X-Original-BCC" not in msg


def test_test_headers_includes_cc_bcc_when_present(service):
    msg = EmailMessage()
    service._add_test_headers(
        msg,
        original_recipients={
            "original_to": ["a@b.com"],
            "original_cc": ["cc@x.com"],
            "original_bcc": ["bcc@y.com"],
        },
        session_id="s",
    )
    assert msg["X-Original-CC"] == "cc@x.com"
    assert msg["X-Original-BCC"] == "bcc@y.com"
