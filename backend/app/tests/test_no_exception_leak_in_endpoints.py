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

A second check (added in the same file) catches bare `detail=str(e)`
(no f-string wrapper) on 5xx responses. This pattern was missed by
the original sweep and was sanitized in the payment_rosters.py
RosterGenerationError handler.

A third check catches `detail={"key": str(e)}` — dict-form detail
containing str(e) values on 5xx responses. This pattern was sanitized
in applications.py (PR #721) and evaded both prior checks because
the dict wrapper hides the str(e) call from the top-level keyword scan.

A fourth check catches the class of bug fixed in PR #722: a broad
`except Exception:` (or bare `except:`) handler raising an
`HTTPException` with `detail=str(e)` on a 4xx response. The previous
three checks only covered 5xx, so this pattern evaded all guards.
Pre_authorization.py had three such sites (lines 82, 140, 252) —
all sanitized in PR #722. The invariant pins that clean state.

The checks run in <1s. No DB, no fixtures, no HTTP client.
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
        pytest.fail(msg)


# ---------------------------------------------------------------------------
# Second check: bare `detail=str(e)` on 5xx responses
# ---------------------------------------------------------------------------

_EXC_NAMES = {"e", "exc", "e2", "ex", "err", "error"}
_5XX_ATTR_PREFIXES = ("HTTP_5",)


def _detail_is_bare_str_exception(call: ast.Call) -> bool:
    """Return True iff `detail=str(<exception-name>)` (not inside f-string)."""
    for kw in call.keywords:
        if kw.arg != "detail":
            continue
        # Must be a bare Call (not a JoinedStr / f-string)
        if not isinstance(kw.value, ast.Call):
            continue
        fn = kw.value.func
        if not (isinstance(fn, ast.Name) and fn.id == "str"):
            continue
        if len(kw.value.args) != 1:
            continue
        if isinstance(kw.value.args[0], ast.Name) and kw.value.args[0].id in _EXC_NAMES:
            return True
    return False


def _status_code_is_5xx(call: ast.Call) -> bool:
    """Return True iff the status_code keyword resolves to a 5xx value."""
    for kw in call.keywords:
        if kw.arg != "status_code":
            continue
        # Literal integer: 500, 502, ...
        if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, int):
            return kw.value.value >= 500
        # Attribute access: status.HTTP_5xx or HTTP_5xx
        if isinstance(kw.value, ast.Attribute):
            attr_name = kw.value.attr
            return any(attr_name.startswith(p) for p in _5XX_ATTR_PREFIXES)
    return False


def _scan_file_5xx_bare_str(path: Path) -> list[tuple[str, int, str]]:
    """Return [(handler_name, lineno, excerpt)] for bare `detail=str(e)` on 5xx."""
    src = path.read_text()
    tree = ast.parse(src)
    findings = []
    for node in ast.walk(tree):
        if not _is_http_exception_raise(node):
            continue
        if not _detail_is_bare_str_exception(node.exc):
            continue
        if not _status_code_is_5xx(node.exc):
            continue
        handler = _enclosing_function(node, tree) or "<module>"
        excerpt = ast.unparse(node).splitlines()[0][:120]
        findings.append((handler, node.lineno, excerpt))
    return findings


def test_no_5xx_endpoint_leaks_bare_str_exception():
    """No `raise HTTPException(status_code=5xx, detail=str(e))` pattern is
    allowed in backend/app/api/v1/endpoints/. Bare str(e) on a 5xx
    response leaks internal exception context (SQL, file paths, etc.)
    to the client without going through the structured log filter.

    Fixed in payment_rosters.py RosterGenerationError handler; this test
    prevents future regressions of the same pattern."""
    violations = []
    for path in _iter_endpoint_files():
        rel = path.relative_to(ENDPOINTS_DIR)
        for handler, lineno, excerpt in _scan_file_5xx_bare_str(path):
            violations.append(f"{rel}:{lineno}  {handler}()  {excerpt!r}")

    if violations:
        msg = (
            "Found HTTPException(status_code=5xx, detail=str(e)) regressions.\n"
            "5xx responses must use a static detail string: "
            'detail="<static message>" + raise ... from e\n'
            "The traceback is captured by logger.exception() / exc_info=True "
            "and must NOT be echoed verbatim to the HTTP client.\n\n"
            "Violations:\n  " + "\n  ".join(violations)
        )
        pytest.fail(msg)
        pytest.fail(msg)


