"""
Tests for email-related enums in `app.models.email_management` and
`app.models.system_setting`.

These enums drive:
- Email delivery state machine (sent / failed / bounced / pending)
- Scheduled-email lifecycle (pending → sent / cancelled / failed)
- Email category routing (11 distinct templates for different recipients)
- Trigger event detection (6 lifecycle events)
- Sending type (single vs bulk — affects approval gate)

Bugs cause:
- Wrong status string → email worker can't resume failed sends after restart
- Category collision → wrong template applied for a notification type
- Trigger event rename → email-automation rules silently stop firing

5 enums (10 cases). Pure, no DB.
"""

from app.models.email_management import (
    EmailCategory,
    EmailStatus,
    ScheduleStatus,
    TriggerEvent,
)
from app.models.system_setting import SendingType

# ─── EmailStatus (delivery state machine) ────────────────────────────


def test_email_status_values():
    """Pin: 4 delivery states. sent + failed + bounced are terminal;
    pending is in-flight. Email worker resumes pending entries after
    restart based on this string."""
    assert EmailStatus.sent.value == "sent"
    assert EmailStatus.failed.value == "failed"
    assert EmailStatus.bounced.value == "bounced"
    assert EmailStatus.pending.value == "pending"
    assert len(list(EmailStatus)) == 4


def test_email_status_bounced_distinct_from_failed():
    """Pin: 'bounced' is distinct from 'failed' — bounced means the
    recipient mailbox rejected, failed means SMTP errored out before
    delivery. Compliance audit + retry-strategy differ for each."""
    assert EmailStatus.bounced.value != EmailStatus.failed.value


# ─── ScheduleStatus (scheduled-email lifecycle) ──────────────────────


def test_schedule_status_values():
    """Pin: 4 lifecycle states. Cron worker filters by 'pending' to
    pick up the queue. A rename would silently empty the queue."""
    assert ScheduleStatus.pending.value == "pending"
    assert ScheduleStatus.sent.value == "sent"
    assert ScheduleStatus.cancelled.value == "cancelled"
    assert ScheduleStatus.failed.value == "failed"
    assert len(list(ScheduleStatus)) == 4


# ─── EmailCategory (template routing) ────────────────────────────────


def test_email_category_values():
    """Pin: 11 categories covering every notification type in the
    system. The frontend admin panel groups templates by these
    categories; a rename would orphan templates from their category."""
    assert EmailCategory.application_whitelist.value == "application_whitelist"
    assert EmailCategory.application_student.value == "application_student"
    assert EmailCategory.recommendation_professor.value == "recommendation_professor"
    assert EmailCategory.review_college.value == "review_college"
    assert EmailCategory.supplement_student.value == "supplement_student"
    assert EmailCategory.result_professor.value == "result_professor"
    assert EmailCategory.result_college.value == "result_college"
    assert EmailCategory.result_student.value == "result_student"
    assert EmailCategory.roster_student.value == "roster_student"
    assert EmailCategory.system.value == "system"
    assert EmailCategory.other.value == "other"


def test_email_category_count_pinned():
    """Pin: 11 categories. Adding a new category without updating the
    admin panel grouping would orphan templates."""
    assert len(list(EmailCategory)) == 11


# ─── TriggerEvent (email automation) ─────────────────────────────────


def test_trigger_event_values():
    """Pin: 6 lifecycle events the email-automation rule engine listens
    for. CRITICAL: a rename here without updating the matching emitter
    would silently disable the automation rule for that event."""
    assert TriggerEvent.application_submitted.value == "application_submitted"
    assert TriggerEvent.professor_review_submitted.value == "professor_review_submitted"
    assert TriggerEvent.college_review_submitted.value == "college_review_submitted"
    assert TriggerEvent.final_result_decided.value == "final_result_decided"
    assert TriggerEvent.supplement_requested.value == "supplement_requested"
    assert TriggerEvent.deadline_approaching.value == "deadline_approaching"
    assert len(list(TriggerEvent)) == 6


def test_trigger_event_review_stages_distinct():
    """Pin: professor_review_submitted, college_review_submitted, and
    final_result_decided are 3 distinct events at 3 distinct points in
    the review pipeline. A regression collapsing any two would fire
    duplicate emails OR miss one notification entirely."""
    review_values = {
        TriggerEvent.professor_review_submitted.value,
        TriggerEvent.college_review_submitted.value,
        TriggerEvent.final_result_decided.value,
    }
    assert len(review_values) == 3


# ─── SendingType (bulk approval gate) ────────────────────────────────


def test_sending_type_values():
    """Pin: 2 sending types. SECURITY-ADJACENT: 'bulk' triggers the
    admin-approval gate (covered separately in wave 6a18 for
    ScheduledEmail). A regression renaming 'bulk' would silently
    bypass approval for batch sends."""
    assert SendingType.single.value == "single"
    assert SendingType.bulk.value == "bulk"
    assert len(list(SendingType)) == 2


# ─── Cross-enum lowercase invariant ──────────────────────────────────


def test_all_email_enum_values_lowercase():
    """Pin: per CLAUDE.md §4, all enum values are lowercase. A
    regression introducing UPPERCASE would cause SQLAlchemy LookupError
    on column bind/load."""
    for enum_cls in (EmailStatus, ScheduleStatus, EmailCategory, TriggerEvent, SendingType):
        for member in enum_cls:
            assert (
                member.value == member.value.lower()
            ), f"{enum_cls.__name__}.{member.name} value '{member.value}' is not lowercase"
