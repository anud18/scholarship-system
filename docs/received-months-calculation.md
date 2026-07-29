# 已領月份數計算

「已領月份數」是同一位學生在某個獎學金配置（`scholarship_configuration`）下，依歷史 `PaymentRoster` 所推算的總月數。兩處會讀這個數字，且**必須一致**：

1. **博士生資格檢查** — `app/services/plugins/phd_eligibility_plugin.py` 檢查 36 個月上限
2. **手動分發頁** — `app/services/manual_distribution_service.py` 顯示欄位
3. **學生領獎紀錄查詢** — `app/services/student_scholarship_history_service.py`「已領月份數」卡片

三者共用 `app/services/received_months_service.py`。

---

## 計算規則

來源表：`payment_rosters` + `payment_roster_items`

篩選條件（**皆需符合**）：

- `payment_roster_items.student_number = :student_nycu_id`
- `payment_roster_items.is_included = TRUE`
- `payment_rosters.scholarship_configuration_id = :config_id`

> ⚠️ 比對鍵是 **`student_number`（學號 / `std_stdcode`）**，不是 `student_id_number`。
> `student_id_number` 已改存身分證字號（`std_pid`，供造冊 Excel 的「身分證字號」欄位），
> 不能用於跨造冊的學生身分比對（外籍生可能無身分證字號）。各呼叫端（分發頁、36 個月上限、歷史查詢）一律以學號比對。

**跨 sub_type 合併**：不篩選 `sub_type`，所以同一配置下的 `nstc`、`moe_1w`、`moe_2w` 一併計入。

**不跨學年度**：`scholarship_configuration_id` 是年度專屬鍵，因此只統計指定配置年度的 roster。若需跨年度加總，需呼叫端自行聚合。

## `roster_cycle` 換算月數

| `roster_cycle` | 每筆 roster 月數 | `period_label` 範例 |
| -------------- | ---------------- | ------------------- |
| `monthly`      | 1                | `2025-01`           |
| `semi_yearly`  | 6                | `2025-H1`           |
| `yearly`       | 12               | `2025`              |

**SQL 等價形式**（示意，實際以 SQLAlchemy 實作）：

```sql
SELECT
  SUM(CASE roster_cycle
    WHEN 'monthly' THEN 1
    WHEN 'semi_yearly' THEN 6
    WHEN 'yearly' THEN 12
    ELSE 1
  END) AS months_received
FROM payment_roster_items pri
JOIN payment_rosters pr ON pr.id = pri.roster_id
WHERE pr.scholarship_configuration_id = :config_id
  AND pri.student_number = :student_nycu_id
  AND pri.is_included = TRUE;
```

服務實作上，會按 `roster_cycle` 分組後再於 Python 端乘上對應係數，行為等價。

## 匯入 vs 系統計算

**已領月份數 = 匯入月份數 + 系統月份數**（相加，不是覆寫）。

| 來源       | 儲存位置                          | 範圍                            |
| ---------- | --------------------------------- | ------------------------------- |
| 匯入月份數 | `student_received_month_records`  | **終身**，鍵為 (學號, 獎學金類型) |
| 系統月份數 | 由上方規則即時計算（不寫回 DB）   | 單一 `scholarship_configuration`（單一學年度） |

> ⚠️ **相加的前提**：國科會的檔案記錄的是本系統接手造冊**之前**已發放的月份，
> 兩者不會涵蓋同一個月。若日後檔案的 `領獎起始月份`→`目前領獎月份` 區間與本系統
> 已造冊的月份重疊，總數會重複計算並可能誤觸 36 個月上限。
> 每筆匯入紀錄都存有 `award_start_month` / `award_current_month`，正是為了日後能
> 在不改 schema 的情況下排除重疊。詳見
> [ADR-0001](adr/0001-received-months-are-additive.md)。

**流程**：

1. 管理員打開手動分發頁 → `get_students_for_distribution` 被呼叫
2. 服務各以一次查詢取得兩半：
   - `get_imported_months_bulk_async(db, [學號], scholarship_type_id)`
   - `calculate_received_months_bulk_async(db, [學號], config_id)`
3. 每位學生：`received_months = 匯入 + 系統`
4. `received_months_source` 標示哪幾半有值（`imported+system` / `imported` / `system` / `null`），
   前端據此顯示「匯」標籤

系統值**從不寫回 DB**；每次開啟頁面都是即時查詢，roster 新增/取消會自動反映。

**匯入入口**：學生領獎紀錄查詢頁的「匯入已領月份數」按鈕（先預覽再確認），
解析規則見 [docs/samples/README.md](samples/README.md)。
匯入的月份數由 `領獎起始月份`→`目前領獎月份` **含頭含尾**推算，
不採用檔案中的「合計目前領獎月份數」。

> 舊的 `college_ranking_items.received_months` / `received_months_source` 覆寫欄位
> 已移除（migration `received_months_ledger_001`）。舊的
> `POST /manual-distribution/import-received-months` 端點亦已刪除。

## 邊界行為

| 情境                                        | 回傳值 |
| ------------------------------------------- | ------ |
| 學生沒有任何 included roster item           | `0`    |
| `scholarship_configuration` 查不到          | 空 dict（所有學生都沒有系統值） |
| 學生被軟刪除（`deleted_at IS NOT NULL`）    | 不列入計算批次 |
| Roster 存在但 `is_included=FALSE`           | 該筆不計 |
| PhD plugin 計算過程拋例外                   | `0`（fail open，允許升遷檢查通過） |

## 測試

- 單元測試：`backend/app/tests/test_received_months_service.py`（11 cases）
- 匯入解析：`backend/app/tests/test_received_months_parser.py`（31 cases）
- 測試執行方式（這個環境的 conftest 有已知問題，請加 `--noconftest`）：

```bash
docker exec scholarship_backend_dev python -m pytest --noconftest \
  app/tests/test_received_months_service.py --override-ini="addopts="
```

## 變更歷史

- 2026-04：抽出 `received_months_service`，與 PhD plugin 統一；修正「1 period = 1 month」bug 改為依 `roster_cycle` 換算月數；手動分發頁同步採用。
- 2026-07：匯入改為獨立的 `student_received_month_records` 帳本（鍵為學號，終身值），
  與系統值**相加**而非覆寫；匯入入口移至學生領獎紀錄查詢頁，並保存原始檔案的整列欄位值。
