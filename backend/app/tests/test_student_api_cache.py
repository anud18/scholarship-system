"""
Redis cache for SIS (學籍) API records — StudentService + student_api_cache.

Runs against the FakeAsyncRedis from test_cache.py with a fake SIS HTTP client,
so it needs neither Redis nor the network.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Union
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core import cache as cache_mod
from app.core.config import settings
from app.core.exceptions import ServiceUnavailableError
from app.services import student_api_cache
from app.services.student_service import StudentService
from app.tests.test_cache import FakeAsyncRedis

BASIC = {"std_stdcode": "314540001", "std_cname": "王小明", "std_pid": "A123456789", "std_academyno": "Y"}
TERM_1 = {"trm_year": "114", "trm_term": "1", "trm_depname": "電機系"}

Answer = Union[Dict[str, Any], int, Exception]  # SIS JSON body, HTTP status, or raised error


class FakeSIS:
    """Scripted SIS endpoint: each (endpoint, year, term) pops answers in order; the last one repeats."""

    def __init__(self, answers: Dict[tuple, List[Answer]]):
        self.answers = answers
        self.calls: List[tuple] = []
        self.client = AsyncMock()
        self.client.post.side_effect = self._post

    async def _post(self, url: str, content: str, **_):
        body = json.loads(content)
        key = (url.rsplit("/", 1)[-1], body.get("trmyear"), body.get("trmterm"))
        self.calls.append(key)
        queue = self.answers[key]
        answer = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(answer, Exception):
            raise answer
        resp = MagicMock()
        if isinstance(answer, int):
            resp.status_code = answer
            return resp
        resp.status_code = 200
        resp.json.return_value = answer
        return resp

    def count(self, endpoint: str, year: Optional[str] = None, term: Optional[str] = None) -> int:
        return self.calls.count((endpoint, year, term))


def found(record):
    return {"code": "200", "data": [record]}


NO_DATA = {"code": "403", "msg": "無資料", "data": None}


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeAsyncRedis()
    cache_mod.reset_clients_for_tests()
    monkeypatch.setattr(student_api_cache, "get_cache", lambda: fake)
    monkeypatch.setattr(cache_mod, "get_cache", lambda: fake)
    monkeypatch.setattr(settings, "student_api_cache_enabled", True)
    yield fake
    cache_mod.reset_clients_for_tests()


@pytest.fixture
def service():
    svc = StudentService()
    svc.api_enabled = True
    svc.api_base_url = "http://fake-sis-api"
    return svc


def sis(answers):
    fake = FakeSIS(answers)
    return fake, patch("app.services.student_service._get_http_client", return_value=fake.client)


def ttl_of(fake_redis: FakeAsyncRedis, key: str) -> float:
    _, expires_at = fake_redis._store[(cache_mod.KEY_PREFIX + key).encode("utf-8")]
    return expires_at - time.time()


# ─── cache hit / miss ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_basic_info_second_call_is_served_from_cache(fake_redis, service):
    fake, patcher = sis({("ScholarshipStudent", None, None): [found(BASIC)]})
    with patcher:
        first = await service.get_student_basic_info("314540001")
        second = await service.get_student_basic_info("314540001")

    assert fake.count("ScholarshipStudent") == 1
    assert first == second
    # Cached raw, normalized on every read: retired 電資 Y still maps to 電機 E
    assert second["std_academyno"] == "E"


@pytest.mark.asyncio
async def test_cached_record_is_encrypted_at_rest(fake_redis, service):
    _, patcher = sis({("ScholarshipStudent", None, None): [found(BASIC)]})
    with patcher:
        await service.get_student_basic_info("314540001")

    blob = fake_redis._store[(cache_mod.KEY_PREFIX + "sis:basic:314540001").encode("utf-8")][0]
    assert blob.startswith(b"pii:")
    assert b"A123456789" not in blob
    assert "王小明".encode("utf-8") not in blob


@pytest.mark.asyncio
async def test_fresh_skips_the_cache_read_but_refreshes_it(fake_redis, service):
    updated = {**BASIC, "std_cname": "王大明"}
    fake, patcher = sis({("ScholarshipStudent", None, None): [found(BASIC), found(updated)]})
    with patcher:
        await service.get_student_basic_info("314540001")
        live = await service.get_student_basic_info("314540001", fresh=True)
        cached = await service.get_student_basic_info("314540001")

    assert fake.count("ScholarshipStudent") == 2
    assert live["std_cname"] == "王大明"
    assert cached["std_cname"] == "王大明"


@pytest.mark.asyncio
async def test_record_uses_long_ttl(fake_redis, service, monkeypatch):
    monkeypatch.setattr(settings, "student_api_cache_ttl", 8 * 3600)
    _, patcher = sis({("ScholarshipStudentTerm", "114", "1"): [found(TERM_1)]})
    with patcher:
        await service.get_student_term_info("314540001", "114", "1")

    assert 8 * 3600 - 60 < ttl_of(fake_redis, "sis:term:314540001:114:1") <= 8 * 3600


# ─── empty answers: retried, then cached briefly ─────────────────────────────


@pytest.mark.asyncio
async def test_empty_term_answer_is_retried_then_cached_as_empty(fake_redis, service, monkeypatch):
    monkeypatch.setattr(settings, "student_api_empty_retries", 2)
    monkeypatch.setattr(settings, "student_api_negative_cache_ttl", 3600)
    fake, patcher = sis({("ScholarshipStudentTerm", "114", "2"): [NO_DATA]})
    with patcher:
        first = await service.get_student_term_info("314540001", "114", "2")
        second = await service.get_student_term_info("314540001", "114", "2")

    assert first is None and second is None
    assert fake.count("ScholarshipStudentTerm", "114", "2") == 3  # 1 + 2 retries, then served from cache
    assert 3600 - 60 < ttl_of(fake_redis, "sis:term:314540001:114:2") <= 3600


@pytest.mark.asyncio
async def test_empty_answer_recovered_by_retry_is_cached_as_record(fake_redis, service):
    fake, patcher = sis({("ScholarshipStudentTerm", "114", "1"): [NO_DATA, found(TERM_1)]})
    with patcher:
        result = await service.get_student_term_info("314540001", "114", "1")
        again = await service.get_student_term_info("314540001", "114", "1")

    assert result == TERM_1 == again
    assert fake.count("ScholarshipStudentTerm", "114", "1") == 2


# ─── errors are never cached ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sis_error_is_not_cached(fake_redis, service):
    fake, patcher = sis({("ScholarshipStudentTerm", "114", "1"): [500, found(TERM_1)]})
    with patcher:
        with pytest.raises(ServiceUnavailableError):
            await service.get_student_term_info("314540001", "114", "1")
        result = await service.get_student_term_info("314540001", "114", "1")

    assert result == TERM_1
    assert fake.count("ScholarshipStudentTerm", "114", "1") == 2


@pytest.mark.asyncio
async def test_redis_outage_falls_through_to_sis(fake_redis, service):
    fake_redis.fail_next = ConnectionError("redis down")
    fake, patcher = sis({("ScholarshipStudent", None, None): [found(BASIC)]})
    with patcher:
        result = await service.get_student_basic_info("314540001")

    assert result["std_cname"] == "王小明"
    assert fake.count("ScholarshipStudent") == 1


@pytest.mark.asyncio
async def test_unreadable_entry_is_dropped_and_refetched(fake_redis, service):
    key = (cache_mod.KEY_PREFIX + "sis:basic:314540001").encode("utf-8")
    fake_redis._store[key] = (b"pii:v1:not-a-valid-envelope", None)
    fake, patcher = sis({("ScholarshipStudent", None, None): [found(BASIC)]})
    with patcher:
        result = await service.get_student_basic_info("314540001")

    assert result["std_cname"] == "王小明"
    assert fake.count("ScholarshipStudent") == 1


@pytest.mark.asyncio
async def test_cache_disabled_always_calls_sis(fake_redis, service, monkeypatch):
    monkeypatch.setattr(settings, "student_api_cache_enabled", False)
    fake, patcher = sis({("ScholarshipStudent", None, None): [found(BASIC)]})
    with patcher:
        await service.get_student_basic_info("314540001")
        await service.get_student_basic_info("314540001")

    assert fake.count("ScholarshipStudent") == 2
    assert fake_redis._store == {}


# ─── invalidation ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalidate_one_student_keeps_codes_sharing_its_prefix(fake_redis):
    for code in ("E1234", "E12345"):
        await student_api_cache.set_cached_record(student_api_cache.basic_key(code), {"std_stdcode": code})
        await student_api_cache.set_cached_record(student_api_cache.term_key(code, "114", "1"), {"trm_year": "114"})

    deleted = await student_api_cache.invalidate_student_api_cache("E1234")

    assert deleted == 2
    assert (await student_api_cache.get_cached_record(student_api_cache.basic_key("E1234")))[0] is False
    assert (await student_api_cache.get_cached_record(student_api_cache.basic_key("E12345")))[0] is True
    assert (await student_api_cache.get_cached_record(student_api_cache.term_key("E12345", "114", "1")))[0] is True


@pytest.mark.asyncio
async def test_invalidate_all(fake_redis):
    await student_api_cache.set_cached_record(student_api_cache.basic_key("A1"), {"std_stdcode": "A1"})
    await student_api_cache.set_cached_record(student_api_cache.term_key("A1", "114", "1"), None)

    assert await student_api_cache.invalidate_student_api_cache() == 2


# ─── snapshot: a failed term-2 lookup still falls back to term 1 ─────────────


@pytest.mark.asyncio
async def test_yearly_snapshot_falls_back_to_term_1_when_term_2_times_out(service):
    _, patcher = sis(
        {
            ("ScholarshipStudent", None, None): [found(BASIC)],
            ("ScholarshipStudentTerm", "114", "2"): [httpx.ReadTimeout("slow")],
            ("ScholarshipStudentTerm", "114", "1"): [found(TERM_1)],
        }
    )
    with patcher:
        snapshot = await service.get_student_snapshot("314540001", academic_year="114", semester=None)

    assert snapshot["trm_depname"] == "電機系"
    assert snapshot["_term_data_status"] == "partial"  # term 2 may exist → re-fetched at submit
    assert "Term 2 lookup failed" in snapshot["_term_error_message"]


@pytest.mark.asyncio
async def test_yearly_snapshot_reports_error_when_term_2_fails_and_term_1_is_empty(service):
    _, patcher = sis(
        {
            ("ScholarshipStudent", None, None): [found(BASIC)],
            ("ScholarshipStudentTerm", "114", "2"): [httpx.ReadTimeout("slow")],
            ("ScholarshipStudentTerm", "114", "1"): [NO_DATA],
        }
    )
    with patcher:
        snapshot = await service.get_student_snapshot("314540001", academic_year="114", semester=None)

    assert snapshot["_term_data_status"] == "error"
    assert "no data for 114 term 1" in snapshot["_term_error_message"]
    assert "trm_depname" not in snapshot


@pytest.mark.asyncio
async def test_yearly_snapshot_uses_term_1_when_term_2_is_empty(service):
    _, patcher = sis(
        {
            ("ScholarshipStudent", None, None): [found(BASIC)],
            ("ScholarshipStudentTerm", "114", "2"): [NO_DATA],
            ("ScholarshipStudentTerm", "114", "1"): [found(TERM_1)],
        }
    )
    with patcher:
        snapshot = await service.get_student_snapshot("314540001", academic_year="114", semester=None)

    assert snapshot["_term_data_status"] == "success"
    assert snapshot["_term_error_message"] is None


# ─── login: a cached "not found" must not lock out a just-enrolled student ──


@pytest.mark.asyncio
async def test_login_lookup_ignores_cached_not_found_and_refreshes_it(fake_redis, service):
    not_found = {"code": "404", "data": None}
    fake, patcher = sis({("ScholarshipStudent", None, None): [not_found, not_found, not_found, found(BASIC)]})
    with patcher:
        # Some page looked the student up before SIS had their record → empty answer cached
        assert await service.get_student_basic_info("314540001") is None
        # SIS now has the record; login asks live and repairs the cache entry
        at_login = await service.get_student_basic_info("314540001", fresh=True, retry_empty=False)
        afterwards = await service.get_student_basic_info("314540001")

    assert at_login["std_cname"] == "王小明"
    assert afterwards["std_cname"] == "王小明"
    assert fake.count("ScholarshipStudent") == 4  # 3 (with retries) + 1 at login, then cache


@pytest.mark.asyncio
async def test_retry_empty_false_asks_sis_once(fake_redis, service, monkeypatch):
    monkeypatch.setattr(settings, "student_api_empty_retries", 2)
    fake, patcher = sis({("ScholarshipStudent", None, None): [{"code": "404", "data": None}]})
    with patcher:
        result = await service.get_student_basic_info("E1234", fresh=True, retry_empty=False)

    assert result is None
    assert fake.count("ScholarshipStudent") == 1
    # An unretried empty answer is not trusted enough to hide the record from other callers
    assert fake_redis._store == {}


@pytest.mark.asyncio
async def test_basic_403_no_data_is_cached_as_empty(fake_redis, service):
    fake, patcher = sis({("ScholarshipStudent", None, None): [NO_DATA]})
    with patcher:
        assert await service.get_student_basic_info("E1234") is None
        assert await service.get_student_basic_info("E1234") is None

    assert fake.count("ScholarshipStudent") == 3  # 1 + 2 retries, second lookup from cache


@pytest.mark.asyncio
async def test_unexpected_sis_code_returns_none_without_caching_or_retrying(fake_redis, service):
    system_error = {"code": "500", "msg": "系統錯誤", "data": None}
    fake, patcher = sis({("ScholarshipStudent", None, None): [system_error, found(BASIC)]})
    with patcher:
        during_outage = await service.get_student_basic_info("314540001")
        after_recovery = await service.get_student_basic_info("314540001")

    assert during_outage is None
    assert after_recovery["std_cname"] == "王小明"
    assert fake.count("ScholarshipStudent") == 2


@pytest.mark.asyncio
async def test_snapshot_reads_sis_live_by_default(fake_redis, service):
    stale = {**BASIC, "std_studingstatus": "1"}
    current = {**BASIC, "std_studingstatus": "2"}
    fake, patcher = sis({("ScholarshipStudent", None, None): [found(stale), found(current)]})
    with patcher:
        await service.get_student_basic_info("314540001")  # caches the stale record
        snapshot = await service.get_student_snapshot("314540001")

    assert snapshot["std_studingstatus"] == "2"
    assert fake.count("ScholarshipStudent") == 2


# ─── get_term_history ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_term_history_keeps_order_and_returns_failures_in_place(service):
    _, patcher = sis(
        {
            ("ScholarshipStudentTerm", "114", "2"): [NO_DATA],
            ("ScholarshipStudentTerm", "114", "1"): [found(TERM_1)],
            ("ScholarshipStudentTerm", "113", "2"): [500],
        }
    )
    with patcher:
        history = await service.get_term_history("314540001", [("114", "2"), ("114", "1"), ("113", "2")])

    assert [(year, term) for year, term, _ in history] == [("114", "2"), ("114", "1"), ("113", "2")]
    assert history[0][2] is None
    assert history[1][2] == TERM_1
    assert isinstance(history[2][2], ServiceUnavailableError)


@pytest.mark.asyncio
async def test_term_history_bounds_concurrency(service, monkeypatch):
    import asyncio

    from app.services import student_service as student_service_module

    monkeypatch.setattr(student_service_module, "TERM_LOOKUP_CONCURRENCY", 2)
    in_flight = peak = 0

    async def slow_term(student_code, academic_year, term):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return None

    monkeypatch.setattr(service, "get_student_term_info", slow_term)
    await service.get_term_history("314540001", [(str(year), "1") for year in range(100, 110)])

    assert peak == 2


@pytest.mark.asyncio
async def test_term_history_propagates_cancellation(service, monkeypatch):
    import asyncio

    async def cancelled(*_):
        raise asyncio.CancelledError()

    monkeypatch.setattr(service, "get_student_term_info", cancelled)
    with pytest.raises(asyncio.CancelledError):
        await service.get_term_history("314540001", [("114", "1")])


@pytest.mark.asyncio
async def test_portal_login_verifies_student_status_live():
    from app.services.portal_sso_service import PortalSSOService

    sso = PortalSSOService(db=None)  # type: ignore[arg-type]
    sso.student_service = MagicMock(api_enabled=True)
    sso.student_service.get_student_basic_info = AsyncMock(return_value={"std_stdcode": "314540001"})

    is_student, _ = await sso._verify_student_status("314540001")

    assert is_student is True
    sso.student_service.get_student_basic_info.assert_awaited_once_with("314540001", fresh=True, retry_empty=False)
