# 申請流程隱藏「已送出 / 無可申請」獎學金 — 設計文件

- **日期**: 2026-06-29
- **狀態**: 已核准（待寫實作計畫）；經三路對抗式審查修正
- **分支**: `worktree-hide-applied-scholarships`

## 背景與問題

學生端有三個顯示獎學金的介面：

1. **「獎學金列表」分頁** — 唯讀型錄，列出所有符合資格的獎學金（含資格/不符資格徽章）。
2. **「學生申請」分頁** — 若至少有一個可選獎學金即掛載申請精靈，否則顯示空狀態提示。
3. **申請精靈的獎學金下拉選單**（`ScholarshipApplicationStep`）— 學生實際挑選要申請的獎學金。

目前後端 `GET /api/v1/scholarships/eligible` 回傳「符合規則且在申請期間內」的獎學金，但**不會**排除學生已申請過的獎學金。結果：學生可以在申請精靈下拉選單選到一個已送出的獎學金，一路填到送出才被後端的 `DUPLICATE_APPLICATION` 守衛擋下（`applications.py`）。這是不好的體驗。

## 目標

- 在**申請流程**（學生申請分頁 + 精靈下拉選單）隱藏「已送出/處理中」的獎學金。
- 當沒有任何可申請的獎學金時，顯示清楚的提示訊息，並區分「皆已送出」與「不符資格」兩種情境。
- **核心不變式**：獎學金出現在申請流程 ⟺ 學生此刻能成功送出（新建或續填）。亦即「顯示 ⟹ 可送出」，與送出時的 `DUPLICATE_APPLICATION` 守衛保持一致，避免「看得到卻送不出」的矛盾。

## 非目標（Out of Scope）

- 不更動「獎學金列表」唯讀型錄 — 維持完整清單（之後若要在型錄上加狀態徽章，可沿用本次新增的後端欄位，但不在本次範圍）。
- 不改變送出守衛「擋哪些狀態」的實質行為（只把它的狀態集合抽成共用常數）。
- 不改變申請期間（application period）開關的既有行為。
- **Renewal / Challenge 申請卡**（`frontend/components/student/RenewalApplicationCard.tsx`、`ChallengeApplicationCard.tsx`）不在範圍：它們走獨立端點 `/api/v1/renewals/*`（非 `/scholarships/eligible`），且自身在伺服器端做名單收斂與前端在地去重，不需要本欄位。

## 已確認的決策

| # | 問題 | 決策 |
|---|------|------|
| 1 | 哪些申請狀態算「已送出」而要隱藏？ | **只隱藏已送出以上**：見下方〈狀態語意〉的 `HIDDEN_APPLICATION_STATUSES`。`draft`（草稿可續填）、`returned`（退回可修改）保留；`rejected` / `withdrawn` / `cancelled` / `deleted`（守衛允許重新申請）保留。 |
| 2 | 在哪些介面隱藏？ | **只在申請流程**（學生申請分頁 + 精靈下拉）。「獎學金列表」型錄維持完整。 |
| 3 | 可申請數為 0 時怎麼處理？ | **顯示提示訊息**（保留分頁），並**區分兩種訊息**：全部已送出 vs. 不符資格。 |

## 狀態語意（單一真相來源）

`ApplicationStatus` enum（`backend/app/models/enums.py`，共 **13** 個值）：
`draft`、`submitted`、`under_review`、`pending_documents`、`approved`、`partial_approved`、`rejected`、`returned`、`withdrawn`、`cancelled`、`manual_excluded`、`cancelled_by_challenge`、`deleted`。

送出守衛（`applications.py`）以「排除集合」定義可重新申請的狀態：`{withdrawn, rejected, cancelled, deleted}`（這些不擋、允許重新申請）。`deleted` 為軟刪除墓碑，與守衛排除集合一致，刻意視為「可重新申請」。

由此定義三組互斥語意（皆以 `.value` 字串表示，沿用既有 `REVIEWABLE_APPLICATION_STATUSES` 慣例）：

