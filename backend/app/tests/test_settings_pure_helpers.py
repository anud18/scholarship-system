"""
Pure-helper tests for `app.core.config.Settings`.

These pre-validators run BEFORE Pydantic field assignment, so they're
testable as classmethods without instantiating Settings (which would
pull from .env / env vars). The parse_* validators normalize list-vs-str
input for CSV-style config fields.

Bugs cause:
- parse_cors_origins returns wrong default → CORS-blocked frontend
  in dev (no localhost:3000)
- parse_allowed_file_types returns wrong default → uploads rejected
- cors_origins_list strip bug → trailing-comma in env var yields
  empty-string origin (browser CORS preflight fails)
- MIME_TYPE_MAPPING typo → file uploads served as octet-stream

3 validators + 1 module constant (10 cases). Pure, no DB.
"""

from app.core.config import MIME_TYPE_MAPPING, Settings

# ─── parse_cors_origins ──────────────────────────────────────────────


def test_parse_cors_origins_list_joined():
    """Pin: list input joined with comma (CSV format expected by
    downstream Pydantic field)."""
    assert Settings.parse_cors_origins(["http://a", "http://b"]) == "http://a,http://b"


def test_parse_cors_origins_empty_falls_back_to_localhost_3000():
    """Pin: None/empty → 'http://localhost:3000' default. Otherwise
    dev environment has no CORS allowlist and frontend can't call API."""
    assert Settings.parse_cors_origins(None) == "http://localhost:3000"
    assert Settings.parse_cors_origins("") == "http://localhost:3000"


def test_parse_cors_origins_string_passed_through():
    """Pin: already-string input passes through unchanged."""
    assert Settings.parse_cors_origins("http://prod.example.com") == "http://prod.example.com"


# ─── parse_allowed_file_types ────────────────────────────────────────


def test_parse_allowed_file_types_list_joined():
    """Pin: list input joined with comma."""
    assert Settings.parse_allowed_file_types(["pdf", "jpg"]) == "pdf,jpg"


def test_parse_allowed_file_types_default():
    """Pin: None/empty → 'pdf,jpg,jpeg,png,doc,docx' default. These
    are the 6 document types the upload validator accepts."""
    assert Settings.parse_allowed_file_types(None) == "pdf,jpg,jpeg,png,doc,docx"
    assert Settings.parse_allowed_file_types("") == "pdf,jpg,jpeg,png,doc,docx"


# ─── validate_time_restrictions_bypass ───────────────────────────────


def test_bypass_time_restrictions_string_coercion():
    """Pin: string 'true'/'1'/'yes'/'on' → True. Defensive against env
    vars (which are always strings)."""
    # PYTEST_CURRENT_TEST is set by pytest, so the bypass guard passes
    for truthy in ("true", "True", "1", "yes", "on"):
        assert Settings.validate_time_restrictions_bypass(truthy) is True


def test_bypass_time_restrictions_string_falsy():
    """Pin: anything not in the truthy set → False."""
    for falsy in ("false", "0", "no", "off", ""):
        assert Settings.validate_time_restrictions_bypass(falsy) is False


# ─── MIME_TYPE_MAPPING ───────────────────────────────────────────────


def test_mime_type_mapping_pdf():
    """Pin: PDF mime is application/pdf. The upload preview endpoint
    uses this exact string in Content-Type response header."""
    assert MIME_TYPE_MAPPING["pdf"] == "application/pdf"


def test_mime_type_mapping_image_variants():
    """Pin: jpg/jpeg/png all mapped. jpg and jpeg both map to image/jpeg
    (admin uploads may use either extension)."""
    assert MIME_TYPE_MAPPING["jpg"] == "image/jpeg"
    assert MIME_TYPE_MAPPING["jpeg"] == "image/jpeg"
    assert MIME_TYPE_MAPPING["png"] == "image/png"


def test_mime_type_mapping_office_docs():
    """Pin: doc/docx office-document mimes. CRITICAL: the docx mime is
    the long openxmlformats variant — browsers won't preview it as
    Word unless served with this exact string."""
    assert MIME_TYPE_MAPPING["doc"] == "application/msword"
    assert MIME_TYPE_MAPPING["docx"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
