"""The email seeders must merge per row, never skip on a non-empty table.

``scripts/reset_database.sh`` runs ``alembic upgrade head`` BEFORE ``python -m
app.seed``, and ``email_timing_three_triggers_001`` inserts the 學院排名送出通知
rule and its template. With the old table-level guard
(``if existing: return``) that single pre-existing row made both seeders bail
out, so a fresh database ended up with the college rule and nothing else —
trigger point 1 (學生送出申請 → 學生 + 教授) had no active rule and silently
sent no mail at all.
"""

import pytest
from sqlalchemy import select

from app.db.seed_scholarship_configs import (
    COLLEGE_RANKING_SUBMITTED_BODY,
    COLLEGE_RANKING_SUBMITTED_CONDITION_QUERY,
    COLLEGE_RANKING_SUBMITTED_SUBJECT,
    COLLEGE_RANKING_SUBMITTED_TEMPLATE_KEY,
    seed_email_automation_rules,
    seed_email_templates,
)
from app.models.email_management import EmailAutomationRule, TriggerEvent
from app.models.system_setting import EmailTemplate, SendingType

# The rules the two submission emails depend on — the ones the old guard dropped.
SUBMISSION_RULE_NAMES = {"申請提交確認郵件", "教授審核通知"}
SUBMISSION_TEMPLATE_KEYS = {"application_submitted_student", "professor_review_notification"}


async def _template_keys(db) -> set[str]:
    result = await db.execute(select(EmailTemplate.key))
    return set(result.scalars().all())


async def _rule_names(db) -> set[str]:
    result = await db.execute(select(EmailAutomationRule.name))
    return set(result.scalars().all())


async def _insert_migration_rows(db) -> None:
    """Recreate exactly what the alembic migration leaves behind."""
    db.add(
        EmailTemplate(
            key=COLLEGE_RANKING_SUBMITTED_TEMPLATE_KEY,
            subject_template=COLLEGE_RANKING_SUBMITTED_SUBJECT,
            body_template=COLLEGE_RANKING_SUBMITTED_BODY,
            sending_type=SendingType.single,
            requires_approval=False,
            recipient_options=[{"label": "學院承辦人", "value": "college"}],
        )
    )
    db.add(
        EmailAutomationRule(
            name="學院排名送出通知",
            description="當學院送出（確認）排名後，通知該學院承辦人排名已送出",
            trigger_event=TriggerEvent.college_review_submitted,
            template_key=COLLEGE_RANKING_SUBMITTED_TEMPLATE_KEY,
            condition_query=COLLEGE_RANKING_SUBMITTED_CONDITION_QUERY,
            delay_hours=0,
            is_active=True,
        )
    )
    await db.commit()


@pytest.mark.asyncio
async def test_seed_still_creates_submission_rows_after_migration_inserted_one(db):
    """Migration-then-seed must end with all three trigger points wired."""
    await _insert_migration_rows(db)

    await seed_email_templates(db)
    await seed_email_automation_rules(db)

    keys = await _template_keys(db)
    names = await _rule_names(db)

    # The pre-existing row survives...
    assert COLLEGE_RANKING_SUBMITTED_TEMPLATE_KEY in keys
    assert "學院排名送出通知" in names
    # ...and the rows the old table-level guard would have skipped are created.
    assert SUBMISSION_TEMPLATE_KEYS <= keys
    assert SUBMISSION_RULE_NAMES <= names


@pytest.mark.asyncio
async def test_all_seeded_rules_reference_a_seeded_template(db):
    """A rule whose template_key has no row is silently dropped at send time."""
    await _insert_migration_rows(db)
    await seed_email_templates(db)
    await seed_email_automation_rules(db)

    keys = await _template_keys(db)
    result = await db.execute(select(EmailAutomationRule.name, EmailAutomationRule.template_key))
    for name, template_key in result.all():
        assert template_key in keys, f"rule {name} points at missing template {template_key}"


@pytest.mark.asyncio
async def test_seeders_are_idempotent(db):
    """Re-running the seed must not duplicate rows."""
    await seed_email_templates(db)
    await seed_email_automation_rules(db)
    first_keys = await _template_keys(db)
    first_names = await _rule_names(db)

    await seed_email_templates(db)
    await seed_email_automation_rules(db)

    result = await db.execute(select(EmailTemplate.key))
    all_keys = list(result.scalars().all())
    result = await db.execute(select(EmailAutomationRule.name))
    all_names = list(result.scalars().all())

    assert len(all_keys) == len(first_keys), "seeding twice duplicated email templates"
    assert len(all_names) == len(first_names), "seeding twice duplicated automation rules"


@pytest.mark.asyncio
async def test_seed_on_empty_database_wires_all_three_trigger_points(db):
    """No migration rows present — the seed alone must still be complete."""
    await seed_email_templates(db)
    await seed_email_automation_rules(db)

    names = await _rule_names(db)
    assert SUBMISSION_RULE_NAMES <= names
    assert "學院排名送出通知" in names

    result = await db.execute(select(EmailAutomationRule.trigger_event).where(EmailAutomationRule.is_active))
    events = {e.value if hasattr(e, "value") else e for e in result.scalars().all()}
    assert events == {"application_submitted", "college_review_submitted"}
