# 造冊 Excel 加上資格驗證資訊 + 不符合儲存格紅底

**Date:** 2026-06-30
**Branch:** `worktree-roster-excel-eligibility`
**Status:** Approved (design)

## 1. 目標 (What & Why)

造冊（payment roster）匯出的 Excel 目前是 STD_UP_MIXLISTA 30 欄付款格式，只列出「合格／納入」的學生，**看不到**每位學生的資格驗證結果。承辦人無法在 Excel 上一眼判斷誰、為什麼不符合。

本功能在造冊 Excel 主名單後面**附加資格驗證欄位**，把**每一條獎學金規則各做成一欄**，並對**不符合的儲存格**上**紅底**（硬性規則 / 學籍 / 銀行 / 排除）或**琥珀底**（警告規則）。讓承辦人直接在 Excel 上審閱資格，紅底列可在上傳付款系統前移除。

## 2. 既有架構重點 (Context)

- 匯出服務：`backend/app/services/excel_export_service.py`（`ExcelExportService`）。
- repo 內**沒有** `.xlsx` template 檔，`_load_template_structure()` 永遠 fallback 到 `_set_default_columns()`，`use_template` 永遠為 `False` → 一律以 `openpyxl.Workbook()` 從預設 30 欄重新建檔。
- `self.field_mapping`（`_set_default_columns` 設定）在匯出流程中**未被讀取**（dead），不動它。
- `item.excel_row_data` 為 write-only（無外部 consumer），可自由調整。
- 每個 `PaymentRosterItem` 已凍結存有資格快照：
  - `verification_status`（學籍：verified/graduated/suspended/withdrawn/api_error/not_found）
  - `is_eligible` property（整體規則資格；`rule_validation_result` 為 None 時回傳 None）
  - `rule_validation_result["details"]["rule_{id}"]` = `{passed, rule_name, rule_type, actual_value, expected_value, operator, message, is_hard_rule, is_warning}`（**逐條規則結果**，產生造冊當下凍結）
  - `failed_rules` / `warning_rules`、`bank_account`、`is_included` / `exclusion_reason`、`is_qualified` property
- `is_included=False` 為**多義**：可能是「產生時因資格不符自動排除」，也可能是「鎖定後手動移除（`exclusion_reason` 前綴『鎖定後移除』）」或「比對分發移除（前綴『比對分發移除』）」。

## 3. 設計 (Design)

所有變更集中在 `excel_export_service.py`（+ 既有測試檔）。一律使用**凍結快照**，不重跑驗證/規則引擎。

### 3.1 欄位佈局（每次匯出動態決定）

```
[ 既有 30 欄付款格式 — 不變 ]
 學籍驗證 | 規則資格 | <規則1> | <規則2> | … | <規則N> | 納入造冊 | 排除原因
```

- **逐條規則欄**：header = 規則的 `rule_name`；來源為所有 item 的 `rule_validation_result["details"]` 中 `rule_{id}` 的**聯集**，依 `rule_id` 升冪排序。
  - header 去重：若兩條規則 `rule_name` 相同，後者加上 `（#{rule_id}）` 後綴，確保 header 唯一（因 row_data 以 header 為 key）。
  - 排除非規則鍵：`no_rules_found`、`error` 等不是 `rule_{數字}` 的鍵略過。
- 同一 roster 為單一 scholarship config + period + sub_type，理論上規則集一致；仍以聯集處理跨 item 差異與「無快照」item。

### 3.2 各欄內容

| 欄位 | 內容 | 來源 |
|------|------|------|
| 學籍驗證 | 已驗證/已畢業/休學中/已退學/驗證錯誤/查無此人 | **重用** `_get_verification_status_label(verification_status)` |
| 規則資格 | 符合 / 不符合 / —（無快照） | `item.is_eligible`（None→「—」） |
| `<規則N>` | 通過 / 未通過 / —（該筆無此規則快照） | `details["rule_{id}"]["passed"]` |
| 納入造冊 | 是 / 否 | `item.is_included` |
| 排除原因 | 文字 | `item.exclusion_reason or ""` |

### 3.3 儲存格上色（只標出問題的儲存格）

紅底 = `PatternFill(start_color="FFC7CE", ...)`（Excel 標準淺紅）；琥珀底 = `PatternFill(start_color="FFEB9C", ...)`。

| 條件 | 上色儲存格 | 顏色 |
|------|-----------|------|
| 無 `bank_account` | 帳號（既有第 3 欄） | 紅 |
| `verification_status != VERIFIED` | 學籍驗證 | 紅 |
| `is_eligible == False` | 規則資格 | 紅 |
| 某條**硬性**規則 `passed == False`（`is_hard_rule`） | 該規則欄 | 紅 |
| 某條**警告**規則 `passed == False`（`is_warning`） | 該規則欄 | 琥珀 |
| `is_included == False` | 納入造冊、排除原因 | 紅 |

