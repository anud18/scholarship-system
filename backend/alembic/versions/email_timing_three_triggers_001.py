"""Reduce automated email to the three agreed trigger points

Revision ID: email_timing_three_triggers_001
Revises: student_history_visibility_001
Create Date: 2026-08-03 00:00:00.000000

The system now mails exactly three events:

1. 學生送出申請       -> 學生 + 指導教授   (existing rules, untouched)
2. 草稿 + 申請截止前三天 -> 學生            (deadline_checker, code-side)
3. 學院送出（確認）排名 -> 該學院承辦人      (this migration wires it up)

For (3) the dormant '學院審核通知' rule — bound to professor_review_submitted,
which nothing ever emitted — is repointed at college_review_submitted, given a
recipient query scoped by college_code, given its own template, and enabled.

Existing installs seeded their automation rules once (the seed skips a
non-empty table), so the change has to be applied here rather than in the seed
alone. Content is snapshotted verbatim rather than imported from
app.db.seed_scholarship_configs so that a later edit to the seed cannot
retroactively change what this migration did.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "email_timing_three_triggers_001"
down_revision: Union[str, None] = "student_history_visibility_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD_RULE_NAME = "學院審核通知"
NEW_RULE_NAME = "學院排名送出通知"
TEMPLATE_KEY = "college_ranking_submitted"

CONDITION_QUERY = """
                SELECT u.email
                FROM users u
                WHERE u.role = 'college'
                AND u.college_code = {college_code}
                AND u.email IS NOT NULL
                AND u.email != ''
            """

SUBJECT_TEMPLATE = "排名已送出 - {scholarship_name} {ranking_name}"

RECIPIENT_OPTIONS_JSON = '[{"label": "學院承辦人", "value": "college"}]'

BODY_TEMPLATE = """{college_name} 您好：

貴學院的 {scholarship_name} 推薦排名已完成送出並鎖定，後續將由承辦單位進行配額分發。

排名資訊：
- 排名名稱：{ranking_name}
- 申請類別：{sub_type_code}
- 學年度學期：{academic_year} 學年度 {semester}
- 排名人數：{total_applications}
- 送出時間：{finalized_at}（操作人：{finalized_by}）

排名送出後即無法修改。若需調整，請聯繫承辦單位解除鎖定。

請至系統查看：{system_url}/college/rankings

國立陽明交通大學
獎學金管理系統"""


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "email_templates" in tables:
        existing = bind.execute(
            sa.text("SELECT id FROM email_templates WHERE key = :key"), {"key": TEMPLATE_KEY}
        ).first()
        if existing is None:
            # requires_approval / sending_type carry Python-side defaults only, so a
            # raw INSERT has to supply them explicitly. recipient_options drives the
            # 收件者選項 list in the admin manual-send UI — omitting it leaves an
            # upgraded install with an empty picker where a seeded one has 學院承辦人.
            bind.execute(
                sa.text(
                    "INSERT INTO email_templates "
                    "(key, subject_template, body_template, sending_type, requires_approval, recipient_options) "
                    "VALUES (:key, :subject, :body, 'single', false, CAST(:recipient_options AS JSON))"
                ),
                {
                    "key": TEMPLATE_KEY,
                    "subject": SUBJECT_TEMPLATE,
                    "body": BODY_TEMPLATE,
                    "recipient_options": RECIPIENT_OPTIONS_JSON,
                },
            )

    if "email_automation_rules" in tables:
        params = {
            "new_name": NEW_RULE_NAME,
            "description": "當學院送出（確認）排名後，通知該學院承辦人排名已送出",
            "template_key": TEMPLATE_KEY,
            "condition_query": CONDITION_QUERY,
            "old_name": OLD_RULE_NAME,
        }
        result = bind.execute(
            sa.text(
                "UPDATE email_automation_rules "
                "SET name = :new_name, "
                "    description = :description, "
                "    trigger_event = 'college_review_submitted', "
                "    template_key = :template_key, "
                "    condition_query = :condition_query, "
                "    delay_hours = 0, "
                "    is_active = true "
                "WHERE name = :old_name"
            ),
            params,
        )

        # An install whose seed predates the '學院審核通知' rule (or where it was
        # deleted) still needs trigger point 3, so insert it rather than leaving
        # the college with no mail at all.
        if result.rowcount == 0:
            already_present = bind.execute(
                sa.text("SELECT id FROM email_automation_rules WHERE name = :new_name"),
                {"new_name": NEW_RULE_NAME},
            ).first()
            if already_present is None:
                bind.execute(
                    sa.text(
                        "INSERT INTO email_automation_rules "
                        "(name, description, trigger_event, template_key, condition_query, "
                        " delay_hours, is_active) "
                        "VALUES (:new_name, :description, 'college_review_submitted', "
                        "        :template_key, :condition_query, 0, true)"
                    ),
                    params,
                )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "email_automation_rules" in tables:
        bind.execute(
            sa.text(
                "UPDATE email_automation_rules "
                "SET name = :old_name, "
                "    description = :description, "
                "    trigger_event = 'professor_review_submitted', "
                "    template_key = 'college_review_notification', "
                "    condition_query = NULL, "
                "    is_active = false "
                "WHERE name = :new_name"
            ),
            {
                "old_name": OLD_RULE_NAME,
                "description": "當教授審核完成後，通知學院有新案件待審核",
                "new_name": NEW_RULE_NAME,
            },
        )

    if "email_templates" in tables:
        bind.execute(sa.text("DELETE FROM email_templates WHERE key = :key"), {"key": TEMPLATE_KEY})
