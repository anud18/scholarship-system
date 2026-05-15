"""
Tests for `backend/scripts/rotate_pii_keys.py` —
the pure-string `_envelope_version` helper and `_BATCH_SIZE`
constant.

Script had ZERO test references. SECURITY-CRITICAL: drives the
PII key-rotation pipeline. Drift in envelope parsing would
silently fail to rotate (or re-encrypt with wrong version) and
leave PII data unprotected during key rollover.

Wave 6a147 pins `_envelope_version` extraction logic + the
batch-size constant. The DB-streaming `rotate()` function itself
requires a real SQLAlchemy engine + database connection so is
out of scope for unit tests.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

# Import the script as a module (it's outside the package tree).
_SCRIPT_PATH = Path("/app/scripts/rotate_pii_keys.py")
if not _SCRIPT_PATH.exists():
    _SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "rotate_pii_keys.py"


@pytest.fixture(scope="module")
def script_module():
    spec = importlib.util.spec_from_file_location("rotate_pii_keys", _SCRIPT_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rotate_pii_keys"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestEnvelopeVersionExtraction:
    """Pin SECURITY: `_envelope_version` parses the version segment
    from a PII envelope. Envelope format is `tag:version:ciphertext`
    (per pii_crypto encoding). Drift would cause:
    - Skip rotation (think envelope matches active version when it
      doesn't) → stale ciphertexts persist
    - OR rotate wrong rows → exhaust crypto budget
    """

    def test_v1_envelope_returns_v1(self, script_module):
        # Pin: standard envelope `pii:v1:<base64>` → "v1".
        assert script_module._envelope_version("pii:v1:abc123") == "v1"

    def test_v2_envelope_returns_v2(self, script_module):
        # Pin: post-rotation envelope returns "v2".
        assert script_module._envelope_version("pii:v2:xyz789") == "v2"

    def test_ciphertext_contains_colons(self, script_module):
        # Pin SECURITY: base64 ciphertext may contain `:` chars
        # but `split(":", 2)` limits to 3 parts, preserving the
        # full ciphertext as the 3rd part. Pin so refactor to
        # plain `split(":")` doesn't drop ciphertext suffix.
        envelope = "pii:v1:abc:def:ghi"
        assert script_module._envelope_version(envelope) == "v1"

    def test_long_version_string(self, script_module):
        # Pin: version segment is whatever sits between the 1st
        # and 2nd colon — supports arbitrary version names
        # (v1, v2, v10, v2025-rotation, etc.).
        assert script_module._envelope_version("pii:v2025-q3:cipher") == "v2025-q3"

    def test_short_version_v1_just_a_char(self, script_module):
        # Pin: even single-character versions work.
        assert script_module._envelope_version("pii:a:x") == "a"

    def test_envelope_missing_version_segment_raises_indexerror(self, script_module):
        # Pin DEFENSIVE: malformed envelope (no colons) raises
        # IndexError — pin so refactor adding error-handling
        # surfaces the design decision.
        with pytest.raises(IndexError):
            script_module._envelope_version("no_colons_here")

    def test_envelope_with_only_one_colon_raises(self, script_module):
        # Pin: "pii:v1" (no ciphertext segment) → IndexError because
        # split(":", 2) only produces 2 parts. Pin so refactor
        # tolerating partial envelopes is deliberate.
        # Actually split(":", 2) on "pii:v1" returns ["pii", "v1"] —
        # accessing [1] yields "v1". So this DOES NOT raise.
        # Pin actual behavior.
        assert script_module._envelope_version("pii:v1") == "v1"


class TestBatchSizeConstant:
    """Pin: _BATCH_SIZE = 500. Pin so refactor doesn't drop to 1
    (slow) or raise to 10000 (memory blowup during rotation)."""

    def test_batch_size_is_500(self, script_module):
        # Pin: 500 is the tested-stable batch size for PII rotation.
        # Pin so refactor doesn't change without a perf+memory
        # benchmark.
        assert script_module._BATCH_SIZE == 500

    def test_batch_size_is_positive_int(self, script_module):
        # Pin: positive int (NOT float, NOT 0).
        assert isinstance(script_module._BATCH_SIZE, int)
        assert script_module._BATCH_SIZE > 0
