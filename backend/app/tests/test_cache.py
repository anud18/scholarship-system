"""Unit tests for app.core.cache.

Reuses the FakeRedis pattern from test_rate_limiting_unit.py — we deliberately
do NOT add the `fakeredis` package to dependencies. The shape needed is small:
get/set/scan/delete/eval/expiry-aware NX SET. ~80 lines.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import pytest
from pydantic import BaseModel

from app.core import cache as cache_mod


class FakeAsyncRedis:
    """Minimal in-memory async Redis for tests. Implements just the
    operations cache.py touches."""

    def __init__(self) -> None:
        self._store: dict[bytes, tuple[bytes, Optional[float]]] = {}  # key → (value, expires_at)
        self.fail_next: Optional[Exception] = None  # arm to make next op raise

    def _expired(self, key: bytes) -> bool:
        entry = self._store.get(key)
        if entry is None:
            return True
        _, exp = entry
        return exp is not None and exp < time.time()

    async def get(self, key: bytes):
        if self.fail_next:
            exc, self.fail_next = self.fail_next, None
            raise exc
        if self._expired(key):
            self._store.pop(key, None)
            return None
        return self._store[key][0]

    async def set(self, key: bytes, value: bytes, ex: Optional[int] = None, nx: bool = False, **_):
        if self.fail_next:
            exc, self.fail_next = self.fail_next, None
            raise exc
        if nx and not self._expired(key) and key in self._store:
            return None  # NX fails when key exists
        self._store[key] = (value, time.time() + ex if ex else None)
        return True

    async def delete(self, *keys: bytes):
        n = 0
        for k in keys:
            if self._store.pop(k, None) is not None:
                n += 1
        return n

    async def scan(self, cursor: int = 0, match: bytes = b"*", count: int = 100):
        pattern = match.decode("utf-8") if isinstance(match, bytes) else match
        # Naive glob implementation: only support trailing '*'
        prefix = pattern[:-1].encode("utf-8") if pattern.endswith("*") else pattern.encode("utf-8")
        # Live-key filter so expired entries don't leak.
        matched = [k for k in list(self._store.keys()) if k.startswith(prefix) and not self._expired(k)]
        return 0, matched

    async def eval(self, script: str, numkeys: int, *keys_and_args):
        # Implement just the release-Lua: check token equals expected, del if so.
        keys = keys_and_args[:numkeys]
        args = keys_and_args[numkeys:]
        key = keys[0] if isinstance(keys[0], bytes) else keys[0].encode("utf-8")
        expected = args[0] if isinstance(args[0], bytes) else args[0].encode("utf-8")
        if key in self._store and self._store[key][0] == expected:
            del self._store[key]
            return 1
        return 0


@pytest.fixture
def fake_redis(monkeypatch):
    """Replace the cache module's get_cache() with a FakeAsyncRedis singleton."""
    fake = FakeAsyncRedis()
    cache_mod.reset_clients_for_tests()
    monkeypatch.setattr(cache_mod, "get_cache", lambda: fake)
    yield fake
    cache_mod.reset_clients_for_tests()


# ---------------------------------------------------------------------------
# @cached
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cached_hits_after_first_call(fake_redis):
    calls = 0

    @cache_mod.cached(key_fn=lambda x, **_: f"sq:{x}", ttl=60, jitter=0)
    async def square(x):
        nonlocal calls
        calls += 1
        return {"x": x, "y": x * x}

    a = await square(7)
    b = await square(7)
    c = await square(8)

    assert a == {"x": 7, "y": 49}
    assert a == b
    assert c == {"x": 8, "y": 64}
    assert calls == 2  # cache hit on second 7


@pytest.mark.asyncio
async def test_cached_falls_through_on_redis_error(fake_redis):
    calls = 0

    @cache_mod.cached(key_fn=lambda **_: "boom", ttl=60, jitter=0)
    async def fn():
        nonlocal calls
        calls += 1
        return {"ok": True}

    fake_redis.fail_next = RuntimeError("redis down")
    result = await fn()  # GET fails, fall through to live function
    assert result == {"ok": True}
    assert calls == 1


@pytest.mark.asyncio
async def test_cached_handles_pydantic(fake_redis):
    class Item(BaseModel):
        name: str
        n: int

    @cache_mod.cached(key_fn=lambda **_: "items", ttl=60, jitter=0)
    async def get_items():
        return [Item(name="a", n=1), Item(name="b", n=2)]

    first = await get_items()
    second = await get_items()
    # Pydantic instance the first call; list of dicts on cache hit.
    assert isinstance(first, list)
    assert isinstance(second, list)
    assert second[0]["name"] == "a"
    assert second[1]["n"] == 2


# ---------------------------------------------------------------------------
# invalidate()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalidate_drops_matching_prefix(fake_redis):
    @cache_mod.cached(key_fn=lambda x, **_: f"fields:{x}", ttl=60, jitter=0)
    async def fetch(x):
        return {"x": x}

    @cache_mod.cached(key_fn=lambda **_: "refdata:all", ttl=60, jitter=0)
    async def fetch_all():
        return {"all": True}

    await fetch("nstc")
    await fetch("moe")
    await fetch_all()
    assert len(fake_redis._store) == 3

    deleted = await cache_mod.invalidate("fields:")
    assert deleted == 2
    # refdata key untouched
    assert any(b"refdata:all" in k for k in fake_redis._store.keys())


@pytest.mark.asyncio
async def test_invalidate_safe_when_redis_down(fake_redis):
    fake_redis.fail_next = RuntimeError("redis down")
    deleted = await cache_mod.invalidate("anything")
    assert deleted == 0  # no exception


# ---------------------------------------------------------------------------
# with_lock
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_lock_rejects_concurrent_acquirer(fake_redis):
    async def hold(seconds):
        async with cache_mod.with_lock("roster:42", ttl_seconds=10):
            await asyncio.sleep(seconds)

    holder = asyncio.create_task(hold(0.1))
    await asyncio.sleep(0.01)  # let holder acquire

    with pytest.raises(cache_mod.LockBusy):
        async with cache_mod.with_lock("roster:42", ttl_seconds=10):
            pass

    await holder

    # Lock released: a fresh acquire works
    async with cache_mod.with_lock("roster:42", ttl_seconds=10):
        pass


@pytest.mark.asyncio
async def test_with_lock_releases_on_exception(fake_redis):
    with pytest.raises(ValueError):
        async with cache_mod.with_lock("flaky", ttl_seconds=10):
            raise ValueError("oops")

    # Subsequent acquire succeeds — lock was released on context exit
    async with cache_mod.with_lock("flaky", ttl_seconds=10):
        pass