規則欄文字固定為「通過/未通過」；warning 規則未通過時文字仍為「未通過」，但底色為琥珀以區別硬性不符。

### 3.4 納入範圍

- 預設（`include_excluded=False`）：列出「`is_included=True`」**＋**「因資格不符自動排除」者；**隱藏手動移除**者。
- `include_excluded=True`：列出全部（含手動移除）。
- 判斷手動移除：新增 pure helper `_is_manual_removal(item)` → `bool(item.exclusion_reason and item.exclusion_reason.startswith(("鎖定後移除", "比對分發移除")))`。
- `_get_roster_items()` 改為依上述規則過濾（取代目前「`include_excluded=False` 只回 `is_included=True`」）。

### 3.5 重用 vs 新增 (DRY)

**重用既有，不重寫：**
- `_get_verification_status_label()`（學籍標籤）
- `PaymentRosterItem.is_eligible`（整體規則資格）
- `item.rule_validation_result["details"]`（逐條規則 pass/fail + 名稱；不重跑 `roster_service._evaluate_scholarship_rule`）
- `_format_allocation_display()`（分發獎學金欄，已用）
- 既有 `PatternFill` import

**新增（最小化、皆 pure / 易測）：**
- `_collect_rule_columns(items) -> List[Tuple[int, str]]`：排序去重的 `(rule_id, header)`。
- `_is_manual_removal(item) -> bool`。
- 重構 `_prepare_excel_data(roster, items, rule_columns)`：回傳 `(excel_data, cell_fills)`，其中 `cell_fills` 為與 `excel_data` 平行的 list，每筆是 `{header: "red" | "amber"}`。
- `_create_excel_file(...)` 改接受明確 `columns` 與 `cell_fills`；header loop / 寫資料 / 套色皆依 `columns`。
- `_set_column_widths(ws, columns)`、`_set_borders(ws, max_row, columns)` 改吃明確 `columns`（不再依賴靜態 `self.template_columns`）。
- `self.template_columns` 保持為 base 30 欄（靜態）；每次匯出計算 `export_columns = base + 驗證/規則欄`，並 thread 進上述方法；`export_roster_to_excel` 回傳的 `template_columns` 與 `preview_roster_export` 回傳的 `column_headers` 改為 `export_columns`。

### 3.6 資料流

```
export_roster_to_excel
  items = _get_roster_items(roster, include_excluded)          # 3.4 過濾
  rule_columns = _collect_rule_columns(items)                  # 3.1
  export_columns = base(30) + [學籍驗證, 規則資格] + rule headers + [納入造冊, 排除原因]
  excel_data, cell_fills = _prepare_excel_data(roster, items, rule_columns)   # 3.2 + 3.3
  _create_excel_file(excel_data, cell_fills, export_columns, ...)             # 寫檔 + 套色
```

## 4. Error handling / Edge cases

- `rule_validation_result is None`（舊資料）：規則資格與所有規則欄 = 「—」，不上色。
- `details == {"no_rules_found": True}`：無規則欄來源。
- 全部 item 皆無規則：無逐條規則欄，只有 學籍驗證/規則資格/納入造冊/排除原因。
- 無任何 item（header-only 檔）：照舊產生只有表頭的有效檔（含新欄位 header）。
- header 衝突：以 `（#id）` 後綴去重。

## 5. Testing（TDD）

僅 `app/tests/test_excel_export_service_rows.py` 觸及這些 internals（blast radius 小）。以 `SimpleNamespace` stub（沿用既有 pattern）新增：

1. 逐條規則欄由 `details` 快照產生、依 rule_id 排序、header 去重。
2. 規則欄文字 通過/未通過/—；硬性未通過→紅、警告未通過→琥珀（實際寫暫存 workbook 後讀 `cell.fill` 驗證）。
3. 學籍/銀行/規則資格/納入造冊/排除原因 紅底條件。
4. `_is_manual_removal` 過濾：手動移除預設不出現、`include_excluded=True` 才出現；自動排除者預設出現且上色。
5. 無快照 item → 規則欄/規則資格「—」、不上色。
6. 既有 30 欄付款內容不變（回歸）。

Lint gate（依 CLAUDE.md）：`black --line-length=120`、`flake8 --select=B904,B014`。

## 6. 風險（使用者已接受）

- 此舉會在官方 STD_UP_MIXLISTA 付款表後加欄並把不符合學生（紅底）一併列入，因此匯出檔轉為「審閱用文件」；上傳付款系統前需移除紅底列。
- 規則多時欄位會變多——這正是「每一條規則一欄」的預期行為。
