"""
Tests for `ConfigManagementService` pure helpers: encryption + validation.

These don't need DB. They pin:
- `ConfigEncryption.encrypt_value` / `decrypt_value`: Fernet round-trip.
  A regression here would either corrupt secret config (DB rotation key,
  SMTP password, MinIO credentials) or fail to decrypt prior values.
- `ConfigurationService.validate_configuration`: data-type validation
  for each of the 5 supported types.

11 cases.
"""

import pytest

from app.models.system_setting import ConfigDataType
from app.services.config_management_service import ConfigEncryption, ConfigurationService

# ─── ConfigEncryption ────────────────────────────────────────────────


@pytest.fixture
def crypto():
    return ConfigEncryption()


def test_encrypt_decrypt_round_trip(crypto):
    """The end-to-end contract: encrypt(decrypt(x)) == x."""
    secret = "smtp-password-12345"
    encrypted = crypto.encrypt_value(secret)
    # Encrypted form is non-empty and NOT the plaintext.
    assert encrypted != secret
    assert len(encrypted) > 0
    # Round-trip recovers the original.
    assert crypto.decrypt_value(encrypted) == secret


def test_encrypt_handles_cjk(crypto):
    """UTF-8 inputs (CJK) round-trip cleanly."""
    secret = "密碼-測試-王小明"
    encrypted = crypto.encrypt_value(secret)
    assert crypto.decrypt_value(encrypted) == secret


def test_encrypt_handles_empty_string(crypto):
    """Empty string is a valid input — encrypt/decrypt should be a no-crash round-trip."""
    encrypted = crypto.encrypt_value("")
    assert crypto.decrypt_value(encrypted) == ""


def test_two_encryptions_of_same_value_are_different(crypto):
    """Fernet uses a fresh IV per encryption — same plaintext yields different ciphertexts."""
    secret = "rotation-test"
    e1 = crypto.encrypt_value(secret)
    e2 = crypto.encrypt_value(secret)
    # Different ciphertext but same plaintext after decryption.
    assert e1 != e2
    assert crypto.decrypt_value(e1) == secret
    assert crypto.decrypt_value(e2) == secret


# ─── ConfigurationService.validate_configuration ────────────────────


@pytest.fixture
def service():
    return ConfigurationService(db=None)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_validate_integer_accepts_int_strings(service):
    """Integer type accepts string representations of ints."""
    ok, _ = await service.validate_configuration("k", "42", ConfigDataType.integer)
    assert ok is True
    ok2, _ = await service.validate_configuration("k", "-17", ConfigDataType.integer)
    assert ok2 is True


@pytest.mark.asyncio
async def test_validate_integer_rejects_non_int(service):
    ok, err = await service.validate_configuration("k", "not-a-number", ConfigDataType.integer)
    assert ok is False
    assert "Validation error" in err


@pytest.mark.asyncio
async def test_validate_float_accepts_decimals(service):
    ok, _ = await service.validate_configuration("k", "3.14", ConfigDataType.float)
    assert ok is True


@pytest.mark.asyncio
async def test_validate_boolean_accepts_canonical_forms(service):
    """All of true/false, 1/0, yes/no, on/off (case-insensitive) are valid."""
    for v in ["true", "FALSE", "1", "0", "Yes", "no", "ON", "off"]:
        ok, _ = await service.validate_configuration("k", v, ConfigDataType.boolean)
        assert ok is True, f"expected {v!r} to validate"


@pytest.mark.asyncio
async def test_validate_boolean_rejects_garbage(service):
    ok, err = await service.validate_configuration("k", "maybe", ConfigDataType.boolean)
    assert ok is False
    assert "Boolean value must be" in err


@pytest.mark.asyncio
async def test_validate_json_accepts_valid_json(service):
    ok, _ = await service.validate_configuration("k", '{"a": 1, "b": [2, 3]}', ConfigDataType.json)
    assert ok is True


@pytest.mark.asyncio
async def test_validate_json_rejects_invalid_json(service):
    ok, err = await service.validate_configuration("k", "{not valid json", ConfigDataType.json)
    assert ok is False


@pytest.mark.asyncio
async def test_validate_string_accepts_anything(service):
    """String type has no validation — any value is OK."""
    ok, _ = await service.validate_configuration("k", "any text here, 任何文字", ConfigDataType.string)
    assert ok is True
