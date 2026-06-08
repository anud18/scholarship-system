# 造冊 查看名單:顯示已移除者 + 回復功能 + 統一操作紀錄

- **日期**: 2026-06-08
- **分支**: `worktree-feat+roster-removed-restore-audit`
- **狀態**: 已實作 — 設計與實作計畫(`docs/superpowers/plans/2026-06-08-roster-removed-restore-audit.md`)皆已產出,程式碼於 PR #916

## 1. 目標

在造冊的「查看名單」(`RosterDetailDialog`)中:

1. **顯示之前被移除的人**(目前他們被前端過濾掉,完全看不到)。
2. 提供 **回復(restore)** 功能,把被移除的人放回名單。
3. **移除、新增(補充人)、回復** 三類事件都要有紀錄,管理員可在介面看到。

範圍涵蓋造冊現有的**三種移除途徑全部**(使用者明確要求「都做」):

| 移除途徑 | 觸發點 | 目前刪除方式 |
|---|---|---|
| 排除(繳回/放棄/其他) | `POST /items/{id}/exclude`,COMPLETED roster | 軟刪除 `is_included=False`(列保留) |
| 比對分發名單 移除孤兒 | `POST /reconcile` 的 remove 路徑,COMPLETED+LOCKED | **硬刪除** `db.delete()`(列消失) |
| 鎖定後移除 | `DELETE /items/{id}`,LOCKED roster | **硬刪除** `db.delete()`(列消失) |

## 2. 採用架構:統一軟刪除 + 單一造冊稽核軌跡

三種移除一律改成 **軟刪除**(`is_included=False`),所有 移除/新增/回復 事件統一寫進 **`RosterAuditLog`**(roster 範圍的稽核表,已存在)。前端「查看名單」內嵌顯示被移除的人並可回復,另加「操作紀錄」面板讀 `RosterAuditLog`。

### 為什麼幾乎零副作用
Excel 匯出 (`excel_export_service.py`)、人數統計 (`_recompute_roster_totals_sync`)、`received_months_service`、`student_scholarship_history_service` **早就** 用 `is_included` 過濾。把硬刪除改成軟刪除後,這些行為**完全不變**——被移除的人本來就不會出現在 Excel、不計入領取月數。

### 考慮過但不採用
- **保留硬刪除、從稽核日誌重建被刪的人**:脆弱(列已不存在,靠 log 拼湊易錯),且使用者選「都做」。
- **另建 archive 表存被移除的列**:多一張表沒好處,`is_included` 旗標已存在且各處早已過濾它。

## 3. 資料模型與移除語意

### 3.1 Enum
- `RosterAuditAction` 新增 **`ITEM_RESTORE = "item_restore"`**(`ITEM_ADD` / `ITEM_REMOVE` / `ITEM_UPDATE` 已存在)。
- **⚠️ 更正(2026-06-08,修 bug 後):`action` 欄並非 String-backed,而是 native PostgreSQL enum `rosterauditaction`**。只改 Python enum 會在寫入 `ITEM_RESTORE` 稽核列時於 PostgreSQL 觸發 500(`InvalidTextRepresentation: invalid input value for enum`);SQLite 測試 DB 不檢查 enum 故抓不到。**必須**新增 Alembic migration `ALTER TYPE rosterauditaction ADD VALUE IF NOT EXISTS 'item_restore'`(見 `backend/alembic/versions/add_item_restore_audit_001.py`)。

### 3.2 移除改為軟刪除
- `reconcile_roster` 的 remove 路徑(`roster_service.py` 約 line 2119–2139):把 `self.db.delete(item)` 改成
  `item.is_included = False; item.exclusion_reason = "比對分發移除:不在分發名單"`。
- `remove_item_from_locked_roster`(約 line 2167–2219):把 `self.db.delete(item)` 改成
  `item.is_included = False; item.exclusion_reason = f"鎖定後移除:{reason}"`。
- 不需新欄位、不需 table schema 變更;但 enum 加值需要一個 `ALTER TYPE ... ADD VALUE` migration(見 §3.1 更正)。

### 3.3 連帶調整(因為被移除的列現在會留著)
1. **比對分發 diff**:`get_distribution_diff_for_roster` 與 `reconcile_roster` 計算 `allowed_remove`(孤兒)時,要**排除已軟移除的列**(`is_included=False`),否則同一人會被一直重複標記為「待移除」。
2. **補充人(reconcile add)**:要 add 的 application 若**已有一筆軟移除的列**,改成**回復那一列**(`is_included=True`),而非新建第二列。
   - 背景:`payment_roster_items` 對 `(roster_id, application_id)` **無** unique 約束(只有一般 index),所以重複列不會被 DB 擋下——必須在程式層防止同一人出現兩列。

## 4. 後端 API

### 4.1 新增回復端點
```
POST /api/v1/payment-rosters/{roster_id}/items/{item_id}/restore
  body: { reason_note?: string }    # 選填補充說明
```
- 僅 admin(`check_user_roles([UserRole.admin], ...)`)。
- 對 `is_included=False` 的列翻回 `True`、清掉 `exclusion_reason`。
- 已是 `is_included=True` → `409 CONFLICT`(冪等,與 `exclude` 對稱)。
- 找不到 item / item 不屬於該 roster → `404` / `400`。
- 寫一筆 `RosterAuditLog`,`action=ITEM_RESTORE`,帶 `old_values`/`new_values`、操作者、IP、user-agent、reason。
- roster 為 `LOCKED` 時**允許**回復,並設 `excel_stale=True`(提示重匯 Excel),與「鎖定後移除」對稱。
- 回復後呼叫 `_recompute_roster_totals_sync` 重算人數/金額。