# ---------------------------------------------------------------------------
# Third check: dict-form detail containing str(e) values
# ---------------------------------------------------------------------------


def _detail_dict_contains_str_exception(call: ast.Call) -> bool:
    """Return True iff detail={"key": str(<exception-name>), ...} in any value."""
    for kw in call.keywords:
        if kw.arg != "detail":
            continue
        if not isinstance(kw.value, ast.Dict):
            continue
        for val in kw.value.values:
            if (
                isinstance(val, ast.Call)
                and isinstance(val.func, ast.Name)
                and val.func.id == "str"
                and len(val.args) == 1
                and isinstance(val.args[0], ast.Name)
                and val.args[0].id in _EXC_NAMES
            ):
                return True
    return False


def _scan_file_dict_detail_str_exception(path: Path) -> list[tuple[str, int, str]]:
    """Return [(handler_name, lineno, excerpt)] for dict-detail str(e) on 5xx."""
    src = path.read_text()
    tree = ast.parse(src)
    findings = []
    for node in ast.walk(tree):
        if not _is_http_exception_raise(node):
            continue
        if not _detail_dict_contains_str_exception(node.exc):
            continue
        if not _status_code_is_5xx(node.exc):
            continue
        handler = _enclosing_function(node, tree) or "<module>"
        excerpt = ast.unparse(node).splitlines()[0][:120]
        findings.append((handler, node.lineno, excerpt))
    return findings


def test_no_5xx_endpoint_leaks_dict_detail_str_exception():
    """No `raise HTTPException(status_code=5xx, detail={"key": str(e)})` pattern
    is allowed in backend/app/api/v1/endpoints/. Dict-wrapped str(e) values on
    5xx responses leak internal exception text (SQL fragments, column values,
    internal paths) to the client without appearing in the top-level keyword scan.

    Fixed in applications.py (PR #721); this test prevents future regressions."""
    violations = []
    for path in _iter_endpoint_files():
        rel = path.relative_to(ENDPOINTS_DIR)
        for handler, lineno, excerpt in _scan_file_dict_detail_str_exception(path):
            violations.append(f"{rel}:{lineno}  {handler}()  {excerpt!r}")

    if violations:
        msg = (
            'Found HTTPException(status_code=5xx, detail={"key": str(e)}) regressions.\n'
            "Dict-wrapped str(e) values on 5xx responses leak internal exception context.\n"
            "Use static strings only: "
            'detail={"message": "<static>", "error_code": "..."} + raise ... from e\n'
            "The traceback is captured by logger.exception() / exc_info=True "
            "and must NOT be echoed verbatim to the HTTP client.\n\n"
            "Violations:\n  " + "\n  ".join(violations)
        )
        pytest.fail(msg)


# ---------------------------------------------------------------------------
# Fourth check: broad except Exception → detail=str(e) on 4xx responses
# ---------------------------------------------------------------------------
# PR #722 fixed three such sites in pre_authorization.py (lines 82, 140, 252).
# The previous three checks only cover 5xx, so broad-except 4xx detail=str(e)
# evaded all guards. This check closes that gap.

_4XX_ATTR_PREFIXES = ("HTTP_4",)


def _status_code_is_4xx(call: ast.Call) -> bool:
    """Return True iff the status_code keyword resolves to a 4xx value."""
    for kw in call.keywords:
        if kw.arg != "status_code":
            continue
        if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, int):
            return 400 <= kw.value.value < 500
        if isinstance(kw.value, ast.Attribute):
            return any(kw.value.attr.startswith(p) for p in _4XX_ATTR_PREFIXES)
    return False