- **REAPPLY_ALLOWED_APPLICATION_STATUSES**（可重新申請，保留可見）：`{withdrawn, rejected, cancelled, deleted}`
- **EDITABLE_APPLICATION_STATUSES**（編輯中，保留可見）：`{draft, returned}`
- **HIDDEN_APPLICATION_STATUSES**（已送出/處理中，**隱藏**）= 全集 − 前兩者 = `{submitted, under_review, pending_documents, approved, partial_approved, manual_excluded, cancelled_by_challenge}`（7 個）

> **設計時不變式**：`HIDDEN = ALL − REAPPLY_ALLOWED − EDITABLE`。`HIDDEN` 恰好是「送出守衛會擋、且無法就地續填」的狀態 → 滿足「顯示 ⟹ 可送出」。`manual_excluded`、`cancelled_by_challenge` 守衛**不**排除（會擋重複申請），故歸入 `HIDDEN`（隱藏）；若產品要讓它們可重新申請，須一併修改守衛的排除集合（屬非目標，需另行決策）。
>
> **實作為顯式 allow-list**：程式以顯式的 `HIDDEN_APPLICATION_STATUSES` 常數判斷（非執行期取補集），對未來新增 enum 值是安全預設（新值預設「顯示」，並由 enum-pin tripwire 測試強制做出有意識的分類決策）。

## 採用方案

### 方案 A（採用）— 後端用專屬 `EXISTS` 查詢算出 `already_submitted`，前端據此過濾申請流程

後端針對每個獎學金設定，用一支專屬查詢判斷學生是否已有「隱藏集合」狀態的申請，回傳布林欄位 `already_submitted`。前端在申請流程過濾，而共用的 `/eligible` 請求仍可餵給完整型錄。單一真相來源、無客戶端重算、改動面最小。

> **與初版的差異（經審查修正）**：初版打算複用 `eligibility_service.get_application_status` 的單列輸出推導，但該函式 (a) 的 `active_statuses` 白名單**漏掉** `pending_documents`、`partial_approved` 等狀態，會讓兩個應隱藏的狀態查不到而漏隱藏；(b) 用 `scalar_one_or_none()` 在多列時會丟例外讓 `/eligible` 噴 500；(c) 取補集的公式缺 `has_application` 守衛會把「沒申請」誤判為隱藏，將整批未申請獎學金全部隱藏。改用專屬 `EXISTS` 查詢可一次避開三者。

### 方案 B（否決）— 純前端 join

前端同抓 `/eligible` 與 `/my-applications` 比對過濾。否決：把後端狀態/守衛規則在前端重做，型錄與精靈各自抓資料要寫兩處，易與後端權威規則漂移。

### 方案 C（否決）— 後端直接從 `/eligible` 移除已申請設定

否決：同支端點也餵給「獎學金列表」型錄，移除會讓型錄也空掉（或被迫加第二種端點模式），與決策 #2 衝突。

## 詳細設計

### 後端

1. **共用狀態常數** — 在 `backend/app/models/enums.py` 新增三個 `.value` 字串清單（緊鄰既有 `REVIEWABLE_APPLICATION_STATUSES`，沿用同風格）：`REAPPLY_ALLOWED_APPLICATION_STATUSES`、`EDITABLE_APPLICATION_STATUSES`、`HIDDEN_APPLICATION_STATUSES`，並以註解寫明上方不變式。

2. **重複申請守衛改用共用常數（DRY）** — `applications.py` 的 `excluded_statuses` 改用 `REAPPLY_ALLOWED_APPLICATION_STATUSES`。
   - 注意：守衛現用 enum **members** 搭 `.notin_()`；改用 `.value` 字串。同檔 `get_application_status` 的 `active_statuses`（`.value` 字串）已用 `.in_()` 成功比對同一 enum 欄位，故 `.notin_()` 搭 `.value` 字串同樣可行（`ApplicationStatus` 以 `values_callable` 存值）。實作時以一筆既有重複申請測試驗證行為不變。

3. **新增 `has_blocking_application(user_id, config) -> bool`**（置於 `eligibility_service` 或 `scholarship_service`）：對 `(user_id, scholarship_type_id, academic_year, semester)` 且 `status IN HIDDEN_APPLICATION_STATUSES` 做 `EXISTS`/`select(...).limit(1)` 查詢。
   - 確定性、無 `None` 邊界、無多列例外（不需排序、不需 `scalar_one_or_none`）。
   - **semester 比較須與守衛一致**：守衛用 `Application.semester == config.semester`（enum 物件，`None` 時比 `IS NULL`）。本查詢**完全沿用守衛的比較方式**（非 `get_application_status` 的 `config.semester.name` 寫法），確保 `already_submitted` 與守衛選到同一批列 → 維持「顯示 ⟹ 可送出」不變式。建議抽一個共用 semester 述詞 helper 供兩處共用。

