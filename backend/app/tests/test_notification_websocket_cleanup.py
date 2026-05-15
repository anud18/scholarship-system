"""
Tests for `NotificationService._send_websocket_notification` — the
WebSocket fan-out + dead-connection cleanup helper.

A regression in this method either:
- Leaks dead websockets indefinitely (memory grows, eventual OOM in the
  long-running notification service)
- Drops the JSON wire format ({"type": "notification", "data": ...})
  so the frontend `onmessage` handler can't deserialize
- Crashes the WHOLE fan-out when ONE websocket raises (silently DoS's
  every other connected client for that user)

The method is pure-async-no-DB: it reads from + mutates the in-memory
`_websocket_connections` dict only. Tests use AsyncMock to simulate
the FastAPI WebSocket object.

Wave 6a161.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.notification_service import NotificationService


@pytest.fixture
def service():
    """NotificationService.__init__ requires an AsyncSession — pass a
    MagicMock since `_send_websocket_notification` never touches `self.db`."""
    svc = NotificationService(db=MagicMock())
    # __init__ already initializes _websocket_connections to {} but we
    # reset to ensure no cross-test bleed if a future change makes it
    # a class-level attribute.
    svc._websocket_connections = {}
    return svc


def _make_ws(should_fail=False):
    """Build a mock websocket with a configurable send_text. AsyncMock's
    side_effect=Exception triggers an exception on await."""
    ws = MagicMock()
    if should_fail:
        ws.send_text = AsyncMock(side_effect=ConnectionError("dead pipe"))
    else:
        ws.send_text = AsyncMock(return_value=None)
    return ws


# ---------------------------------------------------------------------------
# 1. User not connected — no-op, no error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_not_in_connections_is_noop(service):
    """Pin: when the user has no active websockets, the method returns
    quietly. Pin so a refactor doesn't accidentally raise KeyError on
    the missing user_id."""
    # No setup — _websocket_connections is empty
    await service._send_websocket_notification(user_id=42, notification_data={"x": 1})
    # No exception raised, no side effect to check.


# ---------------------------------------------------------------------------
# 2. Healthy connections — all receive the message
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_healthy_websocket_receives_message(service):
    """Pin: a single healthy websocket receives the JSON-encoded message.
    Pin the WIRE FORMAT — `{"type": "notification", "data": ...}` —
    so the frontend onmessage handler can deserialize."""
    ws = _make_ws()
    service._websocket_connections[7] = [ws]

    notification_data = {"id": 100, "title": "Hello"}
    await service._send_websocket_notification(7, notification_data)

    ws.send_text.assert_called_once()
    payload = json.loads(ws.send_text.call_args[0][0])
    assert payload == {"type": "notification", "data": notification_data}


@pytest.mark.asyncio
async def test_multiple_healthy_websockets_all_receive(service):
    """Pin: multiple connections (e.g. user open in 2 browser tabs) all
    receive the message."""
    ws1, ws2, ws3 = _make_ws(), _make_ws(), _make_ws()
    service._websocket_connections[1] = [ws1, ws2, ws3]

    await service._send_websocket_notification(1, {"k": "v"})

    assert ws1.send_text.call_count == 1
    assert ws2.send_text.call_count == 1
    assert ws3.send_text.call_count == 1


@pytest.mark.asyncio
async def test_message_uses_json_dumps(service):
    """Pin: the message is `json.dumps(...)` — not str(dict). Pin so
    a refactor to f-string doesn't break frontend JSON.parse."""
    ws = _make_ws()
    service._websocket_connections[1] = [ws]

    # Use a dict that would render differently with str() vs json.dumps
    await service._send_websocket_notification(1, {"flag": True, "value": None})

    sent = ws.send_text.call_args[0][0]
    # JSON uses lowercase true/null; Python repr would use True/None
    assert "true" in sent
    assert "null" in sent
    assert "True" not in sent
    assert "None" not in sent


