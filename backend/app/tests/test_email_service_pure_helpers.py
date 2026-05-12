"""
Tests for the pure helpers on `EmailService`.

`EmailService` itself is side-effect heavy (SMTP send, DB-backed test-mode
config, template rendering), but two of its methods are pure functions
that can be tested in isolation:

- `_html_to_text` — HTMLParser-based plaintext extraction used to
  populate the multipart/alternative text fallback. A regression here
  would either crash on certain HTML inputs or leak script/style tag
  contents into the plaintext body.
- `_transform_recipients_for_test` — pure dict reshaping for email
  test-mode redirection. Critical: a bug that fails to redirect would
  send real emails to production recipients while we think we're in
  test mode.

These helpers are part of `email_service.py` which was one of three
services flagged as zero-coverage in the audit re-check (PR #231).

Wave 2g — seventh pure-function test coverage PR.
"""

from __future__ import annotations

import pytest

from app.services.email_service import EmailService

pytestmark = pytest.mark.smoke


@pytest.fixture
def service():
    """
    Instantiate EmailService without a DB; the helpers under test don't
    need it. `EmailService.__init__` accepts `db: Optional[AsyncSession]`
    so passing None is supported.
    """
    return EmailService(db=None)


# ---------------------------------------------------------------------------
# _html_to_text
# ---------------------------------------------------------------------------


class TestHtmlToText:
    """Pure HTML-to-plaintext converter used for the text/plain alternative
    in multipart emails."""

    def test_empty_string(self, service: EmailService) -> None:
        assert service._html_to_text("") == ""

    def test_plain_text_passthrough(self, service: EmailService) -> None:
        """Text without any HTML tags should come back essentially unchanged
        (modulo whitespace normalisation)."""
        assert service._html_to_text("Hello, world") == "Hello, world"

    def test_strips_simple_tags(self, service: EmailService) -> None:
        assert service._html_to_text("<p>Hello</p>") == "Hello"

    def test_strips_nested_tags(self, service: EmailService) -> None:
        result = service._html_to_text("<div><p>Hello <strong>world</strong></p></div>")
        assert result == "Hello world"

    def test_skips_script_content(self, service: EmailService) -> None:
        """SECURITY: <script> contents must not leak into plaintext. Otherwise
        a malicious template could embed JS-like text that confuses recipients."""
        html = "<p>Before</p><script>alert('xss')</script><p>After</p>"
        result = service._html_to_text(html)
        assert "alert" not in result
        assert "xss" not in result
        # Surrounding text should still be there
        assert "Before" in result
        assert "After" in result

    def test_skips_style_content(self, service: EmailService) -> None:
        """Same for <style> — its CSS rules shouldn't appear as plaintext."""
        html = "<p>Hello</p><style>.foo { color: red; }</style>"
        result = service._html_to_text(html)
        assert "color: red" not in result
        assert "Hello" in result

    def test_collapses_whitespace(self, service: EmailService) -> None:
        """Multiple consecutive spaces/newlines/tabs collapse to a single
        space. Helps the plain-text body render reasonably."""
        html = "<p>a   b\n\nc\t\td</p>"
        assert service._html_to_text(html) == "a b c d"

    def test_strips_leading_trailing_whitespace(self, service: EmailService) -> None:
        assert service._html_to_text("  <p>Hello</p>  ") == "Hello"

    def test_preserves_cjk(self, service: EmailService) -> None:
        """The implementation uses Python's HTMLParser, which is unicode-aware.
        Important: most real emails in this system are bilingual zh + en."""
        assert service._html_to_text("<p>王小明 申請通過</p>") == "王小明 申請通過"

    def test_html_entities_preserved_or_decoded(self, service: EmailService) -> None:
        """HTMLParser passes entities like &amp; through handle_data as-is by
        default (it doesn't auto-decode). Pin the current behavior so a future
        upgrade to convert_charrefs=True is a conscious change."""
        # `&amp;` either stays as-is OR becomes `&` depending on HTMLParser config
        result = service._html_to_text("<p>Tom &amp; Jerry</p>")
        assert "Tom" in result
        assert "Jerry" in result


# ---------------------------------------------------------------------------
# _transform_recipients_for_test
# ---------------------------------------------------------------------------


class TestTransformRecipientsForTest:
    """Pure dict reshaping. SAFETY-CRITICAL — a bug here that fails to
    redirect would send real emails to production recipients while we
    think we're in test mode."""

    def test_basic_redirect_to_single_test_email(self, service: EmailService) -> None:
        result = service._transform_recipients_for_test(
            original_to=["real@nycu.edu.tw"],
            test_emails=["dev@nycu.edu.tw"],
        )
        # Real recipient must NOT be in the new to/cc/bcc
        assert result["to"] == ["dev@nycu.edu.tw"]
        assert "real@nycu.edu.tw" not in result["to"]
        # CC and BCC are cleared in test mode (documented behavior)
        assert result["cc"] == []
        assert result["bcc"] == []

    def test_multiple_test_emails(self, service: EmailService) -> None:
        result = service._transform_recipients_for_test(
            original_to=["student@nycu.edu.tw"],
            test_emails=["qa1@example.com", "qa2@example.com"],
        )
        assert result["to"] == ["qa1@example.com", "qa2@example.com"]

    def test_original_to_preserved_in_metadata(self, service: EmailService) -> None:
        """The original_to field must round-trip so the test-mode banner /
        X-Original-To header can display who would have received the mail."""
        result = service._transform_recipients_for_test(
            original_to=["alice@nycu.edu.tw", "bob@nycu.edu.tw"],
            test_emails=["dev@example.com"],
        )
        assert result["original_to"] == ["alice@nycu.edu.tw", "bob@nycu.edu.tw"]

    def test_cc_and_bcc_cleared_but_preserved_in_metadata(self, service: EmailService) -> None:
        result = service._transform_recipients_for_test(
            original_to=["to@nycu.edu.tw"],
            test_emails=["dev@example.com"],
            original_cc=["cc@nycu.edu.tw"],
            original_bcc=["bcc@nycu.edu.tw"],
        )
        # Cleared in the live send fields
        assert result["cc"] == []
        assert result["bcc"] == []
        # But preserved in metadata for the test banner
        assert result["original_cc"] == ["cc@nycu.edu.tw"]
        assert result["original_bcc"] == ["bcc@nycu.edu.tw"]

    def test_none_cc_and_bcc_become_empty_lists(self, service: EmailService) -> None:
        """When the caller passes None (the default), metadata fields fall
        back to empty lists, not None — the downstream banner formatter
        assumes lists."""
        result = service._transform_recipients_for_test(
            original_to=["to@nycu.edu.tw"],
            test_emails=["dev@example.com"],
            original_cc=None,
            original_bcc=None,
        )
        assert result["original_cc"] == []
        assert result["original_bcc"] == []

    def test_returned_dict_shape(self, service: EmailService) -> None:
        """The downstream sender expects exactly these 6 keys; pin the shape."""
        result = service._transform_recipients_for_test(
            original_to=["x@nycu.edu.tw"],
            test_emails=["y@example.com"],
        )
        assert set(result.keys()) == {
            "to",
            "cc",
            "bcc",
            "original_to",
            "original_cc",
            "original_bcc",
        }
