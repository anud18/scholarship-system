# Sample files

Checked-in templates for admin-facing imports. Download directly; no auth
required for the static file, but the actual upload requires admin login.

## received-months-template.xlsx

Template for 「匯入已領月份數」 on the 手動分發 page.

**Format**

| 欄位      | 型別   | 必填 | 說明                                |
| --------- | ------ | ---- | ----------------------------------- |
| `學號`    | 字串   | 是   | NYCU 學號，對應 `std_stdcode`       |
| `已領月份數` | 整數 | 是   | 該學生目前已領取的月數，非負整數    |

- 第 1 列為表頭（`學號`, `已領月份數`），系統從第 2 列開始讀取
- 檔案格式必須為 `.xlsx`（不支援 `.xls`）
- 上傳大小上限 5 MB
- 找不到的學號會被忽略（回應會列在 `not_found` 中）
- 已匯入的值會覆寫系統自動計算的月份數，來源標記為 `imported`（UI 以藍色顯示）

**重新產生**

```bash
python3 backend/scripts/generate_received_months_sample.py
```

計算邏輯與系統自動計算的定義請見 [docs/received-months-calculation.md](../received-months-calculation.md)。
