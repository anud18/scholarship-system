"""
Tests for `app/utils/audit_helpers.py`.

The two functions under test (`log_college_review_action` and
`log_college_review_action_with_changes`) wrap every audit-trail write
made by the college-review endpoints. Bugs here cause either:

  - **silent audit-trail loss** — staff dispute a distribution decision
    but no audit row exists (compliance failure)
  - **request metadata leak/loss** — IP/user agent dropped silently or
    extraction crashes the entire endpoint (PII tracking risk)
  - **transaction state corruption** — db.add succeeds, commit fails,
    rollback never runs → next operation sees a half-written log

The helpers are async + DB-coupled, but the DB session and Request are
both narrow enough to fully mock with `AsyncMock` / `MagicMock`. The
real `AuditLog.create_log` factory is exercised end-to-end (it's a
pure-function pinned in test_audit_log_factory_and_enum.py wave 6a47).

12 cases. Async via pytest-asyncio.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.audit_log import AuditAction, AuditLog
from app.utils.audit_helpers import (
    log_college_review_action,
    log_college_review_action_with_changes,
)

# ─── Helpers / fixtures ─────────────────────────────────────────────


def _user():
    u = MagicMock()
    u.id = 42
    return u


def _request(host: str | None = "10.0.0.1", ua: str = "pytest/1.0"):
    """Build a minimal FastAPI Request-like object."""
    req = MagicMock()
    if host is None:
        req.client = None
    else:
        client = MagicMock()
        client.host = host
        req.client = client
    req.headers = {"user-agent": ua} if ua else {}
    return req


def _db_ok():
    """AsyncMock session whose commit succeeds."""
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock(return_value=None)
    db.rollback = AsyncMock(return_value=None)
    return db


def _db_commit_raises():
    """AsyncMock session whose commit raises."""
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock(side_effect=RuntimeError("commit boom"))
    db.rollback = AsyncMock(return_value=None)
    return db


# ─── log_college_review_action ──────────────────────────────────────


@pytest.mark.asyncio
async def test_logs_with_ip_and_user_agent_extracted_from_request():
    # Pin: IP + UA flow from Request through to AuditLog.create_log.
    # A regression that dropped either would mute incident forensics.
    db = _db_ok()
    log = await log_college_review_action(
        db=db,
        user=_user(),
        action=AuditAction.execute_distribution,
        resource_type="distribution",
        resource_id="123",
        description="executed",
        request=_request(host="203.0.113.7", ua="Mozilla/5.0"),
    )

    assert isinstance(log, AuditLog)
    assert log.ip_address == "203.0.113.7"
    assert log.user_agent == "Mozilla/5.0"
    db.add.assert_called_once_with(log)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_request_omitted_yields_null_ip_and_ua():
    # Pin: no Request → both fields None (NOT empty string), so the
    # column truthfully reflects "not captured" rather than "captured
    # as empty".
    db = _db_ok()
    log = await log_college_review_action(
        db=db,
        user=_user(),
        action=AuditAction.update,
        resource_type="ranking",
        resource_id="1",
        description="update",
    )

    assert log.ip_address is None
    assert log.user_agent is None


@pytest.mark.asyncio
async def test_request_with_no_client_handles_gracefully():
    # Pin: FastAPI sets request.client=None when behind certain proxies.
    # Defensive path: don't crash on the dot-access.
    db = _db_ok()
    log = await log_college_review_action(
        db=db,
        user=_user(),
        action=AuditAction.update,
        resource_type="ranking",
        resource_id="1",
        description="update",
        request=_request(host=None),  # → req.client = None
    )

    assert log.ip_address is None
    # UA still extracted because headers dict still has the entry
    assert log.user_agent == "pytest/1.0"


@pytest.mark.asyncio
async def test_default_new_values_become_empty_dict_not_none():
    # Pin: AuditLog.create_log expects new_values dict; passing None
    # would surface as JSON `null` in the column — annoying for SQL
    # consumers grepping for empty changes.
    db = _db_ok()
    log = await log_college_review_action(
        db=db,
        user=_user(),
        action=AuditAction.create,
        resource_type="review",
        resource_id="9",
        description="created",
    )

    assert log.new_values == {}


@pytest.mark.asyncio
async def test_status_defaults_to_success():
    # Pin: most callsites omit status. Default must remain "success"
    # otherwise dashboards filtering on status='success' would silently
    # miss every successful action.
    db = _db_ok()
    log = await log_college_review_action(
        db=db,
        user=_user(),
        action=AuditAction.create,
        resource_type="review",
        resource_id="9",
        description="created",
    )

    assert log.status == "success"


@pytest.mark.asyncio
async def test_explicit_status_propagates():
    db = _db_ok()
    log = await log_college_review_action(
        db=db,
        user=_user(),
        action=AuditAction.update,
        resource_type="ranking",
        resource_id="1",
        description="update",
        status="failed",
    )
    assert log.status == "failed"


@pytest.mark.asyncio
async def test_commit_failure_triggers_rollback_and_reraises():
    # Pin: the docstring says "audit logging should not break the
    # operation" but the IMPLEMENTATION re-raises. Pin the actual
    # behaviour so callers know they MUST wrap in try/except themselves
    # if they want the docstring contract.
    #
    # If a future commit aligns code to docstring (swallow + return),
    # this test breaks loudly — forcing intentional review.
    db = _db_commit_raises()

    with pytest.raises(RuntimeError, match="commit boom"):
        await log_college_review_action(
            db=db,
            user=_user(),
            action=AuditAction.create,
            resource_type="review",
            resource_id="9",
            description="will fail",
        )

    db.rollback.assert_awaited_once()


# ─── log_college_review_action_with_changes ─────────────────────────


@pytest.mark.asyncio
async def test_with_changes_combines_old_and_new_values():
    # Pin: combined structure is {"old_values": ..., "new_values": ...}.
    # Audit-query tooling depends on this exact shape — flattening or
    # renaming keys breaks downstream forensics.
    db = _db_ok()
    log = await log_college_review_action_with_changes(
        db=db,
        user=_user(),
        action=AuditAction.update,
        resource_type="ranking",
        resource_id="1",
        description="changed rank",
        old_values={"rank": 3},
        new_values={"rank": 1},
    )

    assert log.new_values == {
        "old_values": {"rank": 3},
        "new_values": {"rank": 1},
    }


@pytest.mark.asyncio
async def test_with_changes_defaults_missing_sides_to_empty_dicts():
    # Pin: None on either side becomes {}, so the JSON column always
    # has the expected two-key shape.
    db = _db_ok()
    log = await log_college_review_action_with_changes(
        db=db,
        user=_user(),
        action=AuditAction.create,
        resource_type="review",
        resource_id="9",
        description="initial create",
        new_values={"rank": 1},
    )

    assert log.new_values == {"old_values": {}, "new_values": {"rank": 1}}


@pytest.mark.asyncio
async def test_with_changes_extracts_request_metadata():
    db = _db_ok()
    log = await log_college_review_action_with_changes(
        db=db,
        user=_user(),
        action=AuditAction.update,
        resource_type="ranking",
        resource_id="1",
        description="d",
        old_values={"a": 1},
        new_values={"a": 2},
        request=_request(host="198.51.100.4", ua="curl/8.0"),
    )

    assert log.ip_address == "198.51.100.4"
    assert log.user_agent == "curl/8.0"


@pytest.mark.asyncio
async def test_with_changes_no_request_yields_null_metadata():
    db = _db_ok()
    log = await log_college_review_action_with_changes(
        db=db,
        user=_user(),
        action=AuditAction.update,
        resource_type="ranking",
        resource_id="1",
        description="d",
    )
    assert log.ip_address is None
    assert log.user_agent is None


@pytest.mark.asyncio
async def test_with_changes_commit_failure_triggers_rollback_and_reraises():
    db = _db_commit_raises()

    with pytest.raises(RuntimeError, match="commit boom"):
        await log_college_review_action_with_changes(
            db=db,
            user=_user(),
            action=AuditAction.update,
            resource_type="ranking",
            resource_id="1",
            description="will fail",
            old_values={"a": 1},
            new_values={"a": 2},
        )

    db.rollback.assert_awaited_once()
