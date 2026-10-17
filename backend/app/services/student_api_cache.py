"""
Redis cache for raw SIS (學籍) API records.

Every entry is the raw SIS record (before academy normalization) or ``None``
for an empty answer (403 無資料 / 404), wrapped as ``{"d": record}`` and
AES-GCM encrypted with ``pii_crypto`` — the records carry 身分證 and contact
details, and production Redis persists to disk.

Errors (timeouts, 5xx) are never cached. Any Redis or crypto failure counts
as a miss, so a Redis outage only means "no cache", never "no data".
Flush everything with ``await invalidate_student_api_cache()``.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional, Tuple

from app.core.cache import KEY_PREFIX, get_cache, invalidate
from app.core.config import settings
from app.core.pii_crypto import decrypt_pii, encrypt_pii

logger = logging.getLogger(__name__)

CACHE_NAMESPACE = "sis:"


def basic_key(student_code: str) -> str:
    return f"{CACHE_NAMESPACE}basic:{student_code}"


def term_key(student_code: str, academic_year: str, term: str) -> str:
    return f"{CACHE_NAMESPACE}term:{student_code}:{academic_year}:{term}"


def _redis_key(key: str) -> bytes:
    return (KEY_PREFIX + key).encode("utf-8")


async def get_cached_record(key: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Return ``(hit, record)``; ``(True, None)`` is a cached empty answer."""
    if not settings.student_api_cache_enabled:
        return False, None

    try:
        blob = await get_cache().get(_redis_key(key))
    except Exception:  # noqa: BLE001
        logger.warning("SIS cache GET failed for %s; falling through to the API", key, exc_info=True)
        return False, None

    if blob is None:
        return False, None

    try:
        payload = json.loads(decrypt_pii(blob.decode("utf-8")))
        return True, payload["d"]
    except Exception:  # noqa: BLE001
        # Corrupt entry or rotated-out key: drop it and refetch
        logger.warning("SIS cache entry %s unreadable; refetching", key, exc_info=True)
        try:
            await get_cache().delete(_redis_key(key))
        except Exception:  # noqa: BLE001
            logger.warning("SIS cache DEL failed for %s", key, exc_info=True)
        return False, None


async def set_cached_record(key: str, record: Optional[Dict[str, Any]]) -> None:
    """Store a record (TTL ``student_api_cache_ttl``) or an empty answer (``student_api_negative_cache_ttl``)."""
    if not settings.student_api_cache_enabled:
        return

    ttl = settings.student_api_cache_ttl if record is not None else settings.student_api_negative_cache_ttl
    try:
        envelope = encrypt_pii(json.dumps({"d": record}, ensure_ascii=False, separators=(",", ":")))
        await get_cache().set(_redis_key(key), envelope.encode("utf-8"), ex=ttl)
    except Exception:  # noqa: BLE001
        logger.warning("SIS cache SET failed for %s; not cached", key, exc_info=True)


async def invalidate_student_api_cache(student_code: Optional[str] = None) -> int:
    """Drop cached SIS records — all of them, or only one student's."""
    if student_code is None:
        return await invalidate(CACHE_NAMESPACE)

    # invalidate() matches by prefix, so the basic key (no trailing ":") is deleted
    # exactly — otherwise "E1234" would also drop "E12345".
    try:
        deleted = await get_cache().delete(_redis_key(basic_key(student_code)))
    except Exception:  # noqa: BLE001
        logger.warning("SIS cache DEL failed for %s", student_code, exc_info=True)
        deleted = 0
    return deleted + await invalidate(f"{CACHE_NAMESPACE}term:{student_code}:")
