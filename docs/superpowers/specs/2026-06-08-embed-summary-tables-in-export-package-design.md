# 申請資料 ZIP 內嵌「申請總表」設計

**日期**：2026-06-08
**狀態**：設計待 review
**範圍**：`/export-package`（申請資料大 ZIP）

## 1. 背景與目標

學院透過 `/export-package` 匯出「申請資料」時，目前產出的 ZIP 結構為：

```
某獎學金_申請資料_114_1_某學院.zip
├── 4460_教育博/
│   └── 310460031_王小明/
│       ├── 310460031_王小明_學生資料彙整.pdf
│       └── 310460031_王小明_成績單.pdf
└── 7300_資工系/
    └── ...
```

也就是 `系資料夾 / 學生資料夾 / (每位學生的彙整 PDF + 上傳檔案)`，**完全沒有任何跨人一覽的「申請總表」**。學院承辦在拿到這包資料後，仍需自行到另一支端點 `/department-summary-export` 逐系下載「學生資料彙整表」Excel，才能得到一份可掃視全體申請人的總表。

**目標**：讓 `/export-package` 的 ZIP 直接內嵌「申請總表」Excel，分兩層：

- **學院層**：ZIP 根目錄一份涵蓋全院所有申請人的總表
- **系所層**：每個系資料夾內一份該系申請人的總表

達成後 ZIP 結構為：

```
某獎學金_申請資料_114_1_某學院.zip
├── 114學年度某獎學金學生資料彙整表_某學院.xlsx        ← 學院總表（NEW）
├── 4460_教育博/
│   ├── 114學年度某獎學金學生資料彙整表_教育博.xlsx     ← 該系總表（NEW）
│   ├── 310460031_王小明/
│   │   ├── 310460031_王小明_學生資料彙整.pdf
│   │   └── 310460031_王小明_成績單.pdf
│   └── ...
└── 7300_資工系/
    ├── 114學年度某獎學金學生資料彙整表_資工系.xlsx     ← 該系總表（NEW）
    └── ...
```

「申請總表」直接重用既有的 `CollegeRankingExportService.build_workbook()`（與 `/department-summary-export` 產出同格式、同欄位的 Excel）。

### 不在範圍內（YAGNI）

- 不改 `/department-summary-export` 與 `/department-summary-export-bulk` 兩支既有端點的行為。
- 不新增前端 UI 選項；既有「匯出申請資料」按鈕的產出自動包含總表。
- 不改 `build_workbook` 的欄位定義與排版。

## 2. 既有元件盤點（重用）

| 元件 | 位置 | 角色 |
|---|---|---|
| `ExportPackageService.generate_export_zip()` | `app/services/export_package_service.py` | 申請資料大 ZIP 的組裝者（本次主要修改點） |
| `CollegeRankingExportService.build_workbook()` | `app/services/college_ranking_export_service.py` | 純渲染：給 rows + 欄位設定 → 回傳 xlsx bytes |
| `ExportRow` dataclass | 同上 | 一列申請人資料（`rank_position` / `application` / `bank_account` / `advisor_names`） |
| `load_export_aux_data()` | `app/api/v1/endpoints/college_review/_helpers.py` | 載入動態欄位、子類別中文標籤、郵局帳號、指導教授姓名 |

**關鍵事實**：`build_workbook` 透過 `ExportRow.application` 讀取的 `sub_type_preferences`、`sub_scholarship_type`、`student_data`、`submitted_form_data` 全是 `Application` 上的 **JSON / String 欄位（非關聯）**，隨 row 一起載入，因此 **不需要對 `Application` 額外 `selectinload`**。`bank_account` / `advisor_names` 則來自 `load_export_aux_data`（依 `user_id` 另查 `UserProfile` 與指導教授關聯）。

## 3. 架構與資料流

在 `generate_export_zip()` 現有流程的「建 ZIP（寫入每生 PDF + 上傳檔）」之後、回傳之前，插入一個「寫入總表」步驟：

```
1. 取得 scholarship
   → 改為載入完整 ScholarshipType + selectinload(sub_type_configs)
     （取代現在只取 name 的 _get_scholarship_name）
2. 查 applications（現狀，不動）
3. 依系所分群 dept_groups（現狀，key = "{dep_no}_{dep_name}"）
4. 建 ZIP：每系每生寫入彙整 PDF + 上傳檔（現狀，不動）
4.5 ★新增★ tables = await build_embedded_summary_tables(
              db, scholarship_type, dept_groups, college_name, academic_year)
         for path, xlsx_bytes in tables.items():
             zf.writestr(path, xlsx_bytes)
5. 組檔名、回傳（現狀，不動）
```

### 關鍵保證：總表與資料夾同源

