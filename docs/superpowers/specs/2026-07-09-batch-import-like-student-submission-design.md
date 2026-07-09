# 批次匯入對齊學生自送申請流程 — 設計文件

日期：2026-07-09
分支：`claude/admin-batch-import-workflow-dig3m3`

## 背景與問題

批次匯入（`BatchImportService`）與學生自送（`ApplicationService.create_application` / `submit_application`）是兩條獨立實作的申請建立路徑，長期漂移導致匯入的申請與學生自送的申請行為不一致：

| 面向 | 學生自送 | 批次匯入（現況） |
|---|---|---|
| 初始狀態 | `submitted` + `review_stage=student_submitted` | 直接 `under_review`，無 `review_stage`、無 `status_name` |
| 教授指派 | 依 `UserProfile.advisor_nycu_id` 自動設 `professor_id` | 無 → 永遠進不了教授待審清單 |
| 資格驗證 | `EligibilityService`（含白名單）、子類別必填 | 幾乎沒有（只查重複） |
| `submitted_form_data` | 標準 `{fields, documents}` 結構 | 扁平 dict（postal_account、advisor_name…） |
| 郵局帳號/指導教授 | 存 `UserProfile` | 塞在 `submitted_form_data` |
| 金額/名稱 | `config.amount`、`config.config_name` | `amount=None`、`scholarship.name` |
| app_id | `APP-114-0-00001` | 加 `U` 後綴（保留此差異） |

目標：**批次匯入建立的申請要像學生自己送出一樣**——同一條審查流程、同一種資料結構、同一套欄位值。

## 已確認的需求決策

1. **審查流程一致**：匯入後 `status=submitted`、`review_stage=student_submitted`，走教授 → 學院完整審查流程。
2. **資料結構一致**：`submitted_form_data` 用標準 `{fields, documents}` 結構；郵局帳號、指導教授資訊寫入 `UserProfile`（**覆蓋**既有值；Excel 空白欄位保留原值）。
3. **驗證**：套用 eligibility/白名單/子類別檢查；**豁免申請期間**（補登情境）。eligibility/白名單不過**只列警告不擋**；子類別必填**硬擋**。
4. **金額/名稱對齊**：帶入 `config.amount`、`config.config_name or scholarship.name`。
5. **保留 app_id 的 `U` 後綴**（承辦人可一眼辨識來源）。
6. **子類別志願序改為系統推導**：Excel 子類別欄位任何正值標記＝有申請；順序比照學生端規則——`moe_1w` 有選就強制第一志願（`FORCED_FIRST_PREFERENCE`，見 `ScholarshipApplicationStep.tsx:120`），Excel 數字不再有排序意義。nstc/moe_1w 至少一個有標記，否則該列為硬錯誤。
7. **排除範圍**：不觸發 email 自動通知、不 clone 固定文件（存摺封面）、不遷移既有已匯入資料。

## 實作方案：抽出共用申請建構邏輯（方案 B）

不直接重用 `create_application`（與學生情境耦合過深：逐筆 commit、email、eligibility 硬擋），也不只在批次服務內改值（漂移會再發生）。改為把**會漂移的核心**抽成共用模組，兩條路徑共同呼叫。

### 新模組 `backend/app/services/application_builder.py`

只收「已證實漂移」的邏輯，不做投機性抽象：

1. **`generate_app_id(db, academic_year, semester, suffix="") -> str`**
   現有序號邏輯（`ApplicationSequence` + `FOR UPDATE` 鎖 + 格式化）搬入。學生路徑 `suffix=""`、批次路徑 `suffix="U"`。取代 `ApplicationService._generate_app_id` 與批次服務內整段複製的序號碼。
2. **`derive_sub_scholarship_type(subtype_list) -> str`** 與 **`validate_sub_type_for_submission(scholarship, sub_type)`**
   自 `ApplicationService` 的 staticmethod 搬入，call site 直接改引用。
3. **`build_submitted_application_values(scholarship, config) -> dict`**
   回傳提交狀態的共用欄位組：`status=submitted`、`status_name`（i18n）、`review_stage=student_submitted`、`submitted_at`、`amount=config.amount`、`scholarship_name=config.config_name or scholarship.name`。
4. **`assign_professor_from_profile(db, application, user) -> None`**
   自 `submit_application` 抽出：依 `UserProfile.advisor_nycu_id` 查 `role=professor` 的 User，設 `application.professor_id`；查無則留空。

`ApplicationService`（`_create_application_instance`、`submit_application`）與 `BatchImportService` 均改為呼叫上述 helpers。學生路徑屬純重構，行為不變。

### `BatchImportService.create_applications_from_batch` 變更

