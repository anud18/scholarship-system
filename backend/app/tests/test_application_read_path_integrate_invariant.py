"""AST invariant: every application-detail read path must integrate file data
through ``ApplicationService._integrate_application_file_data``.

Background
---------
Uploaded documents live in TWO places that must be reconciled on read: the
``application_files`` relationship (real ``object_name`` + ``file_id``) and the
``submitted_form_data.documents[]`` JSON (which the frontend writes with only a
local filename). The single source of truth that reconciles them — creating /
enriching a ``documents[]`` entry with ``file_id`` + a proxy-resolvable
``file_path`` for every ``application.file`` — is
``_integrate_application_file_data``.

The original preview bug (#885) was precisely that ``get_application_by_id``
used an inferior **inline** enrichment loop INSTEAD of calling the helper, so a
draft reopened with its uploaded files dropped and a bogus ``file_path`` (the
local filename) that the preview iframe 404s on. #890 consolidated six read
paths onto the helper.

The helper itself is unit-tested (``test_application_service_integration.py``),
but those tests pass regardless of whether the read paths CALL it — so a future
refactor that reverts any path to an inline loop would reintroduce #885 with a
green test suite. This invariant pins the wiring: each known application-detail
read method must contain a call to ``self._integrate_application_file_data``.
It fails the moment one stops delegating to the helper.

See ``project_document_preview_failure_rootcauses`` — this closes the one
documented open guard gap among the five preview-failure root causes.
"""

import ast
from pathlib import Path

import pytest

SERVICE_FILE = Path(__file__).resolve().parents[1] / "services" / "application_service.py"

# Application-detail read paths that surface uploaded documents and therefore
# MUST reconcile application_files into submitted_form_data.documents[] via the
# helper. Keep this set in sync when adding a new read path that returns
# documents — do NOT delete an entry to silence the test; rewire the method to
# call the helper instead.
READ_PATHS_REQUIRING_INTEGRATION = frozenset(
    {
        "get_user_applications",
        "get_student_dashboard_stats",
        "get_application_by_id",
        "submit_application",
        "get_applications_for_review",
        "get_applications",
    }
)

HELPER = "_integrate_application_file_data"


def _method_calls_helper(func: ast.AST) -> bool:
    """True iff the function body calls ``self._integrate_application_file_data``."""
    for node in ast.walk(func):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == HELPER:
            return True
    return False


def _application_service_methods() -> dict:
    tree = ast.parse(SERVICE_FILE.read_text(encoding="utf-8"))
    cls = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "ApplicationService"),
        None,
    )
    assert cls is not None, "ApplicationService class not found"
    return {n.name: n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def test_read_paths_exist():
    """Guard against a rename silently shrinking the checked set."""
    methods = _application_service_methods()
    missing = READ_PATHS_REQUIRING_INTEGRATION - set(methods)
    assert not missing, (
        f"Read-path methods no longer exist in ApplicationService: {sorted(missing)}. "
        "If renamed, update READ_PATHS_REQUIRING_INTEGRATION (and confirm the new "
        f"method still calls self.{HELPER})."
    )


@pytest.mark.parametrize("method_name", sorted(READ_PATHS_REQUIRING_INTEGRATION))
def test_read_path_delegates_to_integrate_helper(method_name):
    methods = _application_service_methods()
    func = methods[method_name]
    assert _method_calls_helper(func), (
        f"ApplicationService.{method_name} no longer calls self.{HELPER}. "
        "Application-detail read paths must reconcile application_files into "
        "submitted_form_data.documents[] via the helper — an inline enrichment "
        "loop reintroduces the #885 preview bug (dropped uploads / bogus "
        "file_path that the preview iframe 404s on). Re-wire to the helper "
        "rather than hand-rolling the loop."
    )