def _enclosing_handler_is_broad_except(node: ast.AST, tree: ast.AST) -> bool:
    """Return True iff `node` is lexically inside a broad except handler.

    A broad handler is either:
    - bare `except:` (handler.type is None)
    - `except Exception:` / `except BaseException:`
    """
    target_line = getattr(node, "lineno", None)
    if target_line is None:
        return False
    for try_node in ast.walk(tree):
        if not isinstance(try_node, ast.Try):
            continue
        for handler in try_node.handlers:
            h_start = getattr(handler, "lineno", None)
            h_end = getattr(handler, "end_lineno", None)
            if h_start is None or h_end is None:
                continue
            if not (h_start <= target_line <= h_end):
                continue
            # bare except:
            if handler.type is None:
                return True
            # except Exception: or except BaseException:
            if isinstance(handler.type, ast.Name) and handler.type.id in {"Exception", "BaseException"}:
                return True
            if isinstance(handler.type, ast.Attribute) and handler.type.attr in {"Exception", "BaseException"}:
                return True
    return False


def _scan_file_4xx_broad_except_str(path: Path) -> list[tuple[str, int, str]]:
    """Return [(handler_name, lineno, excerpt)] for broad-except 4xx detail=str(e)."""
    src = path.read_text()
    tree = ast.parse(src)
    findings = []
    for node in ast.walk(tree):
        if not _is_http_exception_raise(node):
            continue
        if not _detail_is_bare_str_exception(node.exc):
            continue
        if not _status_code_is_4xx(node.exc):
            continue
        if not _enclosing_handler_is_broad_except(node, tree):
            continue
        handler = _enclosing_function(node, tree) or "<module>"
        excerpt = ast.unparse(node).splitlines()[0][:120]
        findings.append((handler, node.lineno, excerpt))
    return findings


def test_no_4xx_broad_except_endpoint_leaks_detail_str_exception():
    """No broad `except Exception:` handler in backend/app/api/v1/endpoints/ may
    raise `HTTPException(status_code=4xx, detail=str(e))`.

    This pattern leaks internal exception messages (SQL, file paths, auth context,
    service error detail) to the client via 4xx responses. Because `except Exception`
    catches every application exception, the leaked string is unpredictable and
    cannot be pre-screened by the developer at write time.

    Three such sites were sanitized in pre_authorization.py by PR #722.
    This test pins that clean state and prevents future regressions.

    Intentional `except ValueError` / `except SomeSpecificError` narrow-catch
    handlers are NOT flagged — only broad catches that accept any exception type."""
    violations = []
    for path in _iter_endpoint_files():
        rel = path.relative_to(ENDPOINTS_DIR)
        for handler, lineno, excerpt in _scan_file_4xx_broad_except_str(path):
            violations.append(f"{rel}:{lineno}  {handler}()  {excerpt!r}")

    if violations:
        msg = (
            "Found broad-except 4xx detail=str(e) regressions (class of bug fixed in PR #722).\n"
            "Inside a broad `except Exception:` handler, `detail=str(e)` leaks\n"
            "arbitrary internal exception messages to the HTTP client.\n"
            "Fix: use a static detail string and let the exception chain carry the trace:\n"
            '    raise HTTPException(status_code=400, detail="<static message>") from e\n\n'
            "Violations:\n  " + "\n  ".join(violations)
        )
        pytest.fail(msg)


# ---------------------------------------------------------------------------
# Fifth check: extend exception-detail-leak coverage to services/ and utils/
# ---------------------------------------------------------------------------
# The prior four checks only scan backend/app/api/v1/endpoints/. However,
# services can also raise HTTPException directly (e.g. MinioService).
# Three such sites in minio_service.py were sanitized in PR #724; this
# check prevents future regressions in the service layer.
#
# Scope: backend/app/services/ + backend/app/utils/ (excluding
# endpoint_decorators.py which has intentional narrow-exception patterns
# where str(e) is appropriate because the exception type carries a
# user-facing message by design).
#
# Pattern caught: detail=str(e)  OR  detail=f"...{str(e)/e}..."

