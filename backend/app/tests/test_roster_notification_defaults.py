"""
Tests for `backend/app/services/roster_notification_service.py`.

Module had ZERO test references. Drives the multi-role notification
fan-out for roster generation/completion/error events. Drift in
default-role logic would silently notify the wrong audience (e.g.,
sending error alerts to non-admin processors, or omitting admins
entirely).

Wave 6a142 pins the role-default invariants without touching the
DB (NotificationService is mocked entirely).
"""

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.user import UserRole
from app.services.roster_notification_service import RosterNotificationService


def _stub_roster(**kwargs):
    """Build a PaymentRoster stand-in with the fields referenced
    by notification builders."""
    base = {
        "id": 42,
        "roster_code": "R-114-1-001",
        "period_label": "114 學年度第 1 學期",
        "qualified_count": 25,
        "disqualified_count": 0,
        "total_amount": 250000,
        "created_at": SimpleNamespace(isoformat=lambda: "2026-05-15T00:00:00Z"),
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def _stub_user(user_id):
    return SimpleNamespace(id=user_id)


class TestNotifyRosterGeneratedDefaults:
    """Pin: notify_roster_generated with default args is CURRENTLY
    BROKEN due to UserRole.processor typo (no such enum value;
    UserRole has admin/student/professor/college/super_admin).

    The top-level try/except catches the AttributeError and
    returns []. Pin actual behavior here — see issue tracking
    the underlying bug for the fix path."""

    @pytest.mark.asyncio
    async def test_default_args_raises_attribute_error_due_to_typo(self):
        # Pin BUG: default `notify_roles=None` branch references
        # UserRole.processor (does NOT exist; only admin / student /
        # professor / college / super_admin exist per CLAUDE.md §4).
        # The default-assignment line (47) is OUTSIDE the try/except
        # so the AttributeError PROPAGATES out of the method —
        # crashing whichever roster orchestrator called it.
        # Pin so refactor fixing the typo can confidently change
        # the contract from "raises" to "returns []".
        service = RosterNotificationService(db=MagicMock())
        service._get_users_by_roles = MagicMock(return_value=[_stub_user(1)])
        service.notification_service = MagicMock()
        service.notification_service.createUserNotification = AsyncMock()

        with pytest.raises(AttributeError, match="processor"):
            await service.notify_roster_generated(_stub_roster())

    @pytest.mark.asyncio
    async def test_explicit_roles_override_defaults(self):
        # Pin: caller can pass `notify_roles=[UserRole.admin]` to
        # narrow the fan-out — defaults do NOT merge with caller's
        # list.
        service = RosterNotificationService(db=MagicMock())
        service._get_users_by_roles = MagicMock(return_value=[_stub_user(1)])
        service.notification_service = MagicMock()
        service.notification_service.createUserNotification = AsyncMock()

        await service.notify_roster_generated(_stub_roster(), notify_roles=[UserRole.admin])

        called_roles = service._get_users_by_roles.call_args.args[0]
        assert called_roles == [UserRole.admin]

    @pytest.mark.asyncio
    async def test_empty_users_returns_empty_list_with_warning(self):
        # Pin: when _get_users_by_roles returns empty, returns []
        # WITHOUT calling notification_service. Pin so refactor
        # doesn't accidentally call the notification service with
        # an empty user list (which might emit a misleading "sent
        # 0 notifications" success log).
        service = RosterNotificationService(db=MagicMock())
        service._get_users_by_roles = MagicMock(return_value=[])
        service.notification_service = MagicMock()
        service.notification_service.createUserNotification = AsyncMock()

        result = await service.notify_roster_generated(_stub_roster(), notify_roles=[UserRole.admin])

        assert result == []
        service.notification_service.createUserNotification.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_list_of_notified_user_ids(self):
        # Pin: returns the list of successfully-notified user IDs
        # (NOT True/False or count). Caller uses this list to
        # downstream-log or audit.
        service = RosterNotificationService(db=MagicMock())
        service._get_users_by_roles = MagicMock(return_value=[_stub_user(7), _stub_user(13), _stub_user(99)])
        service.notification_service = MagicMock()
        service.notification_service.createUserNotification = AsyncMock()

        result = await service.notify_roster_generated(_stub_roster(), notify_roles=[UserRole.admin])

        assert result == [7, 13, 99]
        assert service.notification_service.createUserNotification.await_count == 3

    @pytest.mark.asyncio
    async def test_per_user_exception_isolated(self):
        # Pin SECURITY: a failing notification for ONE user does
        # NOT block notifications to subsequent users. Pin so
        # refactor changing to "fail fast" doesn't silently drop
        # admin notifications because one processor's
        # notification storage failed.
        service = RosterNotificationService(db=MagicMock())
        service._get_users_by_roles = MagicMock(return_value=[_stub_user(1), _stub_user(2), _stub_user(3)])
        service.notification_service = MagicMock()
        service.notification_service.createUserNotification = AsyncMock(
            side_effect=[
                None,  # user 1 succeeds
                RuntimeError("broken pipe"),  # user 2 fails
                None,  # user 3 succeeds
            ]
        )

        result = await service.notify_roster_generated(_stub_roster(), notify_roles=[UserRole.admin])

        # User 2 omitted from notified_users list; 1 and 3 included.
        assert result == [1, 3]


class TestNotifyRosterErrorDefaults:
    """Pin: notify_roster_error defaults to admin-ONLY (NOT processor).

    SECURITY: error notifications go to admin alone because they
    require human intervention. Processors handling roster ops
    shouldn't get spammed with errors from outside their scope.
    """

    @pytest.mark.asyncio
    async def test_error_default_role_is_admin_only(self):
        # Pin SECURITY: error notifications go to admin ONLY (NOT
        # admin + processor). Pin so refactor adding processor
        # silently spams the team with errors they can't act on.
        service = RosterNotificationService(db=MagicMock())
        service._get_users_by_roles = MagicMock(return_value=[_stub_user(1)])
        service.notification_service = MagicMock()
        service.notification_service.createUserNotification = AsyncMock()

        await service.notify_roster_error(error_data={"config_name": "nstc-114-1", "error": "missing quota"})

        called_roles = service._get_users_by_roles.call_args.args[0]
        assert called_roles == [UserRole.admin]
        # Per CLAUDE.md §4: UserRole has admin/student/professor/college/super_admin.
        # No `processor` exists.
        assert not any(r.value == "processor" for r in called_roles if hasattr(r, "value"))


class TestNotifyRosterCompletedDefaults:
    """Pin: notify_roster_completed default args ALSO broken
    (same UserRole.processor typo). See issue."""

    @pytest.mark.asyncio
    async def test_completed_default_args_raises_due_to_typo(self):
        # Pin BUG: same UserRole.processor typo in
        # notify_roster_completed default branch. AttributeError
        # propagates (default-assignment is OUTSIDE try/except).
        service = RosterNotificationService(db=MagicMock())
        service._get_users_by_roles = MagicMock(return_value=[_stub_user(1)])
        service.notification_service = MagicMock()
        service.notification_service.createUserNotification = AsyncMock()

        with pytest.raises(AttributeError, match="processor"):
            await service.notify_roster_completed(
                roster=_stub_roster(),
                statistics={"qualified_count": 25, "total_amount": 250000},
            )

    @pytest.mark.asyncio
    async def test_completed_with_explicit_admin_role_works(self):
        # Pin: passing an explicit role list works correctly (skips
        # the broken default branch).
        service = RosterNotificationService(db=MagicMock())
        service._get_users_by_roles = MagicMock(return_value=[_stub_user(1)])
        service.notification_service = MagicMock()
        service.notification_service.createUserNotification = AsyncMock()

        result = await service.notify_roster_completed(
            roster=_stub_roster(),
            statistics={"qualified_count": 25, "total_amount": 250000},
            notify_roles=[UserRole.admin],
        )
        assert result == [1]


class TestTopLevelExceptionFallthrough:
    """Pin: top-level exception in any notify_* method returns []
    (NOT raise). Roster generation orchestrator depends on this
    so notification failures don't crash the roster job."""

    @pytest.mark.asyncio
    async def test_top_level_exception_returns_empty_list(self):
        # Pin: when _get_users_by_roles RAISES (e.g., DB error),
        # the notify_roster_generated method returns [] instead
        # of propagating. Pin so notification failures NEVER
        # crash the upstream roster-generation job.
        service = RosterNotificationService(db=MagicMock())
        service._get_users_by_roles = MagicMock(side_effect=RuntimeError("db connection lost"))

        result = await service.notify_roster_generated(_stub_roster(), notify_roles=[UserRole.admin])
        assert result == []

    @pytest.mark.asyncio
    async def test_error_notify_top_level_exception_returns_empty(self):
        service = RosterNotificationService(db=MagicMock())
        service._get_users_by_roles = MagicMock(side_effect=RuntimeError("db connection lost"))

        result = await service.notify_roster_error(error_data={"error": "x"})
        assert result == []
