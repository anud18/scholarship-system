"""
Source-level regression for the auth rate-limit decorators added in
commit 001b14b. The three brute-force-prone endpoints in
api/v1/endpoints/auth.py — register, login, mock_sso_login — must
have a `@rate_limit(...)` decorator above the route handler.

If a future refactor removes any of these decorators, the suite catches
it before the change ships.
"""

import inspect
import re

from app.api.v1.endpoints import auth


def _function_decorators(module, func_name: str) -> list[str]:
    """Return the lines immediately above `async def func_name(` so we
    can assert decorators are present. inspect.getsource on the function
    itself doesn't include decorators, so grep the module source instead."""
    src = inspect.getsource(module)
    # find the function definition line and walk backward grabbing
    # contiguous decorator/comment lines
    lines = src.splitlines()
    for i, line in enumerate(lines):
        if re.match(rf"\s*async def {func_name}\b", line):
            # walk backward
            decorators = []
            j = i - 1
            while j >= 0 and (lines[j].lstrip().startswith("@") or lines[j].strip() == ""):
                if lines[j].lstrip().startswith("@"):
                    decorators.append(lines[j].strip())
                j -= 1
            return decorators
    return []


def test_register_has_rate_limit_decorator():
    decorators = _function_decorators(auth, "register")
    assert any(d.startswith("@rate_limit") for d in decorators), (
        "auth.register must have @rate_limit decorator (commit 001b14b). "
        f"Found decorators: {decorators}"
    )


def test_login_has_rate_limit_decorator():
    decorators = _function_decorators(auth, "login")
    assert any(d.startswith("@rate_limit") for d in decorators), (
        "auth.login must have @rate_limit decorator (commit 001b14b). "
        f"Found decorators: {decorators}"
    )


def test_mock_sso_login_has_rate_limit_decorator():
    decorators = _function_decorators(auth, "mock_sso_login")
    assert any(d.startswith("@rate_limit") for d in decorators), (
        "auth.mock_sso_login must have @rate_limit decorator (commit 001b14b). "
        f"Found decorators: {decorators}"
    )