**Application 欄位**：
- `status`: `under_review` → `submitted`，補 `status_name`、`review_stage=student_submitted`（用 helper 3）
- `amount`、`scholarship_name`：改由 helper 3 帶入
- `app_id`：改用 helper 1（`suffix="U"`，行為不變）
- 子類別 scalar：改用 helper 2
- 不變：`imported_by_id`、`batch_import_id`、`import_source="batch_import"`、`document_status="pending_documents"`、`is_renewal`/`renewal_year`

**`submitted_form_data`**：扁平 dict → 標準結構，只裝 Excel 自訂欄位（對應 `application_fields` 定義，`field_type`/`required` 從定義帶入）：

```json
{
  "fields": {
    "contact_phone": {"field_id": "contact_phone", "field_type": "text", "value": "0912...", "required": true}
  },
  "documents": []
}
```

**UserProfile upsert**（每列，建申請前）：
- 郵局帳號 → `account_number`；指導教授三欄 → `advisor_name` / `advisor_email` / `advisor_nycu_id`
- Excel 有值 → 覆蓋既有 profile 值；Excel 空白 → 保留原值；無 profile → 新建
- 之後呼叫 helper 4 自動指派教授

**志願序解析**（`parse_excel_file`）：
- 子類別欄位（國科會/教育部…）標記判定：正整數（1、2…）或勾選字樣（V/v/✓）＝有申請；空白或 0 ＝未申請（數字不再解讀為排序）
- `sub_types` / `sub_type_preferences` 順序＝`moe_1w` 強制第一，其餘依欄位順序
- nstc/moe_1w 皆空白 → 該列硬錯誤（`missing_sub_type`）

### 預覽階段驗證（`upload-data` 與 `{batch_id}/validate` 兩入口）

在現有重複申請/學院歸屬檢查外新增：

1. **Eligibility（含白名單）→ 警告**：逐列抓 SIS snapshot，呼叫 `EligibilityService.check_student_eligibility`（與學生自送同一服務）。不過的列入 `validation_warnings`（`warning_type: "eligibility_failed"`，訊息帶原因），不擋匯入。
2. **子類別必填 → 硬錯誤**：見上；confirm 時有 error 的列被排除（沿用既有 `error_student_ids` 機制），全部有錯則整批擋下。
3. **教授帳號 → 警告**：有填指導教授人事編號但查無 `role=professor` 帳號 → 警告「查無教授帳號，該申請將無法進入教授待審清單」。
4. **申請期間：不檢查**。

### Confirm 階段

維持現狀：單一交易、意外錯誤全回滾（all-or-nothing）；警告純資訊性；eligibility 不重跑。

### 範本下載（`/template`）

說明與範例列改為「打勾（填 1 或 V）表示申請該類別」，移除 `8bc041d9` 引入的志願序數字示範。

## 前端變更（小）

- `batch-import-panel.tsx`：新警告型別沿用既有警告列表渲染，確認文案正常；志願序數字相關說明文字改為打勾語意
- 申請列表顯示「已提交」為既有 status 渲染，無需改碼
- 若 OpenAPI schema 有變 → `npm run api:generate` 並提交 `schema.d.ts`

## 測試計畫

**新增**：
- `application_builder` 單元測試：app_id suffix、`moe_1w` 強制第一志願推導、submitted 欄位組、教授自動指派（有/無教授帳號）
- UserProfile 覆蓋語意：有值覆蓋、空白保留、無 profile 新建
- 預覽 eligibility 警告、查無教授警告、子類別缺漏硬錯誤

**更新**：
- `test_batch_import_service_unit.py`、`test_batch_import_endpoints.py`、`test_batch_import_pure_helpers.py`、`test_batch_import_defaults_and_postal.py`：status 改 `submitted`、form_data 新結構、志願序推導
- 前端 `batch-import-panel.test.tsx`、e2e `batch-import-upload.spec.ts`

**回歸**：學生自送路徑抽 helper 屬純重構，既有 `application_service` 測試需全數通過且不改斷言。

依 repo 標準：async 測試進 integration lane；black + flake8（B904/B014）+ logger traceback AST invariant 全過。

## 錯誤處理

- SIS API 不可用：預覽照現行機制降級為警告（`student_api_unavailable`），eligibility 檢查跳過並註記
- UserProfile upsert 失敗：屬同一交易，隨批次回滾
- 教授查無帳號：不是錯誤，警告 + `professor_id=NULL`；學院/管理端仍可審（既有回退路徑）

## 不做的事

- 不發 `application_submitted` 自動信、不 clone 存摺封面
- 不做 DB migration（欄位皆既存）；舊匯入申請的扁平 `submitted_form_data` 不回填，讀取端 `_normalize_submitted_form_data` 已相容舊格式
