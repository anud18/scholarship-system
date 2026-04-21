# 已領月份數計算

「已領月份數」是同一位學生在某個獎學金配置（`scholarship_configuration`）下，依歷史 `PaymentRoster` 所推算的總月數。兩處會讀這個數字，且**必須一致**：

1. **博士生資格檢查** — `app/services/plugins/phd_eligibility_plugin.py` 檢查 36 個月上限
2. **手動分發頁** — `app/services/manual_distribution_service.py` 顯示欄位

兩者共用 `app/services/received_months_service.py`。

---

## 計算規則

來源表：`payment_rosters` + `payment_roster_items`

篩選條件（**皆需符合**）：

- `payment_roster_items.student_id_number = :student_nycu_id`
- `payment_roster_items.is_included = TRUE`
- `payment_rosters.scholarship_configuration_id = :config_id`

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
  AND pri.student_id_number = :student_nycu_id
  AND pri.is_included = TRUE;
```

服務實作上，會按 `roster_cycle` 分組後再於 Python 端乘上對應係數，行為等價。

## 匯入 vs 系統計算

`college_ranking_items.received_months_source` 欄位決定資料來源：

| `received_months_source` | 意義                         | 優先順序 |
| ------------------------ | ---------------------------- | -------- |
| `imported`               | 管理員手動匯入的覆寫值       | 最高     |
| `system`                 | 由上方規則即時計算（不寫回 DB） | 其次     |
| `NULL`                   | 兩者都沒有 → 前端顯示 `-`    | 無值     |

**流程**：

1. 管理員打開手動分發頁 → `get_students_for_distribution` 被呼叫
2. 服務呼叫 `calculate_received_months_bulk_async(db, [student_ids], config_id)` 一次算完所有學生
3. 每位學生：
   - 若 `item.received_months_source == "imported"` → 用 DB 中的覆寫值
   - 否則 → 用剛算的系統值，`source` 標為 `"system"`
4. 回傳給前端，前端用 `source` 決定是否顯示「匯」標籤

系統值**從不寫回 DB**；每次開啟頁面都是即時查詢，roster 新增/取消會自動反映。

管理員若要覆寫，走 [匯入已領月份數](../docs/samples/README.md) 流程，該路徑才會 `UPDATE college_ranking_items SET received_months = ..., received_months_source = 'imported'`。

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
- 測試執行方式（這個環境的 conftest 有已知問題，請加 `--noconftest`）：

```bash
docker exec scholarship_backend_dev python -m pytest --noconftest \
  app/tests/test_received_months_service.py --override-ini="addopts="
```

## 變更歷史

- 2026-04：抽出 `received_months_service`，與 PhD plugin 統一；修正「1 period = 1 month」bug 改為依 `roster_cycle` 換算月數；手動分發頁同步採用。
