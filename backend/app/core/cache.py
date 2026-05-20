"""
Redis-backed cache + distributed-lock helper.

Mirrors the singleton pattern of `app.core.rate_limiting.get_rate_limiter` so
the same connection wiring + fail-open semantics apply.

Usage:

    from app.core.cache import cached, invalidate

    @cached(key_fn=lambda scholarship_type, **_: f"fields:{scholarship_type}",
            ttl=86400)
    async def get_fields(scholarship_type: str, db=Depends(...), ...):
        ...

    # Later, after a write:
    await invalidate("fields:")            # any prefix; uses SCAN + DEL

    async with with_lock("roster:42:2025-1", ttl_seconds=300):
        ...

Notes for future maintainers:
  • Cached values must be JSON-serialisable. Pydantic ``BaseModel`` is
    handled transparently via ``.model_dump()``; datetime/date via
    ``.isoformat()``. SQLAlchemy ORM rows are NOT supported — call
    ``.model_dump()`` or convert to a plain dict before returning. This
    avoids the lazy-loaded-relationship gotcha that bites pickle.
  • Manual ``psql UPDATE`` outside the app does NOT trigger
    invalidation. Run ``redis-cli --scan --pattern 'cache:v1:*' | xargs
    redis-cli del`` after direct DB surgery, or just bump ``KEY_PREFIX``.
  • Any Redis error falls through to the source-of-truth (cache miss
    counts as fail-open). A Redis outage degrades the app to "no cache,"
    not "site down."
"""

from __future__ import annotations

import json
import logging
import random
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import date, datetime
from decimal import Decimal
from functools import wraps
from typing import Any, Awaitable, Callable, Optional

import redis.asyncio as redis_async
import redis as redis_sync

logger = logging.getLogger(__name__)

# Bump this to invalidate the entire cache namespace in one shot
# (deploy a new prefix and the old keys become orphaned, evicted by LRU).
KEY_PREFIX = "cache:v1:"

_async_client: Optional[redis_async.Redis] = None
_sync_client: Optional[redis_sync.Redis] = None


def _redis_url() -> str:
    """Resolve at call time so test fixtures can monkeypatch settings."""
    from app.core.config import settings

    return settings.redis_url


def get_cache() -> redis_async.Redis:
    """Lazy async Redis client. Mirrors ``rate_limiting.get_rate_limiter``."""
    global _async_client
    if _async_client is None:
        _async_client = redis_async.from_url(_redis_url(), decode_responses=False)
    return _async_client


def get_cache_sync() -> redis_sync.Redis:
    """Lazy sync Redis client (used by sync-only endpoints; PR 3 path)."""
    global _sync_client
    if _sync_client is None:
        _sync_client = redis_sync.from_url(_redis_url(), decode_responses=False)
    return _sync_client


def reset_clients_for_tests() -> None:
    """Drop the singletons. Used by tests to swap in a FakeRedis."""
    global _async_client, _sync_client
    _async_client = None
    _sync_client = None


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def _default(obj: Any) -> Any:
    """JSON encoder fallback for the types our app actually returns."""
    if hasattr(obj, "model_dump"):  # Pydantic v2 BaseModel
        return obj.model_dump()
    if hasattr(obj, "dict") and callable(obj.dict):  # Pydantic v1 BaseModel
        return obj.dict()
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, set):
        return list(obj)
    raise TypeError(f"Cache value not JSON-serialisable: {type(obj).__name__}")


def _dumps(value: Any) -> bytes:
    return json.dumps(value, default=_default, separators=(",", ":")).encode("utf-8")


def _loads(blob: bytes) -> Any:
    return json.loads(blob)


# ---------------------------------------------------------------------------
# @cached decorator
# ---------------------------------------------------------------------------


