# 學院分發結果：系所欄位、Excel/PDF 匯出、權限補正

**Date:** 2026-07-15
**Status:** Approved design — ready for implementation plan
**Supersedes/extends:** [2026-06-30-college-view-distribution-results-design.md](./2026-06-30-college-view-distribution-results-design.md)

## Goal

三件事，對應使用者需求「學院看的到分發結果（確認權限，不會看到別的學院的名單，學號 姓名 系所 要在上面，分發結果匯出功能 Excel+PDF）」：

1. **系所** — 分發結果的每位學生要顯示 學號 / 姓名 / **系所**（目前只有學號+姓名）。
2. **匯出** — 分發結果可匯出 Excel 與 PDF。
3. **確認權限** — 確保學院不會看到別的學院的名單，並補上既有實作漏掉的授權檢查。

## Current state (verified 2026-07-15)

「學院看得到分發結果」**已經存在**，由 2026-06-30 spec 實作：

- `GET /api/v1/college-review/distribution-results` — `backend/app/api/v1/endpoints/college_review/distribution.py:423-566`
- `frontend/components/college/distribution/DistributionResultPanel.tsx`
- 由 admin toggle `ScholarshipConfiguration.allow_college_view_distribution` 控制（關閉時 403「分發結果尚未開放查看」）
- Tab 只對 college 角色出現（`CollegeManagementShell.tsx:344-381`）；admin/super_admin 走 `ManualDistributionPanel`，
  所以 `require_college` 排除 admin 是**刻意**的，不是缺陷。
- 既有測試 `backend/app/tests/test_college_view_distribution.py:300` 已驗證跨學院隔離（B 學院學生不出現在 A 學院回應中）。

因此本設計的真正工作是：**補系所、補匯出、修既有缺陷**，而不是重建面板。

### 既有缺陷（由 adversarial design probe 確認，非本次新增）

匯出功能會把這些缺陷印到正式文件上 — 螢幕上的瑕疵，在交給學院的 Excel/PDF 上會變成權威性的錯誤。使用者已決定**全部修**。

| # | 缺陷 | 證據 |
|---|------|------|
| 1 | **缺 grant 授權檢查**：只檢查 role + `college_code` + toggle，未檢查此學院是否被指派到此獎學金/學年度。可列舉 `scholarship_type_id` 取得未授權獎學金的名單。 | `distribution.py:423-461`；對照 `ranking_management.py:1237-1240`、`export_package.py:56-60`、`application_summary_export.py:91-94`、`application_review.py:75-80` 皆有檢查；gate 實作於 `_helpers.py:66-93`（college 需 `AdminScholarship` grant row）與 `_helpers.py:96-128` |
| 2 | **ranking 查詢未依學院 scope**：`distribution_executed = any(...)` 跨所有學院取 OR，A 學院可能因 B 學院已分發而看到整份「未錄取」名單。 | `distribution.py:464-473`（無 `college_code` 述詞）、`:477`（跨學院 any）、`:544-545`（未處理→rejected）；對照 `ranking_management.py:75-80`（issue #1034，「different colleges stay isolated」） |
| 3 | **未依 application_id 去重**：同一學生可能同時被列為 正取 與 未錄取。 | `distribution.py:514-545`（無去重）；`manual_distribution_service.py:556-583` 記載此情境確實會發生（同學院的 `default` ranking 與 sub-type ranking 同時 finalized）並實作了去重與優先規則 |
| 4 | **順序不決定 + 未錄取無名次**：items 查詢無 `ORDER BY`；rejected 清單未排序；rejected dict 不帶 `rank_position`。 | `distribution.py:503-509`、`:545`、`:556-558`；對照 `manual_distribution_service.py:459-467`（明確排序以確保決定性） |

缺陷 1 其實是對 **2026-06-30 spec 自身意圖的違反** — 該 spec line 104-106 要求「Order any college-permission
assertion **before** reading the flag, so a cross-college caller gets a permission error rather than leaking the
flag state」，但實作只做了 `college_code` 真值檢查。

## Scope decisions (locked with user)

- **匯出欄位**：`類別 / 結果 / 名次 / 學號 / 姓名 / 系所`。**不含任何 PII**（無身分證、無匯款帳號）。
  學院拿到的就是畫面上看到的。
  - 因為無 PII，**不寫 `pii_access` AuditLog**（與 `ranking_management.py` 的 PII 匯出不同）。
    此判斷經 probe 驗證通過。
