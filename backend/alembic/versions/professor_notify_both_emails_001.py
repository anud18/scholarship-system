"""Notify the advisor at BOTH the account email and the profile advisor_email

Revision ID: professor_notify_both_emails_001
Revises: advisor_backfill_idx_001
Create Date: 2026-08-24 00:00:00.000000

The 教授審核通知 rule (trigger point 1, professor side) resolved its recipient
with ``COALESCE(users.email, user_profiles.advisor_email)``: the SSO account
email of ``applications.professor_id`` if the professor had an account,
otherwise the address the student typed into their profile. The two are
populated independently and can disagree, and whichever lost the COALESCE was
silently never mailed.

The rule now notifies both (UNION folds them when identical). The seed only
inserts rules whose *name* is missing, so every existing install keeps the old
query until this migration rewrites it.

Content is snapshotted verbatim rather than imported from
app.db.seed_scholarship_configs so that a later edit to the seed cannot
retroactively change what this migration did.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "professor_notify_both_emails_001"
down_revision: Union[str, None] = "advisor_backfill_idx_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TEMPLATE_KEY = "professor_review_notification"
TRIGGER_EVENT = "application_submitted"

# Kept in sync with PROFESSOR_REVIEW_NOTIFICATION_CONDITION_QUERY
# (app/db/seed_scholarship_configs.py).
NEW_CONDITION_QUERY = """
                SELECT email FROM (
                    SELECT u.email
                    FROM applications a
                    JOIN users u ON u.id = a.professor_id
                    WHERE a.id = {application_id}
                    AND u.email IS NOT NULL
                    AND u.email != ''

                    UNION

                    SELECT up.advisor_email
                    FROM applications a
                    JOIN user_profiles up ON up.user_id = a.user_id
                    WHERE a.id = {application_id}
                    AND up.advisor_email IS NOT NULL
                    AND up.advisor_email != ''
                ) emails
                WHERE email IS NOT NULL
            """

NEW_DESCRIPTION = "當申請提交後，通知指導教授有新申請待審核（系統帳號信箱與學生填寫的指導教授信箱皆寄送）"

# What the seed shipped before this revision — restored on downgrade.
OLD_CONDITION_QUERY = """
                SELECT COALESCE(u.email, up.advisor_email) AS email
                FROM applications a
                LEFT JOIN users u ON u.id = a.professor_id
                LEFT JOIN user_profiles up ON up.user_id = a.user_id
                WHERE a.id = {application_id}
                AND COALESCE(u.email, up.advisor_email) IS NOT NULL
                AND COALESCE(u.email, up.advisor_email) != ''
            """

OLD_DESCRIPTION = "當申請提交後，通知指導教授有新申請待審核"


def _set_rule(condition_query: str, description: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "email_automation_rules" not in inspector.get_table_names():
        return

    result = bind.execute(
        sa.text(
            "UPDATE email_automation_rules "
            "SET condition_query = :condition_query, description = :description "
            "WHERE template_key = :template_key "
            "AND CAST(trigger_event AS TEXT) = :trigger_event"
        ),
        {
            "condition_query": condition_query,
            "description": description,
            "template_key": TEMPLATE_KEY,
            "trigger_event": TRIGGER_EVENT,
        },
    )
    print(f"[professor_notify_both_emails_001] rewrote {result.rowcount} '{TEMPLATE_KEY}' rule(s)")


def upgrade() -> None:
    _set_rule(NEW_CONDITION_QUERY, NEW_DESCRIPTION)


def downgrade() -> None:
    _set_rule(OLD_CONDITION_QUERY, OLD_DESCRIPTION)
