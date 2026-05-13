"""
Tests for `app.core.dynamic_config.DynamicConfig`.

This service is the single point of truth for "is this config
runtime-modifiable" vs "needs a restart". A regression here either:
- Adds a secret key to DYNAMIC_CONFIGS → admins accidentally store
  it in plaintext DB (security leak)
- Removes a real dynamic config → admin UI thinks SMTP settings need
  restart, gates the config form
- Type coercion `get_bool/get_int` returns wrong value → SMTP TLS off
  when it should be on, etc.

Pin: STATIC_CONFIGS is the safety net for secret_key / database_url /
SECRET keys. Any new key added to DYNAMIC_CONFIGS must NOT also be in
STATIC_CONFIGS (would be ambiguous).

Methods covered:
- `is_dynamic`, `is_static` — set membership
- `get_bool`, `get_int`, `get_float`, `get_str`, `get_list` — type
  coercion paths (without DB by overriding `get`)

8 helpers (24 cases). Pure, no DB touched.
"""

import pytest

from app.core.dynamic_config import DynamicConfig

# ─── is_dynamic / is_static ──────────────────────────────────────────


def test_is_dynamic_for_smtp_config():
    """Pin: SMTP settings are dynamic (admin can change without restart)."""
    cfg = DynamicConfig()
    assert cfg.is_dynamic("smtp_host") is True
    assert cfg.is_dynamic("smtp_port") is True
    assert cfg.is_dynamic("smtp_password") is True


def test_is_dynamic_false_for_unknown_key():
    cfg = DynamicConfig()
    assert cfg.is_dynamic("nonexistent_key") is False


def test_is_static_for_secret_keys():
    """SECURITY-CRITICAL: secret_key, database_url, MinIO credentials
    MUST be static (require restart). Pin so they never accidentally
    move to DYNAMIC_CONFIGS (which would let admins store them in DB
    plaintext through the config UI)."""
    cfg = DynamicConfig()
    for static_key in (
        "secret_key",
        "database_url",
        "database_url_sync",
        "algorithm",
        "minio_secret_key",
        "minio_access_key",
        "redis_url",
        "virus_scan_api_key",
    ):
        assert cfg.is_static(static_key) is True, f"{static_key} must be static"


def test_no_overlap_between_dynamic_and_static_sets():
    """SECURITY-CRITICAL: a key being in BOTH sets is a config-bug —
    'get' would treat it as dynamic (DB-backed) but is_static() also
    returns True (confusing UI). Pin the partition invariant."""
    cfg = DynamicConfig()
    overlap = cfg.DYNAMIC_CONFIGS & cfg.STATIC_CONFIGS
    assert overlap == set(), f"keys in both DYNAMIC and STATIC: {overlap}"


def test_database_url_not_in_dynamic_configs():
    """Pin explicit guard: database_url MUST NOT be dynamic — otherwise
    a misconfigured admin UI could swap the prod DB connection string
    at runtime."""
    cfg = DynamicConfig()
    assert cfg.is_dynamic("database_url") is False
    assert cfg.is_dynamic("secret_key") is False


# ─── Type coercion (bypass DB via subclass override) ─────────────────


class _StubConfig(DynamicConfig):
    """Subclass that lets tests inject the `get` return value without DB."""

    def __init__(self, stub_value):
        self._stub_value = stub_value

    async def get(self, key, db, default=None):
        return self._stub_value


# ─── get_bool ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_bool_true_string_variants():
    """Pin: 'true' / '1' / 'yes' / 'on' (lowercase-coerced) → True.
    A regression that breaks one variant would make 'TRUE' from .env
    silently evaluate to False."""
    for truthy in ("true", "True", "TRUE", "1", "yes", "Yes", "on", "ON"):
        cfg = _StubConfig(truthy)
        assert await cfg.get_bool("k", None) is True, f"failed for {truthy!r}"


@pytest.mark.asyncio
async def test_get_bool_false_string_variants():
    """Pin: anything not in the truthy set → False (NOT None).
    Don't accidentally let 'on ' (trailing space) be True or 'OFF' be True."""
    for falsy in ("false", "0", "no", "off", "anything-else", "on "):  # trailing space ≠ on
        cfg = _StubConfig(falsy)
        assert await cfg.get_bool("k", None) is False, f"failed for {falsy!r}"


@pytest.mark.asyncio
async def test_get_bool_passes_through_actual_bool():
    """Pin: actual bool values returned by .env-loader pass through."""
    assert await _StubConfig(True).get_bool("k", None) is True
    assert await _StubConfig(False).get_bool("k", None) is False


@pytest.mark.asyncio
async def test_get_bool_none_returns_none():
    """Pin: None → None (not False). Otherwise bool(None) → False which
    might be the WRONG default for an unset flag. Caller can distinguish
    'not set' from 'explicitly False' via this None return."""
    cfg = _StubConfig(None)
    assert await cfg.get_bool("k", None) is None


# ─── get_int / get_float ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_int_coerces_string_to_int():
    """Pin: '8080' → 8080 int. Defends against bare string from DB."""
    assert await _StubConfig("8080").get_int("k", None) == 8080


@pytest.mark.asyncio
async def test_get_int_none_returns_none():
    """Pin: None → None. Otherwise int(None) raises TypeError."""
    assert await _StubConfig(None).get_int("k", None) is None


@pytest.mark.asyncio
async def test_get_float_coerces_string():
    assert await _StubConfig("3.14").get_float("k", None) == 3.14


@pytest.mark.asyncio
async def test_get_float_none_returns_none():
    """Pin: None → None (otherwise float(None) raises)."""
    assert await _StubConfig(None).get_float("k", None) is None


# ─── get_str ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_str_coerces_int_to_str():
    """Pin: int → str (defends against DB returning bare numbers)."""
    assert await _StubConfig(42).get_str("k", None) == "42"


@pytest.mark.asyncio
async def test_get_str_none_returns_none_not_string_None():
    """SECURITY-ADJACENT: pin None → None (literal). Without the guard,
    str(None) would produce the literal string 'None' which is a
    classic source of bugs (SMTP host literally 'None', etc.)."""
    cfg = _StubConfig(None)
    result = await cfg.get_str("k", None)
    assert result is None
    assert result != "None"


# ─── get_list ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_list_already_list_returns_unchanged():
    """Pin: existing list passes through (no double-split)."""
    cfg = _StubConfig(["a", "b", "c"])
    assert await cfg.get_list("k", None) == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_get_list_csv_split_with_default_separator():
    """Pin: comma-separated string → list, trimmed."""
    cfg = _StubConfig("a, b , c")
    assert await cfg.get_list("k", None) == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_get_list_custom_separator():
    """Pin: separator parameter respected."""
    cfg = _StubConfig("a|b|c")
    assert await cfg.get_list("k", None, separator="|") == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_get_list_empty_string_yields_empty_list():
    """Pin: '' → []. Defends against an unset env var becoming [""]."""
    cfg = _StubConfig("")
    assert await cfg.get_list("k", None) == []


@pytest.mark.asyncio
async def test_get_list_none_returns_empty_list():
    """Pin: None → []. Useful for 'no entries configured' default."""
    cfg = _StubConfig(None)
    assert await cfg.get_list("k", None) == []


@pytest.mark.asyncio
async def test_get_list_strips_whitespace_only_items():
    """Pin: 'a, ,b' → ['a', 'b']. Empty/whitespace items dropped."""
    cfg = _StubConfig("a, ,b, , ,c")
    assert await cfg.get_list("k", None) == ["a", "b", "c"]