def cached(key_fn: Callable[..., str], ttl: int, jitter: float = 0.1):
    """Cache the return value of an async function in Redis.

    Args:
        key_fn:    callable(*args, **kwargs) → str. Returns the suffix
                   appended to ``KEY_PREFIX``. Should ignore Depends-injected
                   args (db, current_user, response) — typically with ``**_``.
        ttl:       seconds. Effective expiry has ±``jitter`` randomisation
                   to avoid stampedes when a hot key expires.
        jitter:    fraction of ``ttl`` to randomly add/subtract (default
                   10 %). Set to 0 for deterministic TTL in tests.
    """

    def decorator(fn: Callable[..., Awaitable[Any]]):
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any):
            try:
                client = get_cache()
                key = (KEY_PREFIX + key_fn(*args, **kwargs)).encode("utf-8")
            except TypeError as exc:
                # Most common cause: key_fn signature doesn't accept the
                # positional/keyword args the wrapped function receives.
                # E.g. `lambda **_:` rejects positional. Surface loudly so
                # the bug doesn't masquerade as "cache silently disabled".
                logger.error(
                    "cache: key_fn for %s rejected its args (%s) — " "caching disabled for this call. Fix the lambda.",
                    fn.__qualname__,
                    exc,
                )
                return await fn(*args, **kwargs)
            except Exception:  # noqa: BLE001
                # Redis init failure: fail open, retry on next call.
                logger.warning("cache: key build / redis init failed", exc_info=True)
                return await fn(*args, **kwargs)

            # Lookup
            try:
                hit = await client.get(key)
            except Exception:  # noqa: BLE001
                logger.warning("cache: GET failed; falling through", exc_info=True)
                return await fn(*args, **kwargs)

            if hit is not None:
                try:
                    return _loads(hit)
                except Exception:  # noqa: BLE001
                    # Corrupt cache entry — drop it and recompute.
                    logger.warning("cache: parse failed; recomputing", exc_info=True)
                    try:
                        await client.delete(key)
                    except Exception:
                        pass

            # Miss: compute + store
            value = await fn(*args, **kwargs)
            try:
                ttl_actual = max(1, int(ttl * (1 + random.uniform(-jitter, jitter))))
                await client.set(key, _dumps(value), ex=ttl_actual)
            except TypeError as exc:
                # Value isn't serialisable — log loudly so devs notice and
                # convert to dict, but still return the live value.
                logger.error(
                    "cache: value for key=%s is not JSON-serialisable: %s",
                    key,
                    exc,
                )
            except Exception:  # noqa: BLE001
                logger.warning("cache: SET failed; not cached", exc_info=True)
            return value

        return wrapper

    return decorator


async def invalidate(prefix: str) -> int:
    """Delete every key matching ``KEY_PREFIX + prefix + *``.

    Uses SCAN, not KEYS, so it's safe in production. Returns the number
    of keys deleted (best-effort; 0 on Redis error).
    """
    try:
        client = get_cache()
    except Exception:  # noqa: BLE001
        logger.warning("invalidate: redis init failed", exc_info=True)
        return 0

    pattern = (KEY_PREFIX + prefix + "*").encode("utf-8")
    cursor = 0
    deleted = 0
    try:
        while True:
            cursor, keys = await client.scan(cursor=cursor, match=pattern, count=500)
            if keys:
                deleted += await client.delete(*keys)
            if cursor == 0:
                break
    except Exception:  # noqa: BLE001
        logger.warning("invalidate: SCAN/DEL failed for %r", pattern, exc_info=True)
    return deleted


# ---------------------------------------------------------------------------
# Distributed lock (SET NX EX)
# ---------------------------------------------------------------------------


class LockBusy(RuntimeError):
    """Raised when ``with_lock`` cannot acquire the lock immediately."""

    def __init__(self, key: str):
        super().__init__(f"lock busy: {key}")
        self.key = key


# Lua so check-and-del is atomic; otherwise a stale lock holder could
# delete someone else's freshly-acquired lock if its TTL elapsed mid-op.
_RELEASE_LUA = (
    "if redis.call('get', KEYS[1]) == ARGV[1] then " "  return redis.call('del', KEYS[1]) " "else " "  return 0 " "end"
)


@asynccontextmanager
async def with_lock(key: str, ttl_seconds: int = 60):
    """Acquire a distributed mutex via SET NX EX.

    Raises ``LockBusy`` if the key is already held. Releases on exit if
    we still own the token (atomic Lua check-and-del).

    Designed for "prevent the same expensive operation from running
    twice concurrently" — e.g. payment-roster generation. NOT a
    fairness primitive; competing callers fail fast rather than wait.
    """
    client = get_cache()
    token = uuid.uuid4().hex.encode("utf-8")
    full = (KEY_PREFIX + "lock:" + key).encode("utf-8")
    acquired = await client.set(full, token, nx=True, ex=ttl_seconds)
    if not acquired:
        raise LockBusy(full.decode("utf-8"))
    try:
        yield token.decode("utf-8")
    finally:
        try:
            await client.eval(_RELEASE_LUA, 1, full, token)
        except Exception:  # noqa: BLE001
            logger.warning("with_lock: release failed for %s", key, exc_info=True)


@contextmanager
def with_lock_sync(key: str, ttl_seconds: int = 60):
    """Sync sibling of ``with_lock``. Same semantics; for sync endpoints
    (e.g. the payment-roster generator that uses get_sync_db)."""
    client = get_cache_sync()
    token = uuid.uuid4().hex.encode("utf-8")
    full = (KEY_PREFIX + "lock:" + key).encode("utf-8")
    acquired = client.set(full, token, nx=True, ex=ttl_seconds)
    if not acquired:
        raise LockBusy(full.decode("utf-8"))
    try:
        yield token.decode("utf-8")
    finally:
        try:
            client.eval(_RELEASE_LUA, 1, full, token)
        except Exception:  # noqa: BLE001
            logger.warning("with_lock_sync: release failed for %s", key, exc_info=True)


__all__ = [
    "cached",
    "invalidate",
    "with_lock",
    "with_lock_sync",
    "LockBusy",
    "get_cache",
    "get_cache_sync",
    "reset_clients_for_tests",
    "KEY_PREFIX",
]