SERVICES_DIR = Path(__file__).resolve().parent.parent / "services"
UTILS_DIR = Path(__file__).resolve().parent.parent / "utils"

# endpoint_decorators.py uses narrow-catch exceptions (CollegeReviewAccessError,
# RankingNotFoundError, etc.) whose messages are user-facing by contract.
# Those are intentional and excluded from this check.
_SERVICES_ALLOWLIST: set[str] = {
    str(UTILS_DIR / "endpoint_decorators.py"),
}


def _iter_service_util_files() -> list[Path]:
    """Yield every .py file under services/ and utils/, excluding allowlisted files."""
    paths = []
    for base in (SERVICES_DIR, UTILS_DIR):
        if base.exists():
            paths.extend(
                p
                for p in base.rglob("*.py")
                if p.name != "__init__.py" and "__pycache__" not in p.parts and str(p) not in _SERVICES_ALLOWLIST
            )
    return sorted(paths)


def _scan_service_file(path: Path) -> list[tuple[str, int, str]]:
    """Return [(handler_name, lineno, excerpt)] for any HTTPException detail leak."""
    src = path.read_text()
    tree = ast.parse(src)
    findings = []
    for node in ast.walk(tree):
        if not _is_http_exception_raise(node):
            continue
        is_bad = _detail_is_bare_str_exception(node.exc) or _detail_is_unsanitized_fstring(node.exc)
        if not is_bad:
            continue
        handler = _enclosing_function(node, tree) or "<module>"
        excerpt = ast.unparse(node).splitlines()[0][:120]
        findings.append((handler, node.lineno, excerpt))
    return findings


def test_no_service_raises_http_exception_leaking_exception_detail():
    """No `raise HTTPException(detail=str(e))` or `detail=f"...{str(e)}..."` pattern
    is allowed in backend/app/services/ or backend/app/utils/ (excluding
    endpoint_decorators.py which uses intentional narrow-catch patterns).

    Services that raise HTTPException directly (e.g. MinioService) can leak
    internal SDK error text (bucket names, paths, error codes) to the HTTP
    client through the detail field. PR #724 sanitized 3 such sites in
    minio_service.py; this test pins that clean state.

    The traceback must reach structured logs via logger.exception() or
    exc_info=True — it must NOT be echoed verbatim to the HTTP client."""
    violations = []
    for path in _iter_service_util_files():
        for handler, lineno, excerpt in _scan_service_file(path):
            rel = path.relative_to(Path(__file__).resolve().parent.parent.parent)
            violations.append(f"{rel}:{lineno}  {handler}()  {excerpt!r}")

    if violations:
        msg = (
            "Found HTTPException(detail=str(e) / f-string) regressions in services/ or utils/.\n"
            "Services that raise HTTPException directly must use static detail strings.\n"
            "Use: raise HTTPException(status_code=5xx, detail='<static>') from e\n"
            "The full error is captured by logger.exception() and must NOT reach the client.\n\n"
            "Violations:\n  " + "\n  ".join(violations)
        )
        pytest.fail(msg)


# ---------------------------------------------------------------------------
# Sixth check: broad-except 5xx HTTPException without logger.exception before raise
# ---------------------------------------------------------------------------
# Pattern caught:
#   except Exception [as ...]:
#       ...  # no logger.exception / logger.error / logger.critical call
#       raise HTTPException(status_code=5xx, ...)
#
# When a broad except handler converts any exception to a 5xx HTTPException
# without logging first, the full traceback silently disappears. FastAPI's
# exception handler only returns the HTTP response — it does NOT log the
# chained __cause__ exception. The only way the trace reaches structured logs
# is for the handler to explicitly call logger.exception() before raising.
#
# 28 such sites were fixed across 5 endpoint files in PR #726. This invariant
# prevents future regressions. Services/ and utils/ are intentionally excluded
# here because they are covered by the fifth check (which focuses on whether
# str(e) leaks into the detail= field).


