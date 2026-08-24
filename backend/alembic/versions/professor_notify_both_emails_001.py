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

Only rows still carrying a query this project shipped are rewritten — the
seed's COALESCE text or the older 24f4d6ba449b advisor_email-only text,
compared whitespace-insensitively. `condition_query` is admin-editable
(PUT /email-automation/rules/{id}) and (template_key, trigger_event) is not
unique, so an unconditional UPDATE would flatten a customised recipient
query (or a second, admin-created rule on the same template) with no
pre-image to recover from. Customised rows are left untouched and logged.

Content is snapshotted verbatim rather than imported from
app.db.seed_scholarship_configs so that a later edit to the seed cannot
retroactively change what this migration did.
"""

import re
from typing import Iterable, Sequence, Union

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
                    LEFT JOIN users u ON u.id = a.professor_id
                    WHERE a.id = {application_id}
                    AND up.advisor_email IS NOT NULL
                    AND up.advisor_email != ''
                    AND (
                        u.id IS NULL
                        OR up.advisor_nycu_id IS NULL
                        OR up.advisor_nycu_id = ''
                        OR up.advisor_nycu_id = u.nycu_id
                    )
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

# What 24f4d6ba449b wrote before the seed's COALESCE version existed — an
# install that never re-seeded still carries this text.
LEGACY_CONDITION_QUERY = """
            SELECT user_profiles.advisor_email as email
            FROM applications
            JOIN user_profiles ON applications.user_id = user_profiles.user_id
            WHERE applications.id = {application_id}
            AND user_profiles.advisor_email IS NOT NULL
            AND user_profiles.advisor_email != ''
"""


def _normalize(sql) -> str:
    return re.sub(r"\s+", " ", sql or "").strip()


def _rewrite_shipped_rules(expected: Iterable[str], condition_query: str, description: str) -> None:
    """Rewrite the professor rule(s) whose query is one of *expected*; skip the rest."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "email_automation_rules" not in inspector.get_table_names():
        return

    rows = bind.execute(
        sa.text(
            "SELECT id, condition_query FROM email_automation_rules "
            "WHERE template_key = :template_key "
            "AND CAST(trigger_event AS TEXT) = :trigger_event"
        ),
        {"template_key": TEMPLATE_KEY, "trigger_event": TRIGGER_EVENT},
    ).fetchall()

    expected_normalized = {_normalize(q) for q in expected}
    rewritten = 0
    for row in rows:
        if _normalize(row.condition_query) not in expected_normalized:
            print(
                f"[professor_notify_both_emails_001] rule id={row.id} carries a customised "
                f"condition_query; left untouched"
            )
            continue
        bind.execute(
            sa.text(
                "UPDATE email_automation_rules "
                "SET condition_query = :condition_query, description = :description "
                "WHERE id = :id"
            ),
            {"condition_query": condition_query, "description": description, "id": row.id},
        )
        rewritten += 1
    print(f"[professor_notify_both_emails_001] rewrote {rewritten} of {len(rows)} '{TEMPLATE_KEY}' rule(s)")


def upgrade() -> None:
    _rewrite_shipped_rules((OLD_CONDITION_QUERY, LEGACY_CONDITION_QUERY), NEW_CONDITION_QUERY, NEW_DESCRIPTION)


def downgrade() -> None:
    # Only rows this revision wrote are reverted; a customised row stays as is.
    _rewrite_shipped_rules((NEW_CONDITION_QUERY,), OLD_CONDITION_QUERY, OLD_DESCRIPTION)
