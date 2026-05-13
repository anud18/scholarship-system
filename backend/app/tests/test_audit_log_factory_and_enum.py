"""
Tests for `AuditLog.create_log` factory + the `AuditAction` enum
canonical-value contract.

The audit log is the system of record for every privileged action
(reviews, approvals, deletions, PII access, etc.). Compliance audits
and security incident response BOTH depend on:
1. The set of action values being stable (audit queries filter on these)
2. The factory accepting every required field so INSERTs don't fail

Bugs cause:
- New action added without updating the audit query allowlist → events
  invisible to dashboards
- Enum rename → old DB rows with stale value strings become unfilterable
- create_log missing field → ORM INSERT crashes mid-action

13 cases. Pure construction, no DB.
"""

from app.models.audit_log import AuditAction, AuditLog

# ─── AuditLog.create_log factory ─────────────────────────────────────


def test_create_log_minimal_required_fields():
    """Pin: only user_id + action + resource_type are required."""
    log = AuditLog.create_log(
        user_id=42,
        action=AuditAction.create.value,
        resource_type="application",
    )
    assert log.user_id == 42
    assert log.action == "create"
    assert log.resource_type == "application"
    assert log.resource_id is None
    assert log.description is None


def test_create_log_with_resource_id_and_description():
    """Pin: optional resource_id + description set as-passed.
    These are the two most common optional fields."""
    log = AuditLog.create_log(
        user_id=7,
        action=AuditAction.update.value,
        resource_type="application",
        resource_id="APP-113-1-00001",
        description="Updated student bank account",
    )
    assert log.resource_id == "APP-113-1-00001"
    assert log.description == "Updated student bank account"


def test_create_log_passes_kwargs_through():
    """Pin: **kwargs forwarded to the constructor. Used to pass
    optional fields like ip_address, user_agent, old_values, new_values
    without changing the factory signature."""
    log = AuditLog.create_log(
        user_id=1,
        action=AuditAction.delete.value,
        resource_type="application",
        ip_address="10.0.0.1",
        user_agent="Mozilla/5.0",
        old_values={"status": "submitted"},
        new_values={"status": "deleted"},
    )
    assert log.ip_address == "10.0.0.1"
    assert log.user_agent == "Mozilla/5.0"
    assert log.old_values == {"status": "submitted"}
    assert log.new_values == {"status": "deleted"}


# ─── AuditAction enum value-string contract ──────────────────────────


def test_audit_action_core_lifecycle_values():
    """Pin: the 5 CRUD-style action strings. Audit-log queries in the
    admin dashboard filter on these exact strings."""
    assert AuditAction.create.value == "create"
    assert AuditAction.update.value == "update"
    assert AuditAction.delete.value == "delete"
    assert AuditAction.view.value == "view"
    assert AuditAction.submit.value == "submit"


def test_audit_action_review_decision_values():
    """Pin: review/decision action strings used by the application
    review flow."""
    assert AuditAction.approve.value == "approve"
    assert AuditAction.reject.value == "reject"
    assert AuditAction.professor_review.value == "professor_review"
    assert AuditAction.admin_review.value == "admin_review"
    assert AuditAction.college_review.value == "college_review"
    assert AuditAction.college_review_update.value == "college_review_update"


def test_audit_action_auth_values():
    """Pin: login/logout. These power the 'user activity' admin view."""
    assert AuditAction.login.value == "login"
    assert AuditAction.logout.value == "logout"


def test_audit_action_import_avoids_python_keyword():
    """Pin: the import action uses .import_ (trailing underscore) as
    the Python identifier to avoid the keyword conflict, but its VALUE
    is still 'import' (no underscore). A regression that exposes
    'import_' as the DB value would break audit queries."""
    assert AuditAction.import_.value == "import"
    assert AuditAction.export.value == "export"


def test_audit_action_college_workflow_values():
    """Pin: college-side ranking workflow strings. These are written
    on every finalize/unfinalize click and the admin dashboard groups
    by them."""
    assert AuditAction.finalize_ranking.value == "finalize_ranking"
    assert AuditAction.unfinalize_ranking.value == "unfinalize_ranking"
    assert AuditAction.execute_distribution.value == "execute_distribution"
    assert AuditAction.delete_ranking.value == "delete_ranking"


def test_audit_action_bank_verification_values():
    """Pin: bank verification action strings. Compliance audit filters
    on these to show 'who verified what account when'."""
    assert AuditAction.verify_bank_account.value == "verify_bank_account"
    assert AuditAction.batch_verify_bank_accounts.value == "batch_verify_bank_accounts"


def test_audit_action_pii_access_value():
    """SECURITY-CRITICAL: PII-access action logged when a user views
    full plaintext std_pid (e.g., Excel ranking export). Issue #73
    compliance — pin the exact string so the privacy audit dashboard
    finds these rows."""
    assert AuditAction.pii_access.value == "pii_access"


def test_audit_action_request_documents_and_withdraw():
    """Pin: request_documents (reviewer asks student for more docs)
    + withdraw (student withdraws submitted application) actions."""
    assert AuditAction.request_documents.value == "request_documents"
    assert AuditAction.withdraw.value == "withdraw"


# ─── Enum membership contract ────────────────────────────────────────


def test_all_action_values_are_unique_strings():
    """Pin: no two enum members share a value. A duplicate value would
    cause two members to be aliases in Python and audit queries to
    return BOTH for either filter — confusing the compliance report."""
    values = [a.value for a in AuditAction]
    assert len(values) == len(set(values)), f"duplicate audit action values: {values}"


def test_known_action_count_for_change_review():
    """Pin: 23 actions defined. A refactor adding an action without
    updating the audit dashboard's allowlist would silently hide the
    new events. This test forces a code review when count changes."""
    assert len(list(AuditAction)) == 23
