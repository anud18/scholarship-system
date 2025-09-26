import asyncio
import sys
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, status

from app.core import rate_limiting


class FakePipeline:
    def __init__(self, results):
        self.results = results
        self.commands = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def zremrangebyscore(self, key, min_score, max_score):
        self.commands.append(("zremrangebyscore", key, min_score, max_score))

    async def zcard(self, key):
        self.commands.append(("zcard", key))

    async def zadd(self, key, mapping):
        self.commands.append(("zadd", key, mapping))

    async def expire(self, key, ttl):
        self.commands.append(("expire", key, ttl))

    async def execute(self):
        return self.results


class FakeRedis:
    def __init__(self, pipeline_results):
        self.pipeline_results = pipeline_results
        self.pipelines_created = 0

    def pipeline(self):
        result = self.pipeline_results[min(self.pipelines_created, len(self.pipeline_results) - 1)]
        self.pipelines_created += 1
        return FakePipeline(result)

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_rate_limiter_under_limit(monkeypatch):
    pipeline_results = [[None, 2, None, True]]
    fake_redis = FakeRedis(pipeline_results)
    limiter = rate_limiting.RateLimiter.__new__(rate_limiting.RateLimiter)
    limiter.redis = fake_redis

    limited, remaining = await limiter.is_rate_limited("user:1", limit=5, window_seconds=60)

    assert limited is False
    assert remaining == 2


@pytest.mark.asyncio
async def test_rate_limiter_hits_limit(monkeypatch):
    pipeline_results = [[None, 5, None, True]]
    fake_redis = FakeRedis(pipeline_results)
    limiter = rate_limiting.RateLimiter.__new__(rate_limiting.RateLimiter)
    limiter.redis = fake_redis

    limited, remaining = await limiter.is_rate_limited("key", limit=5, window_seconds=10)

    assert limited is True
    assert remaining == 0


@pytest.mark.asyncio
async def test_rate_limiter_fail_open(monkeypatch):
    class BrokenRedis(FakeRedis):
        def pipeline(self):  # type: ignore[override]
            raise RuntimeError("redis down")

    limiter = rate_limiting.RateLimiter.__new__(rate_limiting.RateLimiter)
    limiter.redis = BrokenRedis([])

    limited, remaining = await limiter.is_rate_limited("key", limit=3, window_seconds=10)
    assert limited is False
    assert remaining == 3


class StubLimiter:
    def __init__(self, responses):
        self.responses = asyncio.Queue()
        for item in responses:
            self.responses.put_nowait(item)
        self.calls = []

    async def is_rate_limited(self, key, limit, window_seconds):
        self.calls.append((key, limit, window_seconds))
        return await self.responses.get()


def _make_dummy_request(ip="127.0.0.1"):
    return SimpleNamespace(method="GET", url="/resource", client=SimpleNamespace(host=ip))


def _make_dummy_user(user_id=1, role="user"):
    return SimpleNamespace(id=user_id, role=role)


def test_rate_limiter_constructor_uses_from_url(monkeypatch):
    captured = {}

    class DummyRedis:
        async def close(self):
            return None

    dummy_client = DummyRedis()

    def fake_from_url(url, decode_responses):
        captured["url"] = url
        captured["decode_responses"] = decode_responses
        return dummy_client

    monkeypatch.setattr(rate_limiting.redis, "from_url", fake_from_url)

    limiter = rate_limiting.RateLimiter("redis://custom:9999")

    assert limiter.redis is dummy_client
    assert captured == {"url": "redis://custom:9999", "decode_responses": True}


@pytest.mark.asyncio
async def test_rate_limiter_close_calls_redis_close():
    called = False

    class DummyRedis:
        async def close(self):
            nonlocal called
            called = True

    limiter = rate_limiting.RateLimiter.__new__(rate_limiting.RateLimiter)
    limiter.redis = DummyRedis()

    await limiter.close()

    assert called is True


def test_get_rate_limiter_prefers_settings_url(monkeypatch):
    monkeypatch.setattr(rate_limiting, "_rate_limiter", None)

    created_urls = []

    class DummyLimiter:
        def __init__(self, redis_url="redis://localhost:6379"):
            created_urls.append(redis_url)

    monkeypatch.setattr(rate_limiting, "RateLimiter", DummyLimiter)

    config_stub = SimpleNamespace(settings=SimpleNamespace(redis_url="redis://settings"))
    monkeypatch.setitem(sys.modules, "app.core.config", config_stub)

    limiter = rate_limiting.get_rate_limiter()

    assert isinstance(limiter, DummyLimiter)
    assert created_urls == ["redis://settings"]


def test_get_rate_limiter_fallbacks_to_default(monkeypatch):
    monkeypatch.setattr(rate_limiting, "_rate_limiter", None)

    created_urls = []

    class FlakyLimiter:
        def __init__(self, redis_url="redis://localhost:6379"):
            created_urls.append(redis_url)
            if redis_url == "redis://broken":
                raise RuntimeError("boom")

    monkeypatch.setattr(rate_limiting, "RateLimiter", FlakyLimiter)

    config_stub = SimpleNamespace(settings=SimpleNamespace(redis_url="redis://broken"))
    monkeypatch.setitem(sys.modules, "app.core.config", config_stub)

    limiter = rate_limiting.get_rate_limiter()

    assert isinstance(limiter, FlakyLimiter)
    assert created_urls == ["redis://broken", "redis://localhost:6379"]


