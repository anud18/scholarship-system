"""
Tests for `EmailTestModeAudit` classmethod factories in
`app.models.email_management`.

These factories construct audit log rows for the email test-mode
gating system — a SECURITY-RELEVANT feature that intercepts outgoing
emails in dev/staging so transactional emails don't reach real users
during testing. Every state transition (enable, disable, intercept,
expire) is logged via one of these factory classmethods.

Bugs cause:
- Wrong `event_type` string → audit-log queries filtering by event
  miss rows (compliance issue: "show me when test mode was last
  enabled" returns nothing)
- Missing `original_recipient` on intercept events → can't verify
  WHICH user's email got redirected (privacy audit failure)
- Constructor args not set → ORM INSERT crashes because NOT NULL
  columns are unset

4 classmethod factories (8 cases). Pure construction, no DB.
"""

from app.models.email_management import EmailTestModeAudit

# ─── log_enabled ─────────────────────────────────────────────────────


def test_log_enabled_sets_event_type_and_config_after():
    """Pin: event_type='enabled', config_after stored, config_before NOT set.
    Used when admin enables email-test-mode."""
    audit = EmailTestModeAudit.log_enabled(
        user_id=42,
        config_after={"redirect_to": "test@example.com", "ttl_minutes": 60},
        ip_address="10.0.0.1",
        user_agent="Mozilla/5.0",
    )
    assert audit.event_type == "enabled"
    assert audit.user_id == 42
    assert audit.config_after == {"redirect_to": "test@example.com", "ttl_minutes": 60}
    assert audit.ip_address == "10.0.0.1"
    assert audit.user_agent == "Mozilla/5.0"


def test_log_enabled_without_optional_args():
    """Pin: ip_address and user_agent default to None — admin actions
    from cron / script lack a request context."""
    audit = EmailTestModeAudit.log_enabled(user_id=1, config_after={"x": "y"})
    assert audit.event_type == "enabled"
    assert audit.ip_address is None
    assert audit.user_agent is None


# ─── log_disabled ────────────────────────────────────────────────────


def test_log_disabled_captures_config_before_not_after():
    """Pin: event_type='disabled', config_BEFORE stored (the state we
    just left). config_after is NOT set on disable events — that's the
    semantic difference from log_enabled. A regression that swaps the
    fields would make the audit trail unverifiable."""
    audit = EmailTestModeAudit.log_disabled(
        user_id=99,
        config_before={"redirect_to": "test@example.com"},
        ip_address="10.0.0.2",
    )
    assert audit.event_type == "disabled"
    assert audit.user_id == 99
    assert audit.config_before == {"redirect_to": "test@example.com"}


# ─── log_email_intercepted (most security-critical) ──────────────────


def test_log_email_intercepted_records_recipients_and_session():
    """SECURITY-CRITICAL: every intercepted email is logged with BOTH
    the original (intended) recipient AND the actual (test) recipient.
    A compliance audit must be able to answer: 'which real user's email
    was redirected when?' Pin all 4 required fields."""
    audit = EmailTestModeAudit.log_email_intercepted(
        original_recipient="real-student@nycu.edu.tw",
        actual_recipient="test-inbox@example.com",
        email_subject="申請審核結果通知",
        session_id="sess-abc-123",
        user_id=7,
    )
    assert audit.event_type == "email_intercepted"
    assert audit.original_recipient == "real-student@nycu.edu.tw"
    assert audit.actual_recipient == "test-inbox@example.com"
    assert audit.email_subject == "申請審核結果通知"
    assert audit.session_id == "sess-abc-123"
    assert audit.user_id == 7


def test_log_email_intercepted_user_id_optional():
    """Pin: user_id is optional. System-generated emails (e.g., cron
    deadline reminders) have no specific user context but still need
    the audit log entry."""
    audit = EmailTestModeAudit.log_email_intercepted(
        original_recipient="x@y.com",
        actual_recipient="z@y.com",
        email_subject="X",
        session_id="s1",
    )
    assert audit.event_type == "email_intercepted"
    assert audit.user_id is None


# ─── log_expired ─────────────────────────────────────────────────────


def test_log_expired_only_records_event_type_and_config_before():
    """Pin: log_expired is system-generated when the test-mode TTL
    elapses. NO user_id (no person triggered this), NO ip_address,
    just event_type='expired' + the config that just expired.

    A regression that demands user_id here would crash the auto-expire
    job."""
    audit = EmailTestModeAudit.log_expired(config_before={"redirect_to": "test@example.com"})
    assert audit.event_type == "expired"
    assert audit.config_before == {"redirect_to": "test@example.com"}
    assert audit.user_id is None


# ─── Event type allowlist (cross-factory contract) ───────────────────


def test_event_type_strings_are_distinct_and_canonical():
    """Pin: the 4 event types are distinct strings. Audit-log queries
    filter on these values; a typo would silently exclude rows.

    A future refactor that consolidates these to an enum should keep
    the same string values."""
    enabled = EmailTestModeAudit.log_enabled(user_id=1, config_after={})
    disabled = EmailTestModeAudit.log_disabled(user_id=1, config_before={})
    intercepted = EmailTestModeAudit.log_email_intercepted(
        original_recipient="a", actual_recipient="b", email_subject="c", session_id="d"
    )
    expired = EmailTestModeAudit.log_expired(config_before={})

    types = {enabled.event_type, disabled.event_type, intercepted.event_type, expired.event_type}
    assert types == {"enabled", "disabled", "email_intercepted", "expired"}
    assert len(types) == 4  # all distinct


def test_no_factory_leaks_fields_across_event_types():
    """Pin: log_enabled doesn't set config_before; log_disabled doesn't
    set config_after; log_email_intercepted doesn't set config_before
    or config_after. Each event type stores ONLY its relevant fields.

    A regression that sets both would cause audit log queries to
    return ambiguous results."""
    enabled = EmailTestModeAudit.log_enabled(user_id=1, config_after={"k": "v"})
    assert getattr(enabled, "config_before", None) is None

    disabled = EmailTestModeAudit.log_disabled(user_id=1, config_before={"k": "v"})
    assert getattr(disabled, "config_after", None) is None

    intercepted = EmailTestModeAudit.log_email_intercepted(
        original_recipient="a", actual_recipient="b", email_subject="c", session_id="d"
    )
    assert getattr(intercepted, "config_before", None) is None
    assert getattr(intercepted, "config_after", None) is None
