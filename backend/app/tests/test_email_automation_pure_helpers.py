"""
Pure-function tests for `EmailAutomationService` template-key mappers.

The automation service receives a `template_key` string (from event
triggers like 'application_submitted_student') and maps it to two
things:
1. An `EmailCategory` enum — used to file the email in the EmailHistory
   table and audit logs.
2. A React Email template name — used by the frontend to render the
   actual HTML body.

If either mapping is wrong, the wrong email goes to the wrong category
in admin views, or worse, the wrong HTML template is rendered. Pinning
both maps so admins can be confident a template_key event sends what
they expect.

2 helpers covered (8 cases):
- `_get_email_category_from_template_key` : 11 known keys + unknown
- `_get_react_email_template_name`        : 8 known keys + unknown
"""

import pytest

from app.models.email_management import EmailCategory
from app.services.email_automation_service import EmailAutomationService


@pytest.fixture
def service():
    return EmailAutomationService()


# ─── _get_email_category_from_template_key ───────────────────────────


def test_category_application_student_keys(service):
    """All keys that map to application_student."""
    assert (
        service._get_email_category_from_template_key("application_submitted_student")
        == EmailCategory.application_student
    )
    assert service._get_email_category_from_template_key("deadline_reminder_draft") == EmailCategory.application_student


def test_category_recommendation_professor_keys(service):
    """Two keys ('notify' + 'review_submitted') route to the same category."""
    assert (
        service._get_email_category_from_template_key("application_notify_professor")
        == EmailCategory.recommendation_professor
    )
    assert (
        service._get_email_category_from_template_key("review_submitted_professor")
        == EmailCategory.recommendation_professor
    )


def test_category_review_and_result_keys(service):
    """Result-* keys route by audience (student / professor / college)."""
    assert service._get_email_category_from_template_key("college_review_notification") == EmailCategory.review_college
    assert service._get_email_category_from_template_key("result_notification_student") == EmailCategory.result_student
    assert (
        service._get_email_category_from_template_key("result_notification_professor") == EmailCategory.result_professor
    )
    assert service._get_email_category_from_template_key("result_notification_college") == EmailCategory.result_college


def test_category_whitelist_supplement_roster(service):
    assert (
        service._get_email_category_from_template_key("whitelist_notification") == EmailCategory.application_whitelist
    )
    assert service._get_email_category_from_template_key("supplement_request") == EmailCategory.supplement_student
    assert service._get_email_category_from_template_key("roster_notification") == EmailCategory.roster_student


def test_category_unknown_key_defaults_to_system(service):
    """Unknown / future template key ⇒ EmailCategory.system (don't crash;
    keep email flow alive but log to the system category for review)."""
    assert service._get_email_category_from_template_key("unknown_template_xyz") == EmailCategory.system
    assert service._get_email_category_from_template_key("") == EmailCategory.system


# ─── _get_react_email_template_name ──────────────────────────────────


def test_react_template_name_known_keys(service):
    """Each automation key maps to a specific React Email template name."""
    expected = {
        "application_submitted_student": "application-submitted",
        "professor_review_notification": "professor-review-request",
        "college_review_notification": "college-review-request",
        "application_deadline_reminder": "deadline-reminder",
        "document_request_notification": "document-request",
        "result_notification_student": "result-notification",
        "roster_notification": "roster-notification",
        "whitelist_notification": "whitelist-notification",
    }
    for key, expected_name in expected.items():
        assert service._get_react_email_template_name(key) == expected_name, f"key={key}"


def test_react_template_name_unknown_returns_none(service):
    """Unknown key ⇒ None (caller can fall back to legacy template loader)."""
    assert service._get_react_email_template_name("unknown") is None


def test_react_template_name_returns_dash_separated_names(service):
    """All template names use dash-separated convention (not snake_case) —
    pin so accidental snake_case slips don't ship."""
    for known_key in (
        "application_submitted_student",
        "professor_review_notification",
        "roster_notification",
    ):
        name = service._get_react_email_template_name(known_key)
        assert name is not None
        assert "_" not in name, f"{known_key} → {name} has underscore"
