"""
Source-level regression for the traceback-preservation sweep
(PRs #574-#588 + #681 + service-layer follow-ups).

The sweep replaced every `logger.error(f"...{e}")` (no exc_info) in
backend/app/ with `logger.exception(...)` or `logger.error(...,
exc_info=True)` so structured logs capture the full stack trace
instead of just str(exc). If a future PR re-introduces the pattern
at ERROR level, this test fails before the change ships.

The check is an AST walk: it finds every `logger.error(...)` call
and verifies that if the first positional arg is an f-string
referencing `{e}` / `{exc}` / `{str(e)}` / etc., then `exc_info=`
is also passed (or the call is `logger.exception(...)` which
implicitly carries exc_info).

Scope: ERROR level only. The same pattern at WARNING level is a
separate (larger, ~47-site) cleanup tracked for a follow-up — for
many warnings the missing trace is less load-bearing because the
exception is recoverable and the message itself names the failure
mode adequately. Tightening WARNING is out of scope here.

The check runs in <1s. No DB, no fixtures, no HTTP client.
"""

import ast
from pathlib import Path

import pytest

# Module-relative path to backend/app — derived from this file's
# own location to stay stable across worktree paths.
APP_DIR = Path(__file__).resolve().parent.parent

LEAK_VARS = {"e", "exc", "e2", "ex", "err", "error"}


def _is_leak_fstring(node: ast.AST) -> bool:
    """True iff `node` is an f-string referencing an exception variable."""
    if not isinstance(node, ast.JoinedStr):
        return False
    for part in node.values:
        if not isinstance(part, ast.FormattedValue):
            continue
        if isinstance(part.value, ast.Name) and part.value.id in LEAK_VARS:
            return True
        if (
            isinstance(part.value, ast.Call)
            and isinstance(part.value.func, ast.Name)
            and part.value.func.id == "str"
            and len(part.value.args) == 1
            and isinstance(part.value.args[0], ast.Name)
            and part.value.args[0].id in LEAK_VARS
        ):
            return True
    return False


def _has_exc_info_truthy(call: ast.Call) -> bool:
    """True iff `exc_info=` keyword is present and not literally False."""
    for kw in call.keywords:
        if kw.arg != "exc_info":
            continue
        # `exc_info=False` doesn't count
        if isinstance(kw.value, ast.Constant) and kw.value.value is False:
            return False
        return True
    return False


def _is_logger_error_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "error"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "logger"
    )


def _enclosing_function(node: ast.AST, tree: ast.AST) -> str:
    target_line = getattr(node, "lineno", 0)
    candidates = [
        fn
        for fn in ast.walk(tree)
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
        and fn.lineno <= target_line <= getattr(fn, "end_lineno", target_line)
    ]
    if not candidates:
        return "<module>"
    return min(candidates, key=lambda fn: target_line - fn.lineno).name


def _iter_app_files() -> list[Path]:
    """Backend application source files, excluding tests and __pycache__."""
    return sorted(p for p in APP_DIR.rglob("*.py") if "__pycache__" not in p.parts and p.parts[-2] != "tests")


def _scan_file(path: Path) -> list[tuple[str, int, str]]:
    src = path.read_text()
    tree = ast.parse(src)
    findings = []
    for node in ast.walk(tree):
        if not _is_logger_error_call(node):
            continue
        if _has_exc_info_truthy(node):
            continue
        if not node.args or not _is_leak_fstring(node.args[0]):
            continue
        handler = _enclosing_function(node, tree)
        excerpt = ast.unparse(node).splitlines()[0][:120]
        findings.append((handler, node.lineno, excerpt))
    return findings


def test_no_logger_error_with_exception_fstring_lacks_exc_info():
    """Every `logger.error(f"...{e}")` call in backend/app/ must also
    pass `exc_info=True`, or be converted to `logger.exception(...)`.
    Without one of those, the traceback is discarded — only str(exc)
    reaches Loki."""
    violations = []
    for path in _iter_app_files():
        rel = path.relative_to(APP_DIR.parent)
        for handler, lineno, excerpt in _scan_file(path):
            violations.append(f"{rel}:{lineno}  {handler}()  {excerpt!r}")

    if violations:
        msg = (
            'Found `logger.error(f"...{e/exc/str(e)}")` calls lacking '
            "`exc_info=True`. PRs #574-#588 + #681 swept this pattern; "
            "do not re-introduce it. Use `logger.exception(...)` (which "
            "implicitly carries exc_info=True) so the full traceback "
            "lands in structured logs instead of just str(exc).\n\n"
            "Violations:\n  " + "\n  ".join(violations)
        )
        pytest.fail(msg)
