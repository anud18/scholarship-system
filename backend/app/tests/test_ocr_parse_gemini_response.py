"""
Pure-function tests for `OCRService._parse_gemini_response`.

OCR is used during bank-statement verification — students upload a photo
and the response is parsed into structured account data. The Gemini
LLM commonly wraps its JSON output in ```json ... ``` markdown fences;
the parser strips them.

Wrong parsing means:
- Successful OCR is incorrectly reported as 'failed' (false negative,
  manual review burden goes up).
- Errors leak raw API responses to the frontend (security/UX issue —
  the SECURITY comment in the source explicitly notes this).

The parser is deliberately conservative: any failure returns a
sanitized error dict rather than re-raising.

1 helper covered (8 cases).
"""

import pytest

from app.services.ocr_service import OCRService


@pytest.fixture
def service():
    return OCRService(db=None)


# ─── Happy path ──────────────────────────────────────────────────────


def test_parse_clean_json_string(service):
    """Plain JSON string with required 'success' field → passes through."""
    result = service._parse_gemini_response('{"success": true, "account_number": "12345"}')
    assert result == {"success": True, "account_number": "12345"}


def test_parse_strips_json_fence_markdown(service):
    """Gemini commonly wraps output in ```json ... ``` — strip both ends."""
    response = '```json\n{"success": true, "confidence": 0.95}\n```'
    result = service._parse_gemini_response(response)
    assert result == {"success": True, "confidence": 0.95}


def test_parse_strips_only_trailing_fence(service):
    """Some responses have only the closing fence (no opening). Pin
    behavior: the impl only strips ```json prefix and ``` suffix in
    that order — a response missing the prefix won't crash."""
    response = '{"success": true}\n```'
    result = service._parse_gemini_response(response)
    assert result == {"success": True}


def test_parse_handles_whitespace_around_fences(service):
    """Extra whitespace around fences and inside content shouldn't break parsing."""
    response = '  \n```json\n  {"success": true}  \n```  \n'
    result = service._parse_gemini_response(response)
    assert result == {"success": True}


# ─── Validation ──────────────────────────────────────────────────────


def test_parse_non_object_response_returns_error(service):
    """Gemini might return a JSON array or scalar — both fail validation
    because we need a dict. Returns sanitized error (NOT raises)."""
    result = service._parse_gemini_response("[1, 2, 3]")
    assert result["success"] is False
    assert "error" in result


def test_parse_missing_success_field_returns_error(service):
    """JSON object missing the required 'success' field → fail validation."""
    result = service._parse_gemini_response('{"account_number": "12345"}')
    assert result["success"] is False
    assert "error" in result


# ─── Error paths (security-sensitive) ────────────────────────────────


def test_parse_invalid_json_returns_sanitized_error(service):
    """Malformed JSON ⇒ sanitized error dict. SECURITY: response_text
    must NOT leak into the error message (frontend would display it)."""
    response_text = "this is not json with potentially sensitive data <key>"
    result = service._parse_gemini_response(response_text)
    assert result["success"] is False
    assert response_text not in str(result)
    # Pinned sanitized message
    assert result["error"] == "Invalid response format."
    assert result["confidence"] == 0.0


def test_parse_runtime_error_returns_sanitized_error(service):
    """Exception inside parsing → generic 'Response processing error.'
    SECURITY: exception details (str(e)) must NOT leak into the
    response dict — pin so a future refactor doesn't accidentally
    add 'detail: str(e)'."""

    class _BadString:
        def strip(self):
            raise RuntimeError("internal-secret-stack-trace-info")

    result = service._parse_gemini_response(_BadString())  # type: ignore[arg-type]
    assert result["success"] is False
    # Sanitized message — exception detail NOT exposed.
    assert "internal-secret" not in str(result)
    assert result["error"] == "Response processing error."