4. **產生 `already_submitted`** — 在 `ScholarshipService.get_eligible_scholarships`（目前 `:155` 呼叫 `get_application_status`、`:224-238` attach 狀態欄位處）：以 `already_submitted = await ...has_blocking_application(user_id, config)` 取代原本被回應層丟棄的狀態欄位。移除 `scholarship_dict` 內那些被丟棄的欄位（`can_apply`/`status_display`/`application_status`/`has_application`/`application_id`），只保留 `already_submitted`。
   - 連帶結果：`/eligible` 路徑**不再呼叫** `get_application_status`，原本多列 `scalar_one_or_none()` 的 500 風險在此路徑消失（符合先前同意的「修掉當機」目標）。`get_application_status` 屆時只剩自身單元測試引用；本次**保留不動**（其 `active_statuses`/`scalar_one_or_none` 屬已知潛在問題，已不在關鍵路徑，徹底移除/修正列為後續）。

5. **暴露欄位** — 在 `EligibleScholarshipResponse`（`backend/app/schemas/scholarship.py:259-286`）新增 `already_submitted: bool = False`（給預設值，對舊/缺值 payload 具韌性，並與前端 optional 欄位對稱）；於端點建構處（`backend/app/api/v1/endpoints/scholarships.py:225-253`）帶出。

> 註：回應維持 ApiResponse 包裝格式（`{success, message, data}`），不引入 `response_model`。新增為單一構造點（`scholarships.py:225`），admin/college 不使用 `EligibleScholarshipResponse`，無其他後端消費者受影響。

### 前端

6. **型別** — 在 `frontend/lib/api/types.ts` 的 `ScholarshipType`（`:210` 一帶）新增 `already_submitted?: boolean`；依 CLAUDE.md §8 於後端執行中跑 `cd frontend && npm run api:generate` 並提交 `lib/api/generated/schema.d.ts`。

7. **共用判斷式** — 在 `frontend/lib/scholarship-eligibility.ts` 新增：

   ```ts
   export function isApplyableScholarship(scholarship: ScholarshipType): boolean {
     return isSelectableScholarship(scholarship) && !scholarship.already_submitted;
   }
   ```

8. **精靈下拉選單** — `frontend/components/student-wizard/steps/ScholarshipApplicationStep.tsx:744` 由 `filter(isSelectableScholarship)` 改為 `filter(isApplyableScholarship)`。
   - 編輯既有草稿/退回件不受影響：`draft`/`returned` 的 `already_submitted` 皆為 `false`，仍在清單中（`editingApplication` 由 code 在清單中尋得，`:621`）。

9. **入口「學生申請」分頁** — `frontend/components/enhanced-student-portal.tsx`：
   - 掛載精靈的條件位於 **`:1338`**：`editingApplication || eligibleScholarships.some(isSelectableScholarship)`。**只把 `.some(...)` 子句**改為 `isApplyableScholarship`，保留 `editingApplication ||` 守衛不動。
   - 空狀態訊息**區分兩種**（純前端推導）：
     - `hasAnySelectable = eligibleScholarships.some(isSelectableScholarship)`、`hasAnyApplyable = eligibleScholarships.some(isApplyableScholarship)`。
     - 當 `!hasAnyApplyable && hasAnySelectable` → 顯示新訊息「您可申請的獎學金皆已送出，請至『我的申請』查看進度」。
     - 否則 → 沿用現有 `messages.no_eligible_scholarships`。

10. **i18n** — 字串實際位於 `frontend/lib/i18n.ts`（**非** portal 元件）。新增 key（例如 `messages.all_eligible_already_submitted`，zh + desc）於 **zh 樹（~`:338`）與 en 樹（~`:853`）兩處**；`frontend/lib/__tests__/i18n.test.ts` 會驗 zh/en 對等，務必兩邊都加。「不符資格」分支沿用既有 `messages.no_eligible_scholarships`。