- **系所來源**：`student_data["trm_depname"]`（申請當時的快照），不 join `departments` 表。
  與 `manual_distribution.py:492`、`payment_rosters.py:1373`、`college_ranking_export_service.py:292` 一致。
  代價：學生事後轉系仍顯示舊系所 — 與系統其他所有 系所 顯示行為一致。
- **既有缺陷**：全部修（1–4）。
- **不重寫面板結構**：維持 正取/備取/未錄取 分區清單，只加 系所 與 匯出。

## Design

### 1. 架構與檔案配置

| 檔案 | 動作 |
|------|------|
| `backend/app/api/v1/endpoints/college_review/_helpers.py` | **新增** `load_college_distribution_results(...)` — gate + scope + 去重 + 分組 |
| `backend/app/services/college_distribution_export_service.py` | **新增** leaf service — `build_workbook()` / `build_pdf()` |
| `backend/app/api/v1/endpoints/college_review/distribution.py` | JSON endpoint 改為薄呼叫；**新增** export endpoint |
| `frontend/lib/api/modules/college.ts` | **新增** `exportDistributionResults(...)`；`DistributionStudent` 加 `department` |
| `frontend/components/college/distribution/DistributionResultPanel.tsx` | Row 加 系所；加 匯出 dropdown |

**Loader 放 `_helpers.py`，不放新的 service module。** 理由：loader 必須 raise `HTTPException`，而
`app/services/` 的 60 個檔案中只有 `minio_service.py` 引用 `HTTPException`，且 tripwire test 的 docstring 將其列為
反面教材。`_helpers.py` 本身已是這個 package 中「共用 gate（`assert_can_manage_ranking:43` raise 403）＋共用 async
loader（`load_export_aux_data:159`）」的家。放這裡讓 raise 點與 status code 單一來源，兩個 endpoint 零轉譯繼承。

**關鍵性質：匯出無法繞過 loader 取得資料**，因此匯出與面板在「顯示誰」這件事上不可能分歧。這讓
「不會看到別的學院的名單」從一個**測試出來的性質**變成一個**結構上成立的性質**。

### 2. 權限模型

`load_college_distribution_results` 的 gate chain，**順序即設計**（權限先於旗標，避免向無 grant 的學院洩漏 toggle 狀態）：

| # | 檢查 | 失敗 |
|---|------|------|
| 1 | `require_college`（endpoint dependency；admin 由 `ManualDistributionPanel` 服務，刻意排除） | 403 |
| 2 | `current_user.college_code` 為真 | 403 使用者未綁定學院 |
| 3 | **新增** `_check_scholarship_permission(user, scholarship_type_id, db)` | 403 無權限存取此獎學金類型 |
| 4 | **新增** `_check_academic_year_permission(user, academic_year, db)` | 403 無權限存取此學年度 |
| 5 | active `ScholarshipConfiguration` 存在 | 404 找不到對應的獎學金配置 |
| 6 | `config.allow_college_view_distribution` | 403 分發結果尚未開放查看 |

**兩層獨立的學院 scope（刻意重複，defence in depth）：**

1. SQL 層 — ranking 查詢加 `CollegeRanking.college_code == college_code`（**新增**，對齊 `ranking_management.py:80`）
2. Python 層 — 既有的 per-student `get_college_code_from_data(sd) != college_code` skip

任一層單獨都足夠；兩層並存意味著未來其中一層出錯不會造成洩漏。

`raise ... from` 規則（B904）適用於任何 except 內的 raise。

### 3. 資料載入（loader 內部）

1. Gate chain（§2）。
2. Rankings：`(scholarship_type_id, academic_year, semester)` **且** `college_code == college_code`。
3. `distribution_executed = any(r.distribution_executed for r in rankings)` — 現在只涵蓋**本學院**的 rankings。
   未分發 → 回 `{distribution_executed: False, sub_types: []}`（非錯誤）。
4. Items：`.order_by(CollegeRankingItem.rank_position, CollegeRankingItem.id)`（對齊
   `manual_distribution_service.py:467`）。維持既有的
   `selectinload(CollegeRankingItem.application).load_only(Application.student_data, Application.deleted_at)`（避免 N+1）。
5. 跳過 soft-deleted（`appn.deleted_at is not None`）與無 `student_data` 者。
6. Python 層學院 scope。
7. **去重 by `application_id`**：沿用 `manual_distribution_service.py:563-583` 已驗證的優先規則 —
   優先保留帶有真實 allocation 的 item；兩個 item 都帶 allocation 時 `logger.warning`（可發現的資料異常）。
   去重必須在分組**之前**。
