"""
Source-level regression for SECURITY audit-log invariants across all
endpoints that were instrumented in previous PRs.

Mirrors the pattern from test_auth_rate_limit_invariants.py and
test_announcement_audit_log_invariants.py: AST-walk each handler
module's source, find the named function, and assert that its body
contains a `logger.info(...)` call somewhere whose `extra` keyword
argument includes an `actor_user_id` key. If a future refactor
removes any of these `logger.info` calls (or drops the
`actor_user_id` key from the `extra` payload), the suite catches it
before the change ships.

Each (module, handler, source_pr) entry below pins a SECURITY
audit-log invariant that landed in the named PR. Don't add an entry
here speculatively — add only after the handler is verified to emit
`logger.info(..., extra={"actor_user_id": ...})` on its success
path.
"""

import ast
import importlib
import inspect

import pytest


def _function_has_logger_info_with_actor(module, func_name: str) -> bool:
    """True iff `func_name` in `module` contains a `logger.info(...)` call
    whose `extra=` kwarg dict literal includes `'actor_user_id'`."""
    src = inspect.getsource(module)
    tree = ast.parse(src)

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != func_name:
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call):
                continue
            if not (
                isinstance(sub.func, ast.Attribute)
                and sub.func.attr == "info"
                and isinstance(sub.func.value, ast.Name)
                and sub.func.value.id == "logger"
            ):
                continue
            for kw in sub.keywords:
                if kw.arg != "extra":
                    continue
                if isinstance(kw.value, ast.Dict):
                    for k in kw.value.keys:
                        if isinstance(k, ast.Constant) and k.value == "actor_user_id":
                            return True
        return False
    return False


# (module_path, handler_name, source_pr_number)
AUDIT_LOG_INVARIANTS = [
    # --- PR #645: scholarship permission deletions (+ creations) ---
    ("app.api.v1.endpoints.admin.permissions", "create_scholarship_permission", 645),
    ("app.api.v1.endpoints.admin.permissions", "delete_scholarship_permission", 645),
    # --- PR #646: scholarship-rule deletions (admin module) ---
    ("app.api.v1.endpoints.admin.rules", "delete_scholarship_rule", 646),
    # --- PR #657: college_review export-package bulk PII export ---
    (
        "app.api.v1.endpoints.college_review.export_package",
        "export_application_package",
        657,
    ),
    # --- PR #658: admin/system-setting mutations ---
    ("app.api.v1.endpoints.admin.system_settings", "set_system_setting", 658),
    # --- PR #660: admin/email-template PUT mutations ---
    ("app.api.v1.endpoints.admin.email_templates", "update_email_template", 660),
    # --- PR #661: system_settings CRUD mutations ---
    ("app.api.v1.endpoints.system_settings", "create_configuration", 661),
    ("app.api.v1.endpoints.system_settings", "update_configuration", 661),
    ("app.api.v1.endpoints.system_settings", "delete_configuration", 661),
    # --- PR #662: college_review/application_summary_export ---
    (
        "app.api.v1.endpoints.college_review.application_summary_export",
        "export_department_summary_single",
        662,
    ),
    (
        "app.api.v1.endpoints.college_review.application_summary_export",
        "export_department_summary_bulk",
        662,
    ),
    # --- PR #663: admin/students directed PII access ---
    ("app.api.v1.endpoints.admin.students", "get_student_detail", 663),
    # --- PR #501: scholarship-rule write endpoints (top-level module) ---
    ("app.api.v1.endpoints.scholarship_rules", "bulk_rule_operation", 501),
    ("app.api.v1.endpoints.scholarship_rules", "copy_rules", 501),
    # --- PR #502: users.py destructive endpoints ---
    ("app.api.v1.endpoints.users", "update_user_college", 502),
    ("app.api.v1.endpoints.users", "bulk_assign_scholarships", 502),
    # --- PR #506: scholarship_management bulk admin endpoints ---
    ("app.api.v1.endpoints.scholarship_management", "simulate_priority_processing", 506),
    # --- PR #576: email_automation audit logging ---
    ("app.api.v1.endpoints.email_automation", "toggle_automation_rule", 576),
]


@pytest.mark.parametrize(
    "module_path,handler_name,source_pr",
    AUDIT_LOG_INVARIANTS,
)
def test_endpoint_handler_emits_actor_user_id_audit_log(module_path: str, handler_name: str, source_pr: int) -> None:
    """Each SECURITY-instrumented handler must emit a `logger.info(...)`
    call carrying `extra={'actor_user_id': ...}` somewhere in its body.
    The corresponding source PR added this invariant; this regression
    test pins it."""
    module = importlib.import_module(module_path)
    assert _function_has_logger_info_with_actor(module, handler_name), (
        f"{module_path}.{handler_name} must emit "
        f"logger.info(..., extra={{'actor_user_id': ...}}) on success "
        f"(PR #{source_pr})."
    )