11. **「獎學金列表」型錄分頁** — 不變，維持完整清單。

## 資料流

```
GET /api/v1/scholarships/eligible
  → ScholarshipService.get_eligible_scholarships
      → has_blocking_application(user_id, config):
          EXISTS Application WHERE user_id, scholarship_type_id, academic_year,
                 semester(同守衛比較), status IN HIDDEN_APPLICATION_STATUSES
      → already_submitted = <該 EXISTS 結果>
  → EligibleScholarshipResponse { ..., already_submitted: bool = False }
  → 前端
      ├─ 獎學金列表型錄：用完整清單（不過濾）
      └─ 申請流程（分頁掛載條件 + 精靈下拉）：filter(isApplyableScholarship)
```

## 邊界情況

- **沒有任何申請（常見情況）**：`EXISTS` 為偽 → `already_submitted = False` → 顯示。（專屬查詢天然處理，無 `None` 反轉風險。）
- **多年度設定共用同一 type code（114 + 115）**：查詢以 `academic_year` + `semester` 為鍵，逐設定計算，申請 114 不會隱藏 115。與精靈以 `configuration_id` 為選取鍵一致。
- **同一設定多列（被拒/撤回 + 新草稿）**：`EXISTS(隱藏集合)` 與排序無關 → 終態（被拒/撤回）不屬隱藏集合、草稿也不屬 → `already_submitted = False` → 顯示，可重新申請/續填。同時天然避開 `scalar_one_or_none` 多列例外。
- **續填草稿 / 修改退回件**：`draft`、`returned` 不在隱藏集合，仍顯示，可由「我的申請」進編輯流程（`editingApplication`）續填。
- **`returned` 在全新精靈直接新建**：因 `returned` 保留可見（決策 #1），若學生不走編輯而在全新精靈選它並按新建，仍會撞既有守衛（守衛只對 `draft` 回傳既有件續填，`returned` 會回 `DUPLICATE_APPLICATION`）。此為既有守衛行為、屬非目標；正常路徑是由「我的申請」編輯退回件。記錄為已知限制。
- **`manual_excluded` / `cancelled_by_challenge`**：屬隱藏集合 → 不顯示（與守衛一致，避免顯示後送出撞 `DUPLICATE_APPLICATION`）。

## 測試

- **後端（async / integration suite）**：
  - `has_blocking_application` / `already_submitted` 真值表：`submitted`、`under_review`、`pending_documents`、`approved`、`partial_approved`、`manual_excluded`、`cancelled_by_challenge` → `True`；`draft`、`returned`、`rejected`、`withdrawn`、`cancelled`、`deleted`、**無申請** → `False`。（明確涵蓋 `manual_excluded`/`cancelled_by_challenge`，把分類釘住，未來新增 enum 值會強制重新分類。）
  - 多列情境：（被拒 + 新草稿）→ `False` 且不丟例外。
  - 守衛重構回歸：一筆既有「重複申請被擋」案例行為不變。
  - 新查詢需自備測試 stub（支援 `EXISTS`/`limit(1)` 形狀）；不沿用 `get_application_status` 的 stub。
- **前端（unit）**：`isApplyableScholarship` 真值表（`already_submitted` × `isSelectableScholarship` 組合）。
- **前端（E2E，選配）**：學生已送出某獎學金 → 精靈下拉看不到該獎學金，但「獎學金列表」型錄仍看得到。

## 發佈注意事項

- 後端執行中時跑 `cd frontend && npm run api:generate`，提交 `lib/api/generated/schema.d.ts`（CI 驗型別同步）。
- 後端 lint 硬性門檻：`black --check --line-length=120`、`flake8 --select=B904,B014`，touched 檔案跑對應 pytest。
- enum-pin tripwire（`test_shared_enums_value_contract.py`）：本次**不改 enum 值**（只加 module 常數），不應觸發；新查詢的真值表即作為分類契約。

## 開放問題

- `manual_excluded` / `cancelled_by_challenge` 採「隱藏（不可重新申請）」分類，與送出守衛一致。若產品實際希望這兩種可重新申請，需另案修改守衛排除集合（非目標）。其餘決策 #1–#3 與兩個附帶小修正皆已確認。