@pytest.mark.asyncio
async def test_rate_limit_decorator_allows_request(monkeypatch):
    response_obj = SimpleNamespace(headers={})

    async def sample_endpoint(request=None, current_user=None):
        return response_obj

    stub = StubLimiter([(False, 7)])
    monkeypatch.setattr(rate_limiting, "_rate_limiter", stub)

    decorated = rate_limiting.rate_limit(requests=10, window_seconds=30)(sample_endpoint)

    request = SimpleNamespace(method="GET", url="/endpoint", client=SimpleNamespace(host="127.0.0.1"))

    user = SimpleNamespace(id=42, role="professor")
    result = await decorated(request, user)

    assert result is response_obj
    assert response_obj.headers["X-RateLimit-Limit"] == "10"
    assert response_obj.headers["X-RateLimit-Remaining"] == "7"
    assert stub.calls == [("rate_limit:user:42:sample_endpoint", 10, 30)]


@pytest.mark.asyncio
async def test_rate_limit_decorator_blocks(monkeypatch):
    async def endpoint(request=None, current_user=None):
        return SimpleNamespace(headers={})

    stub = StubLimiter([(True, 0)])
    monkeypatch.setattr(rate_limiting, "_rate_limiter", stub)

    decorated = rate_limiting.rate_limit(requests=3, window_seconds=15)(endpoint)

    with pytest.raises(HTTPException) as exc:
        await decorated(SimpleNamespace(method="POST", url="/blocked", client=SimpleNamespace(host="1.2.3.4")))

    assert exc.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert exc.value.detail["limit"] == 3
    assert stub.calls == [("rate_limit:ip:1.2.3.4:endpoint", 3, 15)]


@pytest.mark.asyncio
async def test_rate_limit_decorator_uses_custom_key_func_and_kwargs(monkeypatch):
    async def endpoint(request=None, current_user=None):
        return SimpleNamespace(headers={})

    stub = StubLimiter([(False, 9)])
    monkeypatch.setattr(rate_limiting, "_rate_limiter", stub)

    def produce_key(request, current_user):
        pieces = ["custom"]
        if current_user:
            pieces.append(str(current_user.id))
        if request:
            pieces.append(request.url)
        return ":".join(pieces)

    decorated = rate_limiting.rate_limit(requests=12, window_seconds=45, key_func=produce_key)(endpoint)

    response = await decorated(request=_make_dummy_request("8.8.8.8"), current_user=_make_dummy_user(5, "professor"))

    assert response.headers["X-RateLimit-Limit"] == "12"
    assert stub.calls == [("custom:5:/resource", 12, 45)]


@pytest.mark.asyncio
async def test_professor_rate_limit_prefers_user_id(monkeypatch):
    stub = StubLimiter([(False, 99)])
    monkeypatch.setattr(rate_limiting, "_rate_limiter", stub)

    @rate_limiting.professor_rate_limit()
    async def endpoint(request=None, current_user=None):
        return SimpleNamespace(headers={})

    response = await endpoint(current_user=_make_dummy_user(11, "professor"))

    assert response.headers["X-RateLimit-Remaining"] == "99"
    assert stub.calls == [("professor_api:user:11", 60, 3600)]


@pytest.mark.asyncio
async def test_professor_rate_limit_uses_request_ip(monkeypatch):
    stub = StubLimiter([(False, 3)])
    monkeypatch.setattr(rate_limiting, "_rate_limiter", stub)

    @rate_limiting.professor_rate_limit()
    async def endpoint(request=None, current_user=None):
        return SimpleNamespace(headers={})

    await endpoint(request=_make_dummy_request("10.0.0.1"))

    assert stub.calls == [("professor_api:ip:10.0.0.1", 60, 3600)]


@pytest.mark.asyncio
async def test_professor_rate_limit_handles_anonymous(monkeypatch):
    stub = StubLimiter([(False, 1)])
    monkeypatch.setattr(rate_limiting, "_rate_limiter", stub)

    @rate_limiting.professor_rate_limit()
    async def endpoint(request=None, current_user=None):
        return SimpleNamespace(headers={})

    await endpoint()

    assert stub.calls == [("professor_api:anonymous", 60, 3600)]


@pytest.mark.asyncio
async def test_admin_rate_limit_key_generation(monkeypatch):
    stub = StubLimiter([(False, 2)])
    monkeypatch.setattr(rate_limiting, "_rate_limiter", stub)

    @rate_limiting.admin_rate_limit(requests=5, window_seconds=90)
    async def endpoint(request=None, current_user=None):
        return SimpleNamespace(headers={})

    await endpoint(request=_make_dummy_request("9.9.9.9"))

    assert stub.calls == [("admin_api:ip:9.9.9.9", 5, 90)]


@pytest.mark.asyncio
async def test_admin_rate_limit_prefers_user(monkeypatch):
    stub = StubLimiter([(False, 4)])
    monkeypatch.setattr(rate_limiting, "_rate_limiter", stub)

    @rate_limiting.admin_rate_limit()
    async def endpoint(request=None, current_user=None):
        return SimpleNamespace(headers={})

    await endpoint(current_user=_make_dummy_user(321, "admin"))

    assert stub.calls == [("admin_api:user:321", 200, 3600)]


@pytest.mark.asyncio
async def test_student_rate_limit_variants(monkeypatch):
    stub = StubLimiter([(False, 5), (False, 7), (False, 6)])
    monkeypatch.setattr(rate_limiting, "_rate_limiter", stub)

    @rate_limiting.student_rate_limit(requests=8, window_seconds=30)
    async def endpoint(request=None, current_user=None):
        return SimpleNamespace(headers={})

    await endpoint(current_user=_make_dummy_user(15, "student"))
    await endpoint(request=_make_dummy_request("172.16.0.9"))
    await endpoint()

    assert stub.calls == [
        ("student_api:user:15", 8, 30),
        ("student_api:ip:172.16.0.9", 8, 30),
        ("student_api:anonymous", 8, 30),
    ]
