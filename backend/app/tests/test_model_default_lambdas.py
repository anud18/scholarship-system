"""
Source-level regression tests for SQLAlchemy mutable Column defaults
fix in commit 5e7a1aa.

SQLAlchemy permits non-callable mutable defaults (`default=[]`,
`default={}`) but every row that uses the default shares the same
object instance. Application code that mutates the returned dict/list
in-place can leak state across rows. SQLAlchemy 2.0 docs explicitly
recommend callable defaults for this reason.

The fix migrated 5 columns to `default=lambda: ...`. This source-grep
test pins the invariant so a future commit dropping a lambda would
fail the suite.
"""

import inspect

from app.models import application, notification, scholarship


def _has_no_bare_mutable_default(module, kind: str = "JSON") -> list[str]:
    """Find Column declarations with bare mutable default `=[]` or `={}`."""
    src = inspect.getsource(module)
    issues = []
    # Look for `Column(JSON, ... default=[]` or `default={}`
    # without surrounding lambda
    import re

    # Pattern: `Column(...stuff..., default=[])` or default={} on same line
    for m in re.finditer(r"Column\([^)]*default=(\[\]|\{\})\s*[,)]", src):
        issues.append(m.group(0))
    return issues


def test_application_model_no_bare_mutable_default():
    issues = _has_no_bare_mutable_default(application)
    assert not issues, (
        "models/application.py has Column(...) declarations with bare mutable "
        f"defaults: {issues}. Use `default=lambda: [...]` or `default=lambda: {{}}` "
        "to avoid the shared-instance footgun. (commit 5e7a1aa)"
    )


def test_scholarship_model_no_bare_mutable_default():
    issues = _has_no_bare_mutable_default(scholarship)
    assert not issues, (
        "models/scholarship.py has Column(...) declarations with bare mutable "
        f"defaults: {issues}. Use `default=lambda: ...` (commit 5e7a1aa)"
    )


def test_notification_model_no_bare_mutable_default():
    issues = _has_no_bare_mutable_default(notification)
    assert not issues, (
        "models/notification.py has Column(...) declarations with bare mutable "
        f"defaults: {issues}. Use `default=lambda: ...` (commit 5e7a1aa)"
    )
