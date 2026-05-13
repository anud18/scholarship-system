"""
Pure-function tests for `AuditService._get_client_ip`.

The IP extraction helper feeds every audit-log row. Wrong precedence
between X-Forwarded-For / X-Real-IP / request.client.host would either
log the load-balancer's IP instead of the real client (compliance risk)
or fail to detect malicious users behind a proxy.

8 cases pinning the precedence ladder + edge cases:
- X-Forwarded-For (highest precedence; supports comma-separated chain).
- X-Forwarded-For takes the first hop, not the last.
- X-Real-IP (second precedence) used when XFF absent.
- Falls back to request.client.host when no proxy headers.
- Returns None when nothing is available.
- Whitespace is stripped from the first XFF entry.
- XFF takes precedence over X-Real-IP even when both present.
- XFF takes precedence over request.client.host.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.audit_service import AuditService


def _make_request(headers: dict, client_host: str | None = None) -> MagicMock:
    """Build a duck-typed FastAPI Request with the headers + client we want."""
    req = MagicMock()
    req.headers = headers
    if client_host:
        req.client = SimpleNamespace(host=client_host)
    else:
        req.client = None
    return req


@pytest.fixture
def service():
    return AuditService()


def test_returns_xff_first_ip(service):
    """X-Forwarded-For takes precedence and the FIRST entry is the client."""
    req = _make_request({"x-forwarded-for": "192.0.2.1"})
    assert service._get_client_ip(req) == "192.0.2.1"


def test_xff_chain_takes_first_hop_not_last(service):
    """Chain '203.0.113.5, 10.0.0.1, 10.0.0.2' → return the original client (first)."""
    req = _make_request({"x-forwarded-for": "203.0.113.5, 10.0.0.1, 10.0.0.2"})
    assert service._get_client_ip(req) == "203.0.113.5"


def test_xff_strips_whitespace_around_first_hop(service):
    """Leading/trailing whitespace in the first XFF entry is stripped."""
    req = _make_request({"x-forwarded-for": "  198.51.100.42  , 10.0.0.1"})
    assert service._get_client_ip(req) == "198.51.100.42"


def test_returns_x_real_ip_when_xff_absent(service):
    """Without XFF, X-Real-IP is the second precedence level."""
    req = _make_request({"x-real-ip": "203.0.113.99"})
    assert service._get_client_ip(req) == "203.0.113.99"


def test_xff_beats_x_real_ip_when_both_present(service):
    """Order matters: XFF wins over X-Real-IP."""
    req = _make_request({"x-forwarded-for": "192.0.2.10", "x-real-ip": "10.0.0.5"})
    assert service._get_client_ip(req) == "192.0.2.10"


def test_falls_back_to_request_client_host(service):
    """No proxy headers ⇒ use the direct connection IP from request.client.host."""
    req = _make_request({}, client_host="172.16.0.50")
    assert service._get_client_ip(req) == "172.16.0.50"


def test_xff_beats_request_client_host(service):
    """Even if request.client is set, XFF takes precedence (real client behind proxy)."""
    req = _make_request({"x-forwarded-for": "192.0.2.20"}, client_host="172.16.0.50")
    assert service._get_client_ip(req) == "192.0.2.20"


def test_returns_none_when_nothing_available(service):
    """No headers AND no request.client ⇒ None (audit log will store NULL)."""
    req = _make_request({})
    req.client = None
    assert service._get_client_ip(req) is None
