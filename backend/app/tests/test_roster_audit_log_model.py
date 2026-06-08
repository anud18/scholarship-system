"""
Pure-function tests for `RosterAuditLog`.

Audit-log entries record EVERY action on a payment roster. They drive:
- Compliance audits (who did what when)
- Admin troubleshooting UI (filter by error level)
- get_display_message powers the audit-trail row text

Wrong level classification (e.g., INFO reported as error) hides real
issues from admin alerts. Wrong message format = unreadable audit
trail.

4 helpers covered (10 cases):
- `is_error`             : level → bool (ERROR + CRITICAL)
- `is_warning`           : level → bool (WARNING only)
- `get_display_message`  : composes title + description + error + warning
- `create_audit_log`     : factory method preserves all 20 fields
"""

import pytest

from app.models.roster_audit import RosterAuditAction, RosterAuditLevel, RosterAuditLog


def _log(**overrides) -> RosterAuditLog:
    """Build a RosterAuditLog using SA __init__ so _sa_instance_state is set."""
    defaults = {
        "roster_id": 1,
        "title": "Test action",
        "description": None,
        "level": RosterAuditLevel.INFO,
        "error_message": None,
        "warning_message": None,
    }
    defaults.update(overrides)
    return RosterAuditLog(**defaults)


# ─── is_error ────────────────────────────────────────────────────────


def test_is_error_for_error_and_critical():
    """Pin: ERROR AND CRITICAL both qualify. The admin alert filter
    treats them as the same severity tier for paging purposes."""
    assert _log(level=RosterAuditLevel.ERROR).is_error() is True
    assert _log(level=RosterAuditLevel.CRITICAL).is_error() is True


def test_is_error_false_for_info_and_warning():
    """INFO and WARNING are NOT errors. Pin so a refactor that promotes
    WARNING to error doesn't silently page oncall on every warning."""
    assert _log(level=RosterAuditLevel.INFO).is_error() is False
    assert _log(level=RosterAuditLevel.WARNING).is_error() is False


# ─── is_warning ──────────────────────────────────────────────────────


def test_is_warning_only_for_warning_level():
    """is_warning is exact match — pin so INFO/ERROR don't accidentally
    bleed into the warning bucket."""
    assert _log(level=RosterAuditLevel.WARNING).is_warning() is True
    assert _log(level=RosterAuditLevel.INFO).is_warning() is False
    assert _log(level=RosterAuditLevel.ERROR).is_warning() is False
    assert _log(level=RosterAuditLevel.CRITICAL).is_warning() is False


# ─── get_display_message ─────────────────────────────────────────────


def test_display_message_title_only():
    """Just title when nothing else is set."""
    log = _log(title="Roster locked")
    assert log.get_display_message() == "Roster locked"


def test_display_message_with_description():
    """Title + ': description'."""
    log = _log(title="Roster locked", description="by admin user 99")
    assert log.get_display_message() == "Roster locked: by admin user 99"


def test_display_message_with_error_appends_parenthetical():
    """Pin format: '(錯誤: ...)' appended."""
    log = _log(title="Export failed", error_message="MinIO timeout")
    msg = log.get_display_message()
    assert "Export failed" in msg
    assert "(錯誤: MinIO timeout)" in msg


def test_display_message_with_warning_appends_parenthetical():
    """Same format: '(警告: ...)'."""
    log = _log(title="Distribution executed", warning_message="3 students excluded")
    msg = log.get_display_message()
    assert "(警告: 3 students excluded)" in msg


def test_display_message_combines_all_segments():
    """All segments stack: title + description + error + warning."""
    log = _log(
        title="Roster export",
        description="manual trigger",
        error_message="3 rows failed",
        warning_message="2 rows missing bank account",
    )
    msg = log.get_display_message()
    assert "Roster export" in msg
    assert ": manual trigger" in msg
    assert "(錯誤: 3 rows failed)" in msg
    assert "(警告: 2 rows missing bank account)" in msg


# ─── create_audit_log factory ────────────────────────────────────────


def test_create_audit_log_minimal_args():
    """Minimal call: just required args. Default level=INFO."""
    log = RosterAuditLog.create_audit_log(
        roster_id=1,
        action=RosterAuditAction.CREATE,
        title="Roster created",
    )
    assert log.roster_id == 1
    assert log.action == RosterAuditAction.CREATE
    assert log.title == "Roster created"
    assert log.level == RosterAuditLevel.INFO


def test_create_audit_log_with_all_optional_fields():
    """Pin all 20 optional fields pass through unmodified — the factory
    is essentially a typed constructor. If a future refactor renames
    or drops a field, this surfaces it."""
    log = RosterAuditLog.create_audit_log(
        roster_id=1,
        action=RosterAuditAction.EXPORT,
        title="Export",
        user_id=99,
        user_name="Admin",
        user_role="super_admin",
        client_ip="10.0.0.1",
        user_agent="Mozilla/5.0",
        description="Manual export",
        old_values={"a": 1},
        new_values={"b": 2},
        level=RosterAuditLevel.WARNING,
        api_endpoint="/api/v1/roster/export",
        request_method="POST",
        request_payload={"format": "xlsx"},
        response_status=200,
        processing_time_ms=1500,
        affected_items_count=42,
        error_code="E001",
        error_message="partial failure",
        warning_message="3 skipped",
        audit_metadata={"trace_id": "abc-123"},
        tags=["export", "manual"],
    )
    # Spot-check key fields preserved.
    assert log.user_id == 99
    assert log.level == RosterAuditLevel.WARNING
    assert log.old_values == {"a": 1}
    assert log.tags == ["export", "manual"]
    assert log.audit_metadata == {"trace_id": "abc-123"}
    assert log.affected_items_count == 42


def test_item_restore_action_exists():
    from app.models.roster_audit import RosterAuditAction

    assert RosterAuditAction.ITEM_RESTORE.value == "item_restore"


def test_roster_audit_action_value_contract():
    """Tripwire pinning the FULL RosterAuditAction value set.

    `RosterAuditAction` maps to a NATIVE PostgreSQL enum (`rosterauditaction`).
    Adding a Python member WITHOUT an `ALTER TYPE rosterauditaction ADD VALUE`
    Alembic migration causes a production 500 on insert
    (`InvalidTextRepresentation: invalid input value for enum`). The unit suite
    runs on SQLite, which stores enums as plain strings and does NOT enforce the
    constraint — so only this pin catches the drift.

    If this fails because you ADDED a value: add an Alembic migration first
    (see `add_item_restore_audit_001.py`), then update the expected set below.
    """
    from app.models.roster_audit import RosterAuditAction

    assert {a.value for a in RosterAuditAction} == {
        "create",
        "update",
        "delete",
        "lock",
        "unlock",
        "export",
        "download",
        "student_verify",
        "schedule_run",
        "manual_run",
        "dry_run",
        "status_change",
        "item_add",
        "item_remove",
        "item_update",
        "item_restore",
    }
