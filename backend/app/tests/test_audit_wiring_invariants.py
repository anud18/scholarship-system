"""AST invariants: history-critical mutation endpoints must write audit logs.

Born from the 2026-06-11 申請歷史 audit (tracking #995). Three whole modules
mutated long-retention, money-relevant records with ZERO audit trail:

  - batch_import.py (G2 / #964): create/update/delete hundreds of
    applications per call;
  - whitelist mutations (G10 / #972): control who is eligible to apply;
  - renewal.py creations (G11 / #973): renewal/challenge applications.

These tests walk the AST of each module and fail when a listed function no
longer references an audit emitter (`AuditLog` / `ApplicationAuditService`),
so the wiring added for those gaps cannot silently regress. They also pin
that manual_distribution writes audit through the typed service rather than
ad-hoc action strings (G18 / #980).

Sync + pure-AST on purpose: they run in the CI `unit` lane with no DB.
"""

import ast
import pathlib

import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[1]

AUDIT_MARKERS = {"AuditLog", "ApplicationAuditService"}

# module path (relative to app/) -> async endpoint functions that MUST audit
REQUIRED_WIRING = {
    "api/v1/endpoints/batch_import.py": [
        "upload_batch_import_data",
        "update_batch_record",
        "delete_batch_record",
        "upload_batch_documents",
        "confirm_batch_import",
        "delete_batch_import",
    ],
    "api/v1/endpoints/scholarships.py": [
        "add_student_to_whitelist",
        "toggle_scholarship_whitelist",
    ],
    "api/v1/endpoints/scholarship_configurations.py": [
        "batch_add_whitelist",
        "batch_remove_whitelist",
        "import_whitelist_excel",
    ],
    "api/v1/endpoints/renewal.py": [
        "create_renewal_application",
        "create_challenge_application",
    ],
    "api/v1/endpoints/manual_distribution.py": [
        "revoke_application_allocation",
        "suspend_application_allocation",
        "restore_application_allocation",
    ],
}


def _function_references_audit(fn: ast.AST) -> bool:
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and node.id in AUDIT_MARKERS:
            return True
        if isinstance(node, ast.Attribute) and node.attr in AUDIT_MARKERS:
            return True
    return False


def _functions_of(path: pathlib.Path) -> dict:
    tree = ast.parse(path.read_text())
    return {node.name: node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


@pytest.mark.parametrize(
    "module, function_name",
    [(m, f) for m, fns in REQUIRED_WIRING.items() for f in fns],
)
def test_mutation_endpoint_writes_audit(module, function_name):
    path = BACKEND / module
    assert path.exists(), f"{module} moved — update REQUIRED_WIRING"
    functions = _functions_of(path)
    assert function_name in functions, (
        f"{module}::{function_name} not found — if it was renamed, update "
        f"REQUIRED_WIRING; if it was removed, its audit obligation moved somewhere."
    )
    assert _function_references_audit(functions[function_name]), (
        f"{module}::{function_name} mutates history-critical records but no "
        f"longer references AuditLog/ApplicationAuditService — re-wire the "
        f"audit emit (see #995 gaps G2/G10/G11/G18)."
    )


def test_no_adhoc_application_action_strings():
    """G18: allocation lifecycle actions must live in the AuditAction enum.

    The old code wrote action="application.revoke"/"application.suspend"/
    "application.restore" — strings invisible to the enum and the contract
    suite. Any reappearance anywhere under app/ is a regression.
    """
    offenders = []
    for path in BACKEND.rglob("*.py"):
        if "tests" in path.parts:
            continue
        text = path.read_text()
        for needle in ('"application.revoke"', '"application.suspend"', '"application.restore"'):
            if needle in text:
                offenders.append(f"{path.relative_to(BACKEND)}: {needle}")
    assert not offenders, (
        "ad-hoc audit action strings found (use AuditAction.revoke/suspend/"
        f"restore + ApplicationAuditService instead): {offenders}"
    )
