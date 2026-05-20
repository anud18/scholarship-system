"""
Source-level regression for the WARNING-level traceback-preservation
sweep (PRs #698 + #699 + #701 + #702).

Mirrors `test_no_logger_error_traceback_loss.py` but for `logger.warning(...)`.
WARNING is swept *with one documented exception*: the four business-error
handlers in `utils/endpoint_decorators.py::wrapper` intentionally retain
f-string form because they map known recoverable errors
(ReviewPermissionError, RankingNotFoundError, RankingModificationError,
ValueError) to specific HTTP 4xx responses — the trace would be noise
since the exception is already understood and routed.

Two syntactic variants are guarded:
1. **f-string** — `logger.warning(f"...: {e}")` (caught by PRs #698/#699/#702)
2. **positional** — `logger.warning("...: %s", e)` (caught by PRs #701/#702)

If a future PR re-introduces either pattern at WARNING level without
`exc_info=True`, this test fails before the change ships.

The check runs in <1s. No DB, no fixtures, no HTTP client.
"""

import ast
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parent.parent

LEAK_VARS = {"e", "exc", "e2", "ex", "err", "error"}

# Allowlist: (relative-to-app posix path, enclosing function name)
# Documented in source via a SECURITY comment so future readers can find it.
ALLOWLIST = {
    ("utils/endpoint_decorators.py", "wrapper"),
}


def _is_leak_fstring(node: ast.AST) -> bool:
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
    for kw in call.keywords:
        if kw.arg != "exc_info":
            continue
        if isinstance(kw.value, ast.Constant) and kw.value.value is False:
            return False
        return True
    return False


def _is_logger_warning_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "warning"
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
    return sorted(p for p in APP_DIR.rglob("*.py") if "__pycache__" not in p.parts and p.parts[-2] != "tests")


def _has_exception_positional_arg(call: ast.Call) -> bool:
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
    src = path.read_text()
    tree = ast.parse(src)
    findings = []
    for node in ast.walk(tree):
        if not _is_logger_warning_call(node):
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


def test_no_logger_warning_traceback_loss():
    """Every `logger.warning(...)` call that interpolates an exception
    variable (either as f-string `{e}` or as positional `%s`-style arg)
    must also pass `exc_info=True`, or be converted to
    `logger.exception(...)`. Otherwise the trace gets discarded.

    PRs #698 + #699 + #701 + #702 swept the WARNING-level surface
    across utils/core/db/services/cache/endpoints. The four sites in
    `utils/endpoint_decorators.py::wrapper` are intentionally retained
    (HTTP-mapped business errors — trace would be noise) and live in
    the ALLOWLIST."""
    violations = []
    for path in _iter_app_files():
        rel = path.relative_to(APP_DIR.parent)
        rel_to_app = path.relative_to(APP_DIR).as_posix()
        for handler, lineno, excerpt, kind in _scan_file(path):
            if (rel_to_app, handler) in ALLOWLIST:
                continue
            violations.append(f"{rel}:{lineno}  [{kind}]  {handler}()  {excerpt!r}")

    if violations:
        msg = (
            "Found `logger.warning(...)` calls that interpolate an exception "
            "variable but lack `exc_info=True`. The trace gets discarded — "
            "only str(exc) reaches structured logs. Two variants both "
            "forbidden:\n"
            '  - [fstring]    logger.warning(f"...: {e}")    → '
            "logger.exception(...) (drop the {e}) — or logger.warning(..., exc_info=True)\n"
            '  - [positional] logger.warning("...: %s", e)   → '
            "logger.exception(...) (drop the e) — or logger.warning(..., exc_info=True)\n"
            "If a site needs to stay at WARNING level without a trace "
            "(e.g. recoverable business-error mapper in endpoint_decorators.py), "
            "add it to the ALLOWLIST in this test file with a SECURITY "
            "comment at the source site documenting why.\n\n"
            "Violations:\n  " + "\n  ".join(violations)
        )
        pytest.fail(msg)