def _has_logger_call_before_raise(handler_body: list[ast.stmt], raise_line: int) -> bool:
    """Return True iff handler_body contains a logger.exception / logger.error /
    logger.critical call at a line BEFORE raise_line."""
    for stmt in handler_body:
        if getattr(stmt, "lineno", 0) >= raise_line:
            continue
        for node in ast.walk(stmt):
            if not isinstance(node, ast.Expr):
                continue
            if not isinstance(node.value, ast.Call):
                continue
            call = node.value
            if not isinstance(call.func, ast.Attribute):
                continue
            if call.func.attr not in {"exception", "error", "critical"}:
                continue
            if isinstance(call.func.value, ast.Name) and call.func.value.id in {"logger", "log"}:
                return True
    return False


def _handler_is_broad(handler: ast.ExceptHandler) -> bool:
    """Return True iff the ExceptHandler is a broad catch (bare except or except Exception)."""
    if handler.type is None:
        return True
    if isinstance(handler.type, ast.Name) and handler.type.id in {"Exception", "BaseException"}:
        return True
    if isinstance(handler.type, ast.Attribute) and handler.type.attr in {"Exception", "BaseException"}:
        return True
    return False


def _scan_file_5xx_broad_except_no_log(path: Path) -> list[tuple[str, int, str]]:
    """Return [(handler_name, lineno, excerpt)] for broad-except 5xx raises without
    a preceding logger.exception/error/critical call in the same handler body."""
    src = path.read_text()
    tree = ast.parse(src)
    findings = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        for handler in node.handlers:
            if not _handler_is_broad(handler):
                continue
            for stmt in handler.body:
                if not _is_http_exception_raise(stmt):
                    continue
                if not _status_code_is_5xx(stmt.exc):
                    continue
                raise_line = getattr(stmt, "lineno", 0)
                if _has_logger_call_before_raise(handler.body, raise_line):
                    continue
                fn = _enclosing_function(stmt, tree) or "<module>"
                excerpt = ast.unparse(stmt).splitlines()[0][:120]
                findings.append((fn, raise_line, excerpt))
    return findings


def test_no_5xx_broad_except_endpoint_missing_logger_before_raise():
    """Every broad `except Exception:` handler in backend/app/api/v1/endpoints/ that
    raises HTTPException(status_code=5xx) MUST call logger.exception() (or
    logger.error() / logger.critical()) before the raise.

    Without such a call the full traceback is silently dropped: FastAPI converts
    the HTTPException to an HTTP response and the chained __cause__ is never
    captured in structured logs. The developer has no visibility into what failed.

    28 such sites were fixed across 5 endpoint files in PR #726. This invariant
    pins that clean state and prevents future regressions.

    Fix pattern:
        except Exception as exc:
            logger.exception("<same message as detail>")
            raise HTTPException(status_code=500, detail="<static message>") from exc
    """
    violations = []
    for path in _iter_endpoint_files():
        rel = path.relative_to(ENDPOINTS_DIR)
        for fn, lineno, excerpt in _scan_file_5xx_broad_except_no_log(path):
            violations.append(f"{rel}:{lineno}  {fn}()  {excerpt!r}")

    if violations:
        msg = (
            "Found broad-except 5xx HTTPException raises with no logger.exception() before them.\n"
            "The traceback is silently dropped — FastAPI converts the HTTPException to an\n"
            "HTTP response and the __cause__ is never captured in structured logs.\n\n"
            "Fix: add `logger.exception('<message>')` as the FIRST statement in the handler:\n"
            "    except Exception as exc:\n"
            "        logger.exception('<same message as detail>')\n"
            "        raise HTTPException(status_code=500, detail='<static>') from exc\n\n"
            "PR #726 sanitized 28 such sites; do not re-introduce the pattern.\n\n"
            "Violations:\n  " + "\n  ".join(violations)
        )
        pytest.fail(msg)