`build_embedded_summary_tables` 接收的 apps 必須是 `generate_export_zip` 已查好、已分群的**同一份 `dept_groups`**，**不可**重新查詢。理由：

- `/export-package` 與 `/department-summary-export` 的 application 查詢條件不同（前者依 `std_academyno` 篩學院、status 白名單、200 筆上限、載入 `.files`；後者依 `std_depno` 篩系、status 排除 deleted、無上限）。
- 若總表另行重查，會出現「總表列出的人 ≠ 資料夾裡的人」的不一致。
- 直接重用 `dept_groups` 保證每張系總表的學生 == 該系資料夾下的學生資料夾，學院總表 == ZIP 內全部學生。

> 注意：分群 key 在 `/export-package` 用 `trm_depno/trm_depname`（來自 student term data），而 `/department-summary-export` 用 `std_depno`。兩者可能略有差異，但本功能一律以 `/export-package` 自身的 `dept_groups` 為準，以維持「總表 = 資料夾」一致性，不引入 `std_depno` 分群。

## 4. 新增模組（方案 A）

新增 `backend/app/services/export_summary_tables.py`，對外一個 async 函式：

```python
async def build_embedded_summary_tables(
    db: AsyncSession,
    scholarship_type: ScholarshipType,
    dept_groups: dict[str, list[Application]],
    college_name: Optional[str],
    academic_year: int,
) -> dict[str, bytes]:
    """回傳 { ZIP 內路徑 : xlsx_bytes }，含 1 份學院總表 + 每系 1 份系總表。"""
```

選擇獨立模組（而非把方法塞進 `ExportPackageService`）的理由：`export_package_service.py` 已 394 行，且「每生 PDF」與「跨人總表」是兩種不同職責；獨立小模組高內聚、可單獨單元測試。

### 內部邏輯

```
all_apps = [app for apps in dept_groups.values() for app in apps]
dynamic_fields, sub_type_labels, account_by_user, advisor_by_user =
    await load_export_aux_data(db, scholarship_type=scholarship_type, applications=all_apps)

scholarship_name = scholarship_type.name or "獎學金"
result: dict[str, bytes] = {}
service = CollegeRankingExportService()

def _rows(apps):  # apps 先依 _sort_key 排序，再轉 ExportRow(rank_position=None)
    ordered = sorted(apps, key=_sort_key)
    return [ExportRow(rank_position=None, application=a,
                      bank_account=account_by_user.get(a.user_id),
                      advisor_names=advisor_by_user.get(a.user_id)) for a in ordered]

# (a) 每系總表
for dept_folder, apps in sorted(dept_groups.items()):
    dept_name = _dept_name_from_apps(apps)           # 取自 student_data.trm_depname
    title = f"{academic_year}學年度{scholarship_name}學生資料彙整表 - {dept_name}"
    try:
        xlsx = await asyncio.to_thread(service.build_workbook,
                   rows=_rows(apps), dynamic_fields=dynamic_fields,
                   sub_type_labels=sub_type_labels, title=title,
                   sheet_name=f"{academic_year}學年")
        fname = f"{academic_year}學年度{scholarship_name}學生資料彙整表_{dept_name}.xlsx"
        result[f"{dept_folder}/{_sanitize_filename(fname)}"] = xlsx
    except Exception as e:
        logger.exception("dept summary table build failed: %s", dept_folder, exc_info=True)
        result[f"{dept_folder}/_錯誤_總表生成失敗.txt"] = f"系總表生成失敗：{e}".encode()

# (b) 學院總表：依系所分群、系內 _sort_key，串成一張全院表
college_rows = []
for dept_folder, apps in sorted(dept_groups.items()):
    college_rows.extend(_rows(apps))                 # 已分群、組內已排序 → 串接
college_label = college_name or "全校"
title = f"{academic_year}學年度{scholarship_name}學生資料彙整表 - {college_label}"
try:
    xlsx = await asyncio.to_thread(service.build_workbook,
               rows=college_rows, dynamic_fields=dynamic_fields,
               sub_type_labels=sub_type_labels, title=title,
               sheet_name=f"{academic_year}學年")
    fname = f"{academic_year}學年度{scholarship_name}學生資料彙整表_{college_label}.xlsx"
    result[_sanitize_filename(fname)] = xlsx          # 根目錄
except Exception as e:
    logger.exception("college summary table build failed", exc_info=True)
    result["_錯誤_學院總表生成失敗.txt"] = f"學院總表生成失敗：{e}".encode()

return result
```

`_sort_key`、`_sanitize_filename`、`_dept_name_from_apps` 為小工具：`_sort_key` 重用 `/department-summary-export` 同一份（換發優先 → 學號空值最後 → 學號 → id）；`_sanitize_filename` 重用 `export_package_service` 同一份（避免重複，擇一處放共用，另一處 import）。

