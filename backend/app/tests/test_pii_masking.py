"""Unit tests for ``app.utils.pii_masking``.

These pin the backend national-ID (身分證字號) masking to be byte-for-byte
identical to the frontend ``maskIdNumber`` helper
(``frontend/lib/utils/mask.ts``). Masking now happens at the API response
boundary, so the full plaintext national ID never leaves the server for
display-only endpoints. The transform must also be idempotent so the frontend
mask (still applied as defense in depth) does not corrupt an already-masked
value.
"""

from app.utils.pii_masking import mask_id_number


def test_keeps_first_char_and_last_three_for_typical_10_char_id():
    assert mask_id_number("A123456789") == "A******789"
    assert mask_id_number("F229876543") == "F******543"


def test_masks_middle_for_other_lengths():
    assert mask_id_number("AB12345") == "A***345"
    assert mask_id_number("A1234") == "A*234"


def test_keeps_only_first_char_for_four_or_fewer():
    assert mask_id_number("ABCD") == "A***"
    assert mask_id_number("ABC") == "A**"
    assert mask_id_number("AB") == "A*"
    assert mask_id_number("A") == "A"


def test_empty_or_missing_values_return_empty_string():
    assert mask_id_number("") == ""
    assert mask_id_number(None) == ""


def test_trims_surrounding_whitespace_before_masking():
    assert mask_id_number("  A123456789  ") == "A******789"
    assert mask_id_number("   ") == ""


def test_idempotent_on_already_masked_value():
    once = mask_id_number("A123456789")
    assert mask_id_number(once) == once == "A******789"