8. 分組為 `admitted` / `backup` / `rejected`；**`rank_position` 一併帶到 rejected dict**，讓匯出的「名次」欄有值且可排序。
9. 排序使用 None-last sentinel（`(x is None, x or 0)`），不用 `or 0`（`or 0` 會讓 None 與 0 混淆）。
   rejected 亦排序。

回傳結構不變（新增 `department`）：

```jsonc
{
  "distribution_executed": true,
  "sub_types": [{
    "code": "nstc", "label": "國科會", "label_en": "NSTC",
    "admitted": [{ "student_number": "310460031", "student_name": "王小明",
                   "department": "電子研", "rank_position": 1 }],
    "backup":   [{ "student_number": "310460052", "student_name": "陳小美",
                   "department": "資工研", "backup_position": 1 }],
    "rejected": [{ "student_number": "310460088", "student_name": "張三",
                   "department": "電子研", "rank_position": 5 }]
  }]
}
```

### 4. 匯出 service

`backend/app/services/college_distribution_export_service.py`，複製
`college_ranking_export_service.py` 已驗證的形狀：

- `_COLUMNS: list[tuple[str, float]]` = `類別 / 結果 / 名次 / 學號 / 姓名 / 系所`（label + PDF 權重），
  其中 `類別` = sub-type label（`label_map` 解析後的中文名，非 raw code）、
  `結果` ∈ {`正取`, `備取`, `未錄取`}、`名次` = 正取取 `rank_position`、備取取 `backup_position`、
  未錄取取 `rank_position`，
  由此導出 `_HEADERS` 與 `_COL_WEIGHTS` — 單一來源，改 label 不會默默改錯欄寬。
- `_headers()` / `_row_cells(...)` — `build_workbook` 與 `build_pdf` 共用，格式不可能漂移。
- **扁平化順序**：sub-type group（依 code 排序）→ 正取, 備取, 未錄取 → 名次。
- `build_workbook()`：openpyxl；**每個 cell 都過 `sanitize_excel_cell`**（`app.utils.excel_safety`），
  對齊 `college_ranking_export_service.py:130`。
  理由：openpyxl 會把開頭的 `=` 寫成**活的公式**，而 姓名/系所 來自 SIS。
  「無 PII 故不需 audit log」對 audit log 成立，但**不延伸到 formula injection** — 那是另一個獨立的控制。
- `build_pdf()`：A4 **landscape**（6 欄用 landscape 經 probe 驗證無問題）、`pdf_fonts.ensure_cjk_font()`、
  `wordWrap="CJK"`、`xml_escape`、`repeatRows=1`、`KeepInFrame(mode="shrink")`、
  權重正規化至可用頁寬。**不套用 `sanitize_excel_cell`** — reportlab 無公式語意，
  前綴單引號會變成可見的渲染雜訊。這是兩種格式在共用 `_row_cells` 之後**唯一合理的分歧點**。
- **零列情況**：仍輸出表頭（不可讓 reportlab 收到空 table）。

### 5. 匯出 endpoint

```
GET /api/v1/college-review/distribution-results/export
    ?scholarship_type_id=<int>&academic_year=<int>&semester=<str|null>&format=xlsx|pdf
auth: require_college
```

- `format: Literal["xlsx", "pdf"] = Query("xlsx")` — 對齊 `ranking_management.py:1202`；`extension = format`。
- 呼叫**同一個 loader**（§1 的關鍵性質）。
- 檔名：`{academic_year}學年度{scholarship_name}分發結果_{college_label}.{ext}`，
  以 `quote(..., safe="")` 編碼。
- `StreamingResponse`，headers：`Content-Disposition: attachment; filename*=UTF-8''{encoded}`、`Content-Length`。
- **不寫 AuditLog**（無 PII）。

### 6. 前端

- `frontend/lib/api/modules/college.ts`：
  - `DistributionStudent` 加 `department: string`。
  - `exportDistributionResults({ scholarshipTypeId, academicYear, semester, format = "xlsx" })`，
    重用既有的 `_fetchBinaryExport`。沿用 `exportRankingExcel` 的慣例：
    `if (format !== "xlsx") params.set("format", format)`，讓 xlsx URL 保持不變。
- `frontend/components/college/distribution/DistributionResultPanel.tsx`：
  - `Row` 加 系所 顯示。
  - 加 匯出 `DropdownMenu`（匯出 Excel / 匯出 PDF），重用 `triggerBlobDownload` 的 blob 下載模式
    （`URL.createObjectURL` → `<a download>` → `click()` → `revokeObjectURL`），成功時 toast。
  - 尚未分發時不顯示匯出鈕。