### 4.2 稽核統一(操作紀錄面板的單一來源)
目前 reconcile / locked-remove 寫的是**通用 `AuditLog`**,排除寫的是 **`RosterAuditLog`**——兩套,面板讀不到完整歷史。統一做法:

- 三種移除一律寫 `RosterAuditLog`(`ITEM_REMOVE`),補充人寫 `ITEM_ADD`,回復寫 `ITEM_RESTORE`。
- 每筆帶結構化 `audit_metadata`:`student_name`、`student_id`(學號)、`application_id`、`source`(`exclude` / `reconcile` / `locked_remove` / `restore`)、`reason`。
- `description` 用人類可讀句:「排除 王小明(繳回)」「比對分發移除 李大華」「回復 王小明」。
- 既有 `GET /{roster_id}/audit-logs` 端點沿用,前端面板直接讀它。
- **通用 `AuditLog` 寫入處置**:規劃階段先確認 reconcile/locked-remove 的通用 `AuditLog` 是否被全域稽核頁面消費。預設**移除**這些通用寫入、改以 `RosterAuditLog` 為單一來源(符合專案「不留向後相容」原則);若發現被全域頁面依賴,則保留並補上 `RosterAuditLog`。

## 5. 前端 查看名單(`RosterDetailDialog`)

### 5.1 名單內嵌顯示被移除的人
- 移除目前的 `items.filter(item => item.is_included)`(約 line 419,現在直接把被移除者從畫面拿掉)。
- 被移除的列:**置灰 + 刪除線 + 「已移除」標籤**,顯示移除原因 / 操作者 / 時間。
- 列尾「排除」按鈕,對已移除列改為 **「回復」** 按鈕 → 確認對話框 → 呼叫 restore 端點 → toast + 重抓名單。
- 人數與各學院人數仍只算 `is_included`(維持現狀,被移除者不計入「X 人」)。
- 提供「**顯示已移除**」切換,**預設開**;關閉時折疊被移除的列讓畫面乾淨。

### 5.2 操作紀錄面板
- Dialog 內新增可展開區/分頁「操作紀錄」,呼叫 `getAuditLogs(roster_id)`(API client 已存在)。
- 用既有 `frontend/components/audit-trail/AuditLogItem.tsx` 樣式,依時間倒序列出 移除/新增/回復,每筆顯示 動作圖示 + 學生 + 原因 + 操作者 + 時間。
- 動作篩選(全部 / 移除 / 新增 / 回復)。

## 6. 權限、鎖定、邊界規則

- **權限**:移除 / 回復 / 補充人 全部限 admin(與現況一致)。
- **鎖定 roster**:移除與回復**都允許**,一律設 `excel_stale=True`(對稱、可逆)。
- **孤兒回復語意**:被「比對分發」移除者(已不在分發名單)仍可回復,屬 admin 明確覆寫。回復後該列重新計入名單;比對 diff 仍會把它列為「在名單但不在分發」的可移除項(這是正確事實)。UI 文案需讓 admin 知道回復的是「分發名單已不含此人」者。
- **防重複**:同一 application 在一份 roster 永遠最多一筆 item;補充人遇既有軟移除列 → 回復而非新建。

## 7. 測試

### 後端
- restore 端點:成功翻旗標、`409` 冪等、`404`、非 admin `403`、`LOCKED` 允許並設 `excel_stale`、回復後 totals 正確。
- 三種移除改軟刪除後:Excel 匯出與人數統計不變(被移除者仍排除)。
- 比對 diff 排除已軟移除列(不再重複標記孤兒)。
- 補充人遇既有軟移除列 → 回復而非新建第二列。
- 每種事件(三種移除 / 補充 / 回復)都寫對一筆 `RosterAuditLog` 且 `audit_metadata` 欄位齊全。

### 前端
- 被移除列渲染:置灰 + 「已移除」標籤 + 回復按鈕。
- 回復流程:確認 → 呼叫 → toast → 重抓名單。
- 「顯示已移除」切換折疊/展開。
- 操作紀錄面板渲染與動作篩選。

### CI / Lint
- `uvx --from "black==26.3.1" black --check --line-length=120 backend/app`
- `flake8 app --select=B904,B014 --max-line-length=120`(restore 端點的 `raise ... from e`)
- async 服務測試用 async fixture + `await`。
- 若改動 API schema,跑 `cd frontend && npm run api:generate` 並 commit `lib/api/generated/schema.d.ts`。

## 8. 主要檔案

**後端**
- `backend/app/models/roster_audit.py`(加 `ITEM_RESTORE`)
- `backend/app/api/v1/endpoints/payment_rosters.py`(新 restore 端點;exclude 端點對齊;audit 統一)
- `backend/app/services/roster_service.py`(reconcile / locked-remove 改軟刪除;diff 排除軟移除;補充人改回復)

**前端**
- `frontend/components/roster/RosterDetailDialog.tsx`(內嵌已移除者 + 回復 + 操作紀錄面板)
- `frontend/lib/api/modules/payment-rosters.ts`(加 `restoreRosterItem`)
- 重用 `frontend/components/audit-trail/AuditLogItem.tsx`
