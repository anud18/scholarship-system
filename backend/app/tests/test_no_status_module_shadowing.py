"""AST invariant: never shadow the `status` module with a parameter named `status`.

`from fastapi import status` is the project-wide idiom for HTTP constants. An
endpoint that also declares a parameter named `status` (a very natural name for
a filter) rebinds the name locally, so every `status.HTTP_*` lookup in that
function raises AttributeError at runtime.

This is not hypothetical. `admin/bank_verification.py::list_verification_tasks`
shipped with exactly this bug: passing an invalid `?status=` value tried to
raise a 400, hit `'str' object has no attribute 'HTTP_400_BAD_REQUEST'`, and
returned 500 instead. The 2026-08-06 ZAP active scan hit it 212 times.

The fix is `Query(None, alias="status")` on a differently-named parameter, which
keeps the wire contract while freeing the module name.

Sibling invariants: test_no_logger_warning_traceback_loss.py,
test_no_logger_error_traceback_loss.py.
"""

import ast
import pathlib

APP_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _iter_python_files():
    for path in APP_ROOT.rglob("*.py"):
        if "tests" in path.parts:
            continue
        yield path


def _shadowing_violations(tree, path):
    violations = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        arg_names = {a.arg for a in node.args.args + node.args.kwonlyargs + node.args.posonlyargs}
        if "status" not in arg_names:
            continue

        # The parameter shadows the module only if the body actually reads
        # `status.HTTP_*`; a handler that never touches the constants is fine.
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Attribute)
                and isinstance(inner.value, ast.Name)
                and inner.value.id == "status"
                and inner.attr.startswith("HTTP_")
            ):
                violations.append(
                    f"{path.relative_to(APP_ROOT.parent)}:{inner.lineno} "
                    f"in {node.name}(): parameter 'status' shadows the fastapi "
                    f"status module, so 'status.{inner.attr}' raises AttributeError. "
                    f"Rename the parameter and use Query(..., alias='status')."
                )
                break
    return violations


def test_no_endpoint_shadows_the_status_module():
    violations = []
    for path in _iter_python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        violations.extend(_shadowing_violations(tree, path))

    assert not violations, "status-module shadowing detected:\n" + "\n".join(violations)
