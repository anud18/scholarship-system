"""
Source-level regression for the exception-detail-leak SECURITY sweep
(PRs #684 + #685 + #686 + #687, total 71 sites sanitized).

The sweep replaced every `HTTPException(detail=f"<msg>: {str(e)}")`
(or `{e}`) in backend/app/api/v1/endpoints/ with a sanitized
`detail="<msg>"`, on the rationale that interpolating the internal
exception message into the client-facing `detail` field leaks
context (MinIO bucket paths, SQL fragments, file-system paths,
authentication error contexts, etc.) to attackers.

If a future PR re-introduces the pattern, this test fails before
the change ships. The check is an AST walk: it finds every
`raise HTTPException(...)` call and verifies the `detail` keyword
argument is not an f-string containing a `{str(e)}` / `{e}` /
`{exc}` interpolation.

One intentional retention is allowlisted (email_management.py
template-variable KeyError — see SECURITY comment in PR #686).

The check runs in <1s. No DB, no fixtures, no HTTP client.
"""

import ast
from pathlib import Path

import pytest

# Module-relative path to backend/app/api/v1/endpoints — derived from
# this file's own location to stay stable across worktree paths.
ENDPOINTS_DIR = Path(__file__).resolve().parent.parent / "api" / "v1" / "endpoints"


# (module-relative path, handler_name, status_code, reason) — allowlist
# of intentional retentions documented in their source via SECURITY
# comment. Verified manually in PR #686.
ALLOWLIST: set[tuple[str, str]] = {
    ("email_management.py", "send_test_email"),
}


def _iter_endpoint_files() -> list[Path]:
    """Recursively yield every .py file under backend/app/api/v1/endpoints,
    excluding __init__.py and __pycache__."""
    return sorted(p for p in ENDPOINTS_DIR.rglob("*.py") if p.name != "__init__.py" and "__pycache__" not in p.parts)


def _detail_is_unsanitized_fstring(call: ast.Call) -> bool:
    """Return True iff this `raise HTTPException(...)` call has a
    `detail=f"...{str(e)} | {e} | {exc} | {e2}..."` keyword arg."""
    for kw in call.keywords:
        if kw.arg != "detail":
            continue
        # f-string is a JoinedStr in the AST
        if not isinstance(kw.value, ast.JoinedStr):
            continue
        # Walk each FormattedValue and check the expression
        for part in kw.value.values:
            if not isinstance(part, ast.FormattedValue):
                continue
            # `{e}` / `{exc}` / `{e2}` / etc.
            if isinstance(part.value, ast.Name) and part.value.id in {"e", "exc", "e2", "ex", "err", "error"}:
                return True
            # `{str(e)}` / `{str(exc)}`
            if (
                isinstance(part.value, ast.Call)
                and isinstance(part.value.func, ast.Name)
                and part.value.func.id == "str"
                and len(part.value.args) == 1
                and isinstance(part.value.args[0], ast.Name)
                and part.value.args[0].id in {"e", "exc", "e2", "ex", "err", "error"}
            ):
                return True
    return False


def _is_http_exception_raise(stmt: ast.AST) -> bool:
    return (
        isinstance(stmt, ast.Raise)
        and isinstance(stmt.exc, ast.Call)
        and (
            (isinstance(stmt.exc.func, ast.Name) and stmt.exc.func.id == "HTTPException")
            or (isinstance(stmt.exc.func, ast.Attribute) and stmt.exc.func.attr == "HTTPException")
        )
    )


def _enclosing_function(node: ast.AST, tree: ast.AST) -> str | None:
    """Find the function (sync or async) that lexically contains `node`.
    Returns the function name or None if at module scope."""
    target_line = getattr(node, "lineno", None)
    if target_line is None:
        return None
    candidates = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if fn.lineno <= target_line <= getattr(fn, "end_lineno", target_line):
            candidates.append(fn)
    if not candidates:
        return None
    return min(candidates, key=lambda fn: target_line - fn.lineno).name


def _scan_file(path: Path) -> list[tuple[str, int, str]]:
    """Return [(handler_name, lineno, source_excerpt)] for each
    unsanitized HTTPException-detail-f-string call in the file."""
    src = path.read_text()
    tree = ast.parse(src)
    findings = []
    for node in ast.walk(tree):
        if not _is_http_exception_raise(node):
            continue
        if not _detail_is_unsanitized_fstring(node.exc):
            continue
        handler = _enclosing_function(node, tree) or "<module>"
        excerpt = ast.unparse(node).splitlines()[0][:120]
        findings.append((handler, node.lineno, excerpt))
    return findings


def test_no_endpoint_raises_http_exception_leaking_exception_detail():
    """Every `raise HTTPException(detail=f"...{e}")` pattern in
    backend/app/api/v1/endpoints/ must have been sanitized by
    PRs #684-#687. New code that re-introduces it fails this test."""
    violations = []
    for path in _iter_endpoint_files():
        rel = path.relative_to(ENDPOINTS_DIR)
        for handler, lineno, excerpt in _scan_file(path):
            if (str(rel), handler) in ALLOWLIST:
                continue
            violations.append(f"{rel}:{lineno}  {handler}()  {excerpt!r}")

    if violations:
        msg = (
            'Found HTTPException(detail=f"...{e/exc/str(e)}") regressions. '
            "PRs #684-#687 sanitized 71 such sites; do not re-introduce "
            'the leak pattern. Use detail="<message>" + `raise ... from e` '
            "instead, so the trace lands in structured logs without "
            "echoing internal exception text to the client.\n\n"
            "Violations:\n  " + "\n  ".join(violations)
        )
        pytest.fail(msg)