# ---------------------------------------------------------------------------
# 3. SECURITY: one bad websocket must NOT take down the others
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_one_bad_websocket_does_not_block_others(service):
    """Pin SECURITY: when one websocket raises, the loop continues to
    deliver to remaining healthy websockets. Pin so a refactor that
    propagates the exception silently DoS's every other connected client
    for the same user."""
    bad = _make_ws(should_fail=True)
    good1 = _make_ws()
    good2 = _make_ws()
    service._websocket_connections[1] = [bad, good1, good2]

    await service._send_websocket_notification(1, {"k": "v"})

    # Good ones still received
    assert good1.send_text.call_count == 1
    assert good2.send_text.call_count == 1
    # Bad one was attempted
    assert bad.send_text.call_count == 1


@pytest.mark.asyncio
async def test_method_does_not_raise_on_bad_websocket(service):
    """Pin: the method must NOT bubble the websocket exception. Pin so
    the upstream caller (notification dispatch loop) doesn't crash and
    take down every other channel."""
    bad = _make_ws(should_fail=True)
    service._websocket_connections[1] = [bad]

    # Must NOT raise
    await service._send_websocket_notification(1, {"k": "v"})


# ---------------------------------------------------------------------------
# 4. Cleanup: dead websockets are pruned
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dead_websocket_is_pruned_from_connections(service):
    """Pin MEMORY: a websocket that raises during send is REMOVED from
    the connections dict. Pin so a refactor doesn't accidentally leak
    dead connections (OOM in long-running service)."""
    bad = _make_ws(should_fail=True)
    service._websocket_connections[1] = [bad]

    await service._send_websocket_notification(1, {"k": "v"})

    assert bad not in service._websocket_connections[1]


@pytest.mark.asyncio
async def test_healthy_websockets_stay_after_one_dies(service):
    """Pin: only the dead ones get pruned. Healthy connections stay."""
    bad = _make_ws(should_fail=True)
    good1 = _make_ws()
    good2 = _make_ws()
    service._websocket_connections[1] = [bad, good1, good2]

    await service._send_websocket_notification(1, {"k": "v"})

    remaining = service._websocket_connections[1]
    assert bad not in remaining
    assert good1 in remaining
    assert good2 in remaining


@pytest.mark.asyncio
async def test_all_dead_leaves_empty_list_not_missing_key(service):
    """Pin: when ALL connections die, the user's list goes empty but
    the key stays (not popped to None / deleted). Pin so the next
    `add_websocket_connection` finds the existing list to append to."""
    bad1 = _make_ws(should_fail=True)
    bad2 = _make_ws(should_fail=True)
    service._websocket_connections[1] = [bad1, bad2]

    await service._send_websocket_notification(1, {"k": "v"})

    assert 1 in service._websocket_connections
    assert service._websocket_connections[1] == []


# ---------------------------------------------------------------------------
# 5. Cross-user isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_other_users_connections_untouched(service):
    """Pin: sending to user 1 does NOT touch user 2's connections. Pin
    so a refactor doesn't accidentally fan out across the whole dict."""
    user1_ws = _make_ws()
    user2_ws = _make_ws()
    service._websocket_connections[1] = [user1_ws]
    service._websocket_connections[2] = [user2_ws]

    await service._send_websocket_notification(1, {"k": "v"})

    assert user1_ws.send_text.call_count == 1
    assert user2_ws.send_text.call_count == 0
    # User 2's connection list also unchanged
    assert service._websocket_connections[2] == [user2_ws]


# ---------------------------------------------------------------------------
# 6. Empty connection list for a present user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_connection_list_for_present_user(service):
    """Pin: when user_id IS in the dict but the list is empty (e.g.
    all connections previously died), the method runs the for-loop 0
    times and returns. Pin so a refactor doesn't crash on empty list."""
    service._websocket_connections[42] = []

    await service._send_websocket_notification(42, {"k": "v"})
    # No exception, no side effect.
    assert service._websocket_connections[42] == []
