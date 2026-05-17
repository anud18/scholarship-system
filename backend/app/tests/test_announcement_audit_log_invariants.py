"""
Source-level regression for the SECURITY audit-log decorators added by
PR #659 (canonical admin/announcements.py) and PR #680 (orphan
notifications.py /admin/announcements handlers).

Both handler families MUST emit a `logger.info(...)` on the success path
of every mutation (CREATE / UPDATE / DELETE) recording at minimum the
`actor_user_id` extra. If a future refactor removes any of these
`logger.info` calls, this suite catches it before the change ships.

The pattern parallels test_auth_rate_limit_invariants.py — source-level
AST inspection rather than runtime mock — so the test does not require
a database, HTTP client, or fixtures.
"""

import ast
import inspect

from app.api.v1.endpoints import notifications
from app.api.v1.endpoints.admin import announcements


def _function_has_logger_info_with_actor(module, func_name: str) -> bool:
    """Return True if `func_name` in `module` contains a logger.info(...)
    call somewhere in its body whose `extra` keyword argument includes
    an `actor_user_id` key. Walks the AST so reorderings / refactors
    inside the function don't false-positive."""
    src = inspect.getsource(module)
    tree = ast.parse(src)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            for sub in ast.walk(node):
                if not isinstance(sub, ast.Call):
                    continue
                # match logger.info(...) calls
                if not (
                    isinstance(sub.func, ast.Attribute)
                    and sub.func.attr == "info"
                    and isinstance(sub.func.value, ast.Name)
                    and sub.func.value.id == "logger"
                ):
                    continue
                # check for extra= kwarg with actor_user_id key
                for kw in sub.keywords:
                    if kw.arg != "extra":
                        continue
                    if isinstance(kw.value, ast.Dict):
                        for k in kw.value.keys:
                            if isinstance(k, ast.Constant) and k.value == "actor_user_id":
                                return True
            return False
    return False


# ---------------------------------------------------------------------------
# Canonical admin/announcements.py (PR #659)
# ---------------------------------------------------------------------------


def test_canonical_create_announcement_audits():
    assert _function_has_logger_info_with_actor(announcements, "create_announcement"), (
        "admin/announcements.create_announcement must emit "
        "logger.info(..., extra={'actor_user_id': ...}) on success (PR #659)."
    )


def test_canonical_update_announcement_audits():
    assert _function_has_logger_info_with_actor(announcements, "update_announcement"), (
        "admin/announcements.update_announcement must emit "
        "logger.info(..., extra={'actor_user_id': ...}) on success (PR #659)."
    )


def test_canonical_delete_announcement_audits():
    assert _function_has_logger_info_with_actor(announcements, "delete_announcement"), (
        "admin/announcements.delete_announcement must emit "
        "logger.info(..., extra={'actor_user_id': ...}) on success (PR #659)."
    )


# ---------------------------------------------------------------------------
# Orphan notifications.py /admin/announcements* (PR #680)
#
# These handlers are flagged for product triage in #665/#679. If
# product decides to delete them, removing both the handler *and* this
# test together is the expected workflow — this test will catch
# accidental removal of audit-log without removing the orphan handler.
# ---------------------------------------------------------------------------


def test_orphan_create_system_announcement_audits():
    assert _function_has_logger_info_with_actor(notifications, "createSystemAnnouncement"), (
        "notifications.createSystemAnnouncement (orphan route) must emit "
        "logger.info(..., extra={'actor_user_id': ...}) on success (PR #680)."
    )


def test_orphan_create_test_notifications_audits():
    assert _function_has_logger_info_with_actor(notifications, "createTestNotifications"), (
        "notifications.createTestNotifications (orphan route) must emit "
        "logger.info(..., extra={'actor_user_id': ...}) on success (PR #680)."
    )
