"""
Source-level regression for the traceback-preservation sweep
(PRs #574-#588 + #681 + #695 + #696 + service-layer follow-ups).

The sweep replaced every `logger.error(...)` call that interpolated
an exception variable with `logger.exception(...)` or
`logger.error(..., exc_info=True)` so structured logs capture the
full stack trace instead of just str(exc).

Two syntactic variants are guarded:
1. **f-string** — `logger.error(f"...: {e}")` (caught by #695)
2. **positional** — `logger.error("...: %s", e)` (caught by #696)

If a future PR re-introduces either pattern at ERROR level without
`exc_info=True`, this test fails before the change ships.

Scope: ERROR level only. The same pattern at WARNING level was
swept by PRs #698 + #699 but is not yet CI-guarded here — the
noise/signal tradeoff differs for WARNING (some recoverable paths
in `endpoint_decorators.py` intentionally retain f-string form for
readability since the trace would be noise).

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


def _has_exception_positional_arg(call: ast.Call) -> bool:
    """True iff any positional arg (after the format string) is a bare
    exception variable reference like `logger.error("...", e)` or a
    `str(e)` wrapper. Catches the pattern fixed by PR #696."""
    # Skip the first positional arg (the format string itself).
    for arg in call.args[1:]:
        if isinstance(arg, ast.Name) and arg.id in LEAK_VARS:
            return True
        if (
            isinstance(arg, ast.Call)
            and isinstance(arg.func, ast.Name)
            and arg.func.id == "str"
            and len(arg.args) == 1
            and isinstance(arg.args[0], ast.Name)
            and arg.args[0].id in LEAK_VARS
        ):
            return True
    return False


def _scan_file(path: Path) -> list[tuple[str, int, str, str]]:
    """Return [(handler, lineno, excerpt, kind)] for each violation.
    `kind` is 'fstring' or 'positional' so the failure message can
    point at the relevant fix recipe."""
    src = path.read_text()
    tree = ast.parse(src)
    findings = []
    for node in ast.walk(tree):
        if not _is_logger_error_call(node):
            continue
        if _has_exc_info_truthy(node):
            continue
        if not node.args:
            continue
        kind = None
        if _is_leak_fstring(node.args[0]):
            kind = "fstring"
        elif _has_exception_positional_arg(node):
            kind = "positional"
        if kind is None:
            continue
        handler = _enclosing_function(node, tree)
        excerpt = ast.unparse(node).splitlines()[0][:120]
        findings.append((handler, node.lineno, excerpt, kind))
    return findings


def test_no_logger_error_traceback_loss():
    """Every `logger.error(...)` call that interpolates an exception
    variable (either as f-string `{e}` or as positional `%s`-style
    arg) must also pass `exc_info=True`, or be converted to
    `logger.exception(...)`. Without one of those, the traceback is
    discarded — only str(exc) reaches Loki.

    PRs #574-#588 + #681 + #695 swept the f-string variant.
    PR #696 swept the positional-arg variant.
    This invariant catches regressions of either."""
    violations = []
    for path in _iter_app_files():
        rel = path.relative_to(APP_DIR.parent)
        for handler, lineno, excerpt, kind in _scan_file(path):
            violations.append(f"{rel}:{lineno}  [{kind}]  {handler}()  {excerpt!r}")

    if violations:
        msg = (
            "Found `logger.error(...)` calls that interpolate an exception "
            "variable but lack `exc_info=True`. The trace gets discarded — "
            "only str(exc) reaches structured logs. Two variants both "
            "forbidden:\n"
            '  - [fstring]    logger.error(f"...: {e}")    → '
            "logger.exception(...) (drop the {e})\n"
            '  - [positional] logger.error("...: %s", e)   → '
            "logger.exception(...) (drop the e)\n"
            "Either form, the fix is the same: use logger.exception() so "
            "exc_info is carried automatically.\n\n"
            "Violations:\n  " + "\n  ".join(violations)
        )
        pytest.fail(msg)