> **設計決策（已確認）**
> - 「學院初審會議之學院排序」欄 → **一律留空**（`rank_position=None`），與 `/department-summary-export` 行為一致；匯出申請資料時尚未完成排序。
> - 學院總表列順序 → **先依系所分群，系內再依 `_sort_key`**（換發優先 → 學號）。

## 5. `ExportPackageService` 的改動

1. **`_get_scholarship_name` → `_get_scholarship_type`**：載入完整 `ScholarshipType` 並 `selectinload(ScholarshipType.sub_type_configs)`；`generate_export_zip` 用 `stype.name` 取代原 `scholarship_name`，同物件傳給 helper。
2. 在步驟 4 之後呼叫 `build_embedded_summary_tables`，逐一 `zf.writestr`。
3. 其餘流程（查詢、分群、每生 PDF、檔名、200 上限）**不變**。

## 6. 邊界情況

| 情況 | 行為 |
|---|---|
| 全校匯出（`college_code=None`，admin） | `college_name` 為 None → 學院總表標題「… - 全校」、檔名 `…_全校.xlsx`，內容涵蓋 ZIP 內所有系（與現有 zip 已混合各系的行為一致） |
| 未知系所（`unknown_未知系所` 資料夾） | 照樣產一份該夾系總表；`dept_name` 取 `未知系所` |
| 單一系的學院 | 學院總表與該系總表內容近乎重複，但**兩份都產**，忠於「學院層一份 + 每系一份」需求 |
| 申請數為 0 | 現有流程已先擲 `無申請資料可匯出`，不會進到本步驟 |
| 200 筆上限 | 不變，於本步驟之前即擋下 |

## 7. 錯誤處理

沿用既有「PDF 失敗寫 `_錯誤_*.txt`」模式：

- 每份 workbook 各自 `try/except`；某系失敗 → 在該系資料夾寫 `_錯誤_總表生成失敗.txt`，`logger.exception(..., exc_info=True)`，**不中斷整包 ZIP**。
- 學院層總表失敗 → 根目錄寫 `_錯誤_學院總表生成失敗.txt`。
- `build_workbook` 為同步 openpyxl，以 `asyncio.to_thread` 包裹，避免阻塞 event loop（與現有檔案抓取一致）。

## 8. 測試

### 8.1 單元測試 `test_export_summary_tables_*.py`
仿 `test_export_package_pure_helpers.py` / `test_application_summary_export_helpers.py`：

- monkeypatch `load_export_aux_data` 回傳固定 aux；餵 fake `dept_groups`（用 `Application(**defaults)` 建構，避免 `__new__` 繞過 `__init__` 的 `_sa_instance_state` 陷阱）。
- 斷言回傳 dict 的 key：含 1 個根目錄學院 xlsx + 每系 1 個 `{dept_folder}/...xlsx`。
- 以 openpyxl 載回 bytes，斷言：
  - 每張系總表資料列數 == 該系 apps 數。
  - 學院總表列數 == 全部 apps 數，且列順序「先依系所分群」（驗證跨系邊界處系所欄變化符合 `sorted(dept_groups)` 順序）。
  - 「學院初審會議之學院排序」欄（第 2 欄）全為空字串。
- 單系失敗（monkeypatch `build_workbook` 對特定 title 擲例外）→ 該系出現 `_錯誤_總表生成失敗.txt`，其餘系正常。

### 8.2 整合測試（仿 `test_application_summary_export_endpoint.py`）
- 對 `ExportPackageService.generate_export_zip()` 斷言 `ZipFile.namelist()` 同時含：根目錄學院 xlsx + 每個系資料夾下的系 xlsx。
- 斷言每張系總表的學號集合 == 該系資料夾下的學生資料夾名（學號）集合（總表 = 資料夾一致性）。

### 8.3 CI / Lint 硬性門檻
- `uvx --from "black==26.3.1" black --check --line-length=120 backend/app`
- `flake8 app --select=B904,B014 --max-line-length=120`（`raise ... from`、無冗餘例外 tuple）
- `except` 內 `logger.warning/error` 若插值例外變數須帶 `exc_info=True`
- 新增 async 測試會落在 CI 的 **integration** suite（`asyncio_mode = auto`）。

## 9. 影響面 / 風險

- **效能**：每包額外建 1 +(系數) 張 openpyxl workbook。申請上限 200 筆、系數通常數個到數十個，每張小檔，影響可忽略；`to_thread` 確保不阻塞。
- **回溯相容**：依專案政策「NO BACKWARD COMPATIBILITY」，直接改 `_get_scholarship_name`，不保留舊簽名。需 grep 確認該方法無其他呼叫者。
- **檔名衝突**：系總表檔名含系名、置於各自系資料夾；學院總表於根目錄含學院名；與既有「學生資料夾」名稱不衝突。