- OpenAPI 型別重新產生（CLAUDE.md §8）。**注意**：不可用 `npm run api:generate`（它打 `localhost:8000`，
  而該埠服務的是另一個 worktree）。改為從**本 worktree** 的 app dump spec 後再跑 openapi-typescript。

### 7. 測試

新測試落在 **integration** lane（async def 會被自動收集為 integration 並從 unit 排除）。

**Backend（`backend/app/tests/test_college_view_distribution.py` 擴充 + 新 `test_college_distribution_export.py`）：**

- **跨學院隔離必須在 export endpoint 本身驗證** — 用 openpyxl 讀回 workbook 逐列斷言，
  **不可**只掃描 response bytes（掃 bytes 會因壓縮/編碼而產生偽陰性）。
- 去重：同一學生存在於兩個 finalized rankings（一個 allocated、一個未 allocated）→ 匯出**只有一列**，且為 正取。
- 名次：未錄取列的 名次 有值；列順序決定性（同樣輸入跑兩次結果相同）。
- 新 403：無 `AdminScholarship` grant → 403；無該學年度 config → 403。
- `sanitize_excel_cell`：`std_cname` 為 `=WEBSERVICE(...)` → 匯出後被中和（對照
  `test_college_ranking_export_service.py:420` 的 `test_malicious_student_name_is_neutralized`）。
- PDF：CJK 姓名可渲染；含 `&`/`<` 的姓名經 `xml_escape` 不炸。
- 零列匯出：仍有表頭，不 raise。
- 既有 4 個測試維持通過（需修 fixture，見「行為變更」）。

**Lint gate（commit 前，CLAUDE.md）：**

```bash
uvx --from "black==26.3.1" black --check --line-length=120 backend/app
flake8 app --select=B904,B014 --max-line-length=120
```

## 行為變更（刻意）

1. **無 grant 的學院使用者：200 → 403。** 這是修正缺陷 1 的直接後果，也是 2026-06-30 spec 原本的意圖。
2. **admin 建立的全域 ranking（`college_code IS NULL`）上跑的分發：學院將看到「尚未分發」。**
   這與 `ranking_management.py:80` 既有行為一致（college 使用者在 `/rankings` 本來就看不到 NULL rankings），
   且 issue #1034 的結論是 rankings 本質上是 per-college。

### 既有測試 fixture 需修正

`test_college_view_distribution.py` 的 fixtures 目前不真實，修正後才會通過：

- `college_client_factory`（`:102-113`）建立的 college user **沒有 `AdminScholarship` grant row** → 需補。
- `_seed_distribution`（`:128-138`）建立的 `CollegeRanking` **沒有 `college_code`**（NULL）→ 需設為 `"A"`。

這是 fixture 缺口，不是跳過 gate 的理由。

## Out of scope

- 不改分發/finalize/造冊的權限（維持 admin-only）。
- 不改 PII 政策 — 學院仍看不到身分證/匯款帳號/金額。
- 不改 `allow_college_view_distribution` toggle 的粒度或 admin UI。
- 不動未使用的 `GET /college-review/rankings/{ranking_id}/distribution-details`。
- 不統一 codebase 中四種「我的學院」的判定方式（見下）。

## Risks / notes

- **四種「我的學院」判定並存**：SQL `json_extract_path_text(student_data,'std_academyno')`、
  Python `student_data.get("std_academyno")`、`get_college_code_from_data(sd)`（fallback chain
  `std_academyno → academy_code → college_code → std_college`）、`Department.academy_code`。
  本 endpoint 用第三種。後果：只帶 `academy_code` 而無 `std_academyno` 的快照，在 `/distribution-results`
  看得到、在 `/applications` 看不到。**這不是洩漏**（fallback 取到的仍是該學生自己的學院），
  但屬於已知的不一致，本次**明示接受**，不在此 PR 統一。
- **`get_academy_code_from_data`（`application_helpers.py:276`）與其註解自相矛盾**（註解說優先 `std_academyno`，
  程式卻優先 `trm_academyno`）。本設計不使用該函式，僅記錄。
- **測試容器 vs worktree**：dev container 掛載的是**別的 worktree**，
  `docker compose exec backend pytest` 會測到錯的程式碼。須在 host 以 inline env 跑（見 CLAUDE.md / worktree recipe）。
