# Sample files

Checked-in templates for admin-facing imports. Download directly; no auth
required for the static file, but the actual upload requires admin login.

## received-months-example.xlsx

「匯入已領月份數」的範例檔，複製國科會「獲獎生已領月份統計表」的空白表格式：
第 1 列標題、第 2 列表頭、第 3 列國科會的`範例`示範列，其後為預先編號的空白列。

入口在**學生領獎紀錄查詢**頁的「匯入已領月份數」對話框，可直接按「下載範例」取得
（`GET /api/v1/admin/received-months/template`）。實務上也可以不用這個範例，
直接上傳國科會核發的原始檔。

> 這個檔案與「下載範例」按鈕提供的內容出自同一個 `build_received_months_template()`，
> 不會各自漂移。

解析規則（表頭以名稱定位，不依欄位位置）：

| 欄位               | 必填 | 說明                                        |
| ------------------ | ---- | ------------------------------------------- |
| `學號`             | 是   | NYCU 學號，對應 `std_stdcode`               |
| `領獎起始月份`     | 是   | 民國月份，如 `113年9月`                     |
| `目前領獎月份`     | 是   | 民國月份，如 `115年8月`                     |
| `合計目前領獎月份數` | 否 | 僅作為核對；**不**採用為匯入值              |

- 月份數 = `領獎起始月份` 到 `目前領獎月份` 的**含頭含尾**月數（`113年9月`→`115年8月` = 24）
- 表頭上方的標題列、`範例` 示範列、學號空白列都會自動略過
- 月份格式接受 `113年9月`、`113年09月`、`113/9`、`113-09`、Excel 日期儲存格
- `合計目前領獎月份數` 與推算值不符 → 該列仍匯入（採推算值），並在預覽標示警告
- `領獎起始月份`／`目前領獎月份` 空白或無法解析，或結束早於起始 → 該列不匯入，預覽標示錯誤
- 系統中查無此學號者**仍會匯入**，待該生日後提出申請時即可套用
- 檔案格式必須為 `.xlsx`（不支援 `.xls`），上傳大小上限 5 MB
- 先「預覽」再「確認匯入」；未確認前不會寫入任何資料

**重新產生**

```bash
python3 backend/scripts/generate_received_months_sample.py
```

計算邏輯與系統自動計算的定義請見 [docs/received-months-calculation.md](../received-months-calculation.md)。
