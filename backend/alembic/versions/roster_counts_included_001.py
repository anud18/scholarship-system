"""Recompute roster counts from 納入造冊 + 繁中化 exclusion_reason.

# Why

造冊列表 / 造冊詳情 對同一份名單顯示兩個數字：

  - 造冊詳情「納入造冊人數」= COUNT(payment_roster_items.is_included)  → 47
  - 造冊列表「N 人」= payment_rosters.qualified_count                  → 13

`qualified_count` 產生時是以舊的 `PaymentRosterItem.is_qualified`
（= 已驗證 + 納入造冊 + **有郵局帳號**）計算，因此缺郵局帳號的學生被算成
「不合格」並且不計入 total_amount——但他們其實仍在造冊名單內（補件即可撥款）。

程式端已改以 `is_included` 為唯一判準（與 `_recompute_roster_totals_sync`、
Excel「納入造冊」欄同源）。本 migration 將**既有**造冊的統計欄位重算，
讓歷史資料與新邏輯一致。

# 同時處理

`exclusion_reason` 過去把英文列舉值直接寫進使用者可見文案
（`學籍驗證未通過: suspended`）。此處一併改寫為繁體中文
（`學籍驗證未通過：休學中`），對應 STUDENT_VERIFICATION_STATUS_LABELS。

# Safety

純資料 migration，無 DDL。以 `to_regclass` 檢查資料表存在後才執行，
在尚未建立造冊資料表的資料庫上為 no-op。downgrade 不還原數字
（舊值已無法從 items 反推出「有無郵局帳號」以外的資訊），僅還原文案格式。

Revision ID: roster_counts_included_001
Revises: received_months_ledger_001
Create Date: 2026-07-28
"""

import sqlalchemy as sa
from alembic import op

revision = "roster_counts_included_001"
down_revision = "received_months_ledger_001"
branch_labels = None
depends_on = None


# 英文列舉值 → 繁體中文標籤（對應 app.models.payment_roster
# .STUDENT_VERIFICATION_STATUS_LABELS）
_STATUS_LABELS = {
    "verified": "已驗證",
    "graduated": "已畢業",
    "suspended": "休學中",
    "withdrawn": "已退學",
    "api_error": "驗證錯誤",
    "not_found": "查無此人",
}

_RECOMPUTE_SQL = sa.text("""
    UPDATE payment_rosters r
       SET total_applications = s.total_count,
           qualified_count    = s.included_count,
           disqualified_count = s.total_count - s.included_count,
           total_amount       = s.included_amount
      FROM (
            SELECT roster_id,
                   COUNT(*) AS total_count,
                   COUNT(*) FILTER (WHERE is_included) AS included_count,
                   COALESCE(
                       SUM(scholarship_amount) FILTER (WHERE is_included), 0
                   ) AS included_amount
              FROM payment_roster_items
             GROUP BY roster_id
           ) s
     WHERE r.id = s.roster_id
    """)


def _tables_exist(bind) -> bool:
    return all(
        bind.execute(sa.text("SELECT to_regclass(:t)"), {"t": table}).scalar() is not None
        for table in ("payment_rosters", "payment_roster_items")
    )


def upgrade() -> None:
    bind = op.get_bind()
    if not _tables_exist(bind):
        return

    for value, label in _STATUS_LABELS.items():
        bind.execute(
            sa.text("""
                UPDATE payment_roster_items
                   SET exclusion_reason = :new_reason
                 WHERE exclusion_reason = :old_reason
                """),
            {"old_reason": f"學籍驗證未通過: {value}", "new_reason": f"學籍驗證未通過：{label}"},
        )

    bind.execute(_RECOMPUTE_SQL)


def downgrade() -> None:
    bind = op.get_bind()
    if not _tables_exist(bind):
        return

    for value, label in _STATUS_LABELS.items():
        bind.execute(
            sa.text("""
                UPDATE payment_roster_items
                   SET exclusion_reason = :new_reason
                 WHERE exclusion_reason = :old_reason
                """),
            {"old_reason": f"學籍驗證未通過：{label}", "new_reason": f"學籍驗證未通過: {value}"},
        )
