"""
Pure-function tests for `StudentService` helpers.

This service is the bridge to the NYCU student-information API. The
HMAC header signs every outbound request — a bug there means *every*
API call fails authentication, which kills the application
submission flow silently from a student-facing perspective.

4 helpers covered (12 cases):
- `_generate_hmac_auth_header`  : HMAC-SHA256 signature shape
- `get_student_type_from_data`  : degree code → 'phd' | 'master' | 'undergraduate'
- `determine_student_api_type`  : currently always 'student' (regression guard)
- `is_api_available`            : reflects self.api_enabled
"""

import hashlib
import hmac
import re

import pytest

from app.services.student_service import StudentService


@pytest.fixture
def service():
    """StudentService.__init__ reads settings; in test envs api_enabled is
    False by default. Override the auth fields directly for the HMAC test
    to be deterministic."""
    s = StudentService()
    s.api_account = "test-account"
    s.hmac_key = bytes.fromhex("0011223344556677" * 4)  # 32-byte key
    return s


# ─── _generate_hmac_auth_header ──────────────────────────────────────


def test_hmac_header_format(service):
    """Header is 'HMAC-SHA256:{14-digit-timestamp}:{account}:{64-hex-signature}'."""
    header = service._generate_hmac_auth_header('{"a":1}')
    assert header.startswith("HMAC-SHA256:")
    parts = header.split(":")
    # Scheme : timestamp : account : signature → 4 segments
    assert len(parts) == 4
    assert parts[0] == "HMAC-SHA256"
    assert re.match(r"^\d{14}$", parts[1]), f"timestamp not YYYYMMDDHHMMSS: {parts[1]}"
    assert parts[2] == "test-account"
    assert re.match(r"^[0-9a-f]{64}$", parts[3]), f"signature not 64-hex: {parts[3]}"


def test_hmac_signature_matches_manual_recompute(service):
    """Sanity check: re-derive the signature against the same timestamp
    and confirm equality — pins the algorithm (SHA256, hex lowercase)
    and the message format (timestamp + body)."""
    body = '{"action":"qrySoaaScholarshipStudent","stdcode":"123"}'
    header = service._generate_hmac_auth_header(body)
    _, time_str, _, signature = header.split(":")

    expected = hmac.new(service.hmac_key, (time_str + body).encode("utf-8"), hashlib.sha256).hexdigest().lower()
    assert signature == expected


def test_hmac_different_bodies_produce_different_signatures(service):
    """Different request bodies must produce different signatures (sanity
    check that the body actually feeds into the HMAC, not just the key)."""
    sig1 = service._generate_hmac_auth_header('{"a":1}').split(":")[3]
    sig2 = service._generate_hmac_auth_header('{"a":2}').split(":")[3]
    assert sig1 != sig2


# ─── get_student_type_from_data ──────────────────────────────────────


def test_student_type_phd(service):
    """std_degree '1' ⇒ phd."""
    assert service.get_student_type_from_data({"std_degree": "1"}) == "phd"


def test_student_type_master(service):
    """std_degree '2' ⇒ master."""
    assert service.get_student_type_from_data({"std_degree": "2"}) == "master"


def test_student_type_undergraduate_default(service):
    """std_degree '3' or anything else ⇒ undergraduate (the SIS default)."""
    assert service.get_student_type_from_data({"std_degree": "3"}) == "undergraduate"
    assert service.get_student_type_from_data({"std_degree": "9"}) == "undergraduate"


def test_student_type_missing_field_defaults_to_undergraduate(service):
    """Missing std_degree key ⇒ falls back via .get default '3' ⇒ undergraduate.
    Don't blow up — just degrade to the largest student segment."""
    assert service.get_student_type_from_data({}) == "undergraduate"


# ─── determine_student_api_type ──────────────────────────────────────


def test_determine_api_type_returns_student_for_none_config(service):
    """Current behavior is 'always student'. This test pins that contract so
    a regression to 'student_term' surfaces immediately (would break the API
    call signature in get_student_data_by_type)."""
    assert service.determine_student_api_type(None) == "student"


def test_determine_api_type_returns_student_for_any_config(service):
    """Even with a config object passed, it returns 'student' until the
    config-driven branch (commented-out) is enabled."""

    class _FakeConfig:
        requires_term_data = True

    assert service.determine_student_api_type(_FakeConfig()) == "student"


# ─── is_api_available ────────────────────────────────────────────────


def test_is_api_available_reflects_api_enabled(service):
    service.api_enabled = True
    assert service.is_api_available() is True

    service.api_enabled = False
    assert service.is_api_available() is False
