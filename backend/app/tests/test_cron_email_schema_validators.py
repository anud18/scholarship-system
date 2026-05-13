"""
Pydantic validator tests for `roster_schedule.py` and `user_profile.py`.

`RosterScheduleBase.validate_cron_expression` gates the cron strings
admin paste into the roster scheduler. A bad cron expression slipping
through causes the scheduler thread to crash at next-run-time
computation, which silently disables all roster generation until an
ops engineer notices.

`RosterScheduleBase.validate_notification_emails` and
`AdvisorInfoBase.validate_email` are email-format gates. Bad emails
saved silently → notification thread silently swallows SMTP errors
without alerting on payment day.

The advisor_email validator also implements the `'' → None` sentinel
coercion — pin this because the API contract treats empty string as
'unset', and a refactor that breaks the coercion would save literal
empty strings as advisor_email in the DB.

5 validators (16 cases). Pure Pydantic, no DB.
"""

import pytest
from pydantic import ValidationError

from app.models.payment_roster import RosterCycle
from app.schemas.roster_schedule import (
    RosterScheduleBase,
    RosterScheduleUpdate,
)
from app.schemas.user_profile import (
    AdvisorInfoBase,
    AdvisorInfoUpdate,
    UserProfileCreate,
    UserProfileUpdate,
)

# ─── RosterScheduleBase.validate_cron_expression ─────────────────────


def _schedule_payload(**overrides) -> dict:
    payload = {
        "scholarship_configuration_id": 1,
        "roster_cycle": RosterCycle.MONTHLY,
    }
    payload.update(overrides)
    return payload


def test_cron_expression_valid_5field_accepted():
    """Standard 5-field cron: 'every day at 02:00'."""
    s = RosterScheduleBase(**_schedule_payload(cron_expression="0 2 * * *"))
    assert s.cron_expression == "0 2 * * *"


def test_cron_expression_invalid_rejected():
    """Pin: garbage cron string raises. SECURITY-CRITICAL: without this,
    the scheduler thread crashes on next_run_time() at runtime —
    silently disabling all roster generation."""
    with pytest.raises(ValidationError) as exc:
        RosterScheduleBase(**_schedule_payload(cron_expression="not a cron"))
    assert "Invalid cron" in str(exc.value)


def test_cron_expression_too_few_fields_rejected():
    """Pin: croniter requires ≥ 5 fields. '* * *' rejected."""
    with pytest.raises(ValidationError):
        RosterScheduleBase(**_schedule_payload(cron_expression="* * *"))


def test_cron_expression_none_passes_through():
    """None means 'no schedule' — pin so the manual-trigger-only path
    remains accessible without setting a cron."""
    s = RosterScheduleBase(**_schedule_payload(cron_expression=None))
    assert s.cron_expression is None


def test_cron_update_path_validator_also_enforced():
    """RosterScheduleUpdate has a parallel validator (separate code
    path). Pin so a consolidation refactor doesn't drop one side."""
    with pytest.raises(ValidationError):
        RosterScheduleUpdate(cron_expression="bad")


# ─── RosterScheduleBase.validate_notification_emails ─────────────────


def test_notification_emails_valid_list_accepted():
    s = RosterScheduleBase(
        **_schedule_payload(
            notification_emails=["ops@nycu.edu.tw", "admin+alerts@nycu.edu.tw"],
        )
    )
    assert s.notification_emails == ["ops@nycu.edu.tw", "admin+alerts@nycu.edu.tw"]


def test_notification_emails_one_bad_apple_rejects_list():
    """Pin: ALL emails must be valid. A single bad entry aborts the
    whole list — defensive against admin pasting a CSV with one typo."""
    with pytest.raises(ValidationError) as exc:
        RosterScheduleBase(
            **_schedule_payload(
                notification_emails=["valid@example.com", "not-an-email"],
            )
        )
    assert "Invalid email format" in str(exc.value)
    assert "not-an-email" in str(exc.value)


def test_notification_emails_none_passes_through():
    """None means 'notifications disabled / use defaults' — pin."""
    s = RosterScheduleBase(**_schedule_payload(notification_emails=None))
    assert s.notification_emails is None


# ─── AdvisorInfoBase.validate_email (with empty-string sentinel) ─────


def test_advisor_email_empty_string_coerced_to_none():
    """Pin: '' → None. The frontend may submit empty string when user
    clears the field; the API contract treats this as 'unset', not
    'set to empty'. A refactor breaking this would save '' literals
    in DB and break has_advisor_info detection."""
    info = AdvisorInfoBase(advisor_email="")
    assert info.advisor_email is None


def test_advisor_email_none_passes_through():
    info = AdvisorInfoBase(advisor_email=None)
    assert info.advisor_email is None


def test_advisor_email_valid_accepted():
    info = AdvisorInfoBase(advisor_email="prof@nycu.edu.tw")
    assert info.advisor_email == "prof@nycu.edu.tw"


def test_advisor_email_malformed_rejected():
    """Pin: missing @, missing TLD, etc. rejected."""
    for bad in ["not-an-email", "missing@tld", "@missing.local", "spaces in@email.com"]:
        with pytest.raises(ValidationError):
            AdvisorInfoBase(advisor_email=bad)


# ─── UserProfileCreate / Update parallel email validators ────────────


def test_user_profile_create_advisor_email_sentinel_coercion():
    """Parallel validator on UserProfileCreate — pin both code paths."""
    p = UserProfileCreate(advisor_email="")
    assert p.advisor_email is None


def test_user_profile_update_advisor_email_sentinel_coercion():
    p = UserProfileUpdate(advisor_email="")
    assert p.advisor_email is None


def test_user_profile_update_advisor_email_invalid_rejected():
    """Pin: validation also fires on Update (when value is set)."""
    with pytest.raises(ValidationError):
        UserProfileUpdate(advisor_email="bad-format")


# ─── AdvisorInfoUpdate inherits the validator ────────────────────────


def test_advisor_info_update_inherits_validator():
    """AdvisorInfoUpdate extends AdvisorInfoBase — verify the inherited
    validator still fires."""
    upd = AdvisorInfoUpdate(advisor_email="", change_reason="cleared")
    assert upd.advisor_email is None

    with pytest.raises(ValidationError):
        AdvisorInfoUpdate(advisor_email="garbage", change_reason="?")
