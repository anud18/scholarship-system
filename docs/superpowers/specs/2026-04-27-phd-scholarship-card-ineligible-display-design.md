# PhD 獎學金卡片：不合格子類型顯示與學籍資料補充 Design Spec

**Date**: 2026-04-27
**Scope**: Frontend (主要) + 後端 schema 擴充（兩個欄位） — `enhanced-student-portal.tsx`, `StudentDataReviewStep.tsx`, `i18n.ts`, `schemas/scholarship.py`, `endpoints/scholarships.py`

---

## Background

兩個調查案例觸發此次設計：

1. **csphd0002**（博士四年級，`trm_termcount=7`）反映「看不到教育部獎學金」。調查發現 MOE 規則 `trm_termcount in (1,2,3,4,5,6)` 失敗，`moe_1w` 子類型在 `_filter_eligible_subtypes` 被過濾出回傳資料。
2. **414708008**（已歸化僑生/外籍生，`std_identity in (3,4)` 但 `std_nation ≠ "中華民國"`）同樣看不到教育部獎學金，根因是 MOE 規則 `std_nation == "中華民國"` 失敗。

這兩個案例的後端規則行為**符合既定政策**，不修改：
- MOE 限本國籍 + 限一至三年級 → 政策本意
- 頂層 `std_identity != 17` → 排除陸生

但 UX 上學生只看到部分子類型卻不知道為何缺漏，造成困惑。本 spec 處理 UX 缺口。

---

## Goals

1. 學生在獎學金瀏覽卡片可清楚看到該獎學金的**所有子類型**，不合格的灰掉並列出失敗原因。
2. 學生在「確認學籍資料」步驟可看到自己的 `std_nation`（國籍）與 `std_identity`（身分），方便理解為何某些子類型不合格、也方便日後跟承辦人溝通。

---

## Non-Goals

- ❌ 不修改任何 `scholarship_rules`（rule 4 / 5 / 7 / 18 全部不動）
- ❌ 不修改 i18n `eligibility_tags` 中「中華民國國籍」display
- ❌ 不修改 eligibility/篩選**業務邏輯**（service 層完全不動）
- ❌ 不修改申請流程的子類型選擇器（仍只能勾選 eligible 子類型）

> **Scope expanded during implementation:** the original spec scoped only Block 1, but the user reviewed the partial result and asked for Block 2「申請資格」 to also iterate all subtypes (greyed title + 「（不符資格）」 hint for ineligible, with the same passed/error tag groupings). The implementation reflects this expanded scope.

---

## Backend Data Plumbing Gap

`ScholarshipService.get_eligible_scholarships()`（`backend/app/services/scholarship_service.py:182-188`）已經組好：
- `all_sub_type_list`：來自 `scholarship_type.sub_type_list`（資料庫欄位，目前 phd = `["nstc", "moe_1w"]`）
- `subtype_eligibility`：每個子類型的 `{ eligible, failed_rules, warning_rules }`

但 **`EligibleScholarshipResponse` schema（`backend/app/schemas/scholarship.py:247-272`）沒有對應欄位**，endpoint（`backend/app/api/v1/endpoints/scholarships.py:219-244`）也沒有 pass through，所以這些資料**從未送到前端**。

本 spec 要在 schema + endpoint 補上這兩個欄位，service 層完全不動。

---

## Backend Changes

### Change 0a — Schema 新增兩個欄位

**File**: `backend/app/schemas/scholarship.py`
**Class**: `EligibleScholarshipResponse`（line 247）

新增：
```python
class SubtypeRuleDetail(BaseModel):
    rule_name: str
    message: str
    tag: str

class SubtypeEligibilityInfo(BaseModel):
    eligible: bool
    failed_rules: List[SubtypeRuleDetail] = []
    warning_rules: List[SubtypeRuleDetail] = []

class EligibleScholarshipResponse(BaseModel):
    # ... 既有欄位不動 ...
    all_sub_type_list: List[str] = []
    subtype_eligibility: Dict[str, SubtypeEligibilityInfo] = {}
```

### Change 0b — Endpoint pass through 兩個欄位

**File**: `backend/app/api/v1/endpoints/scholarships.py`
**Function**: `get_scholarship_eligibility`（line 219-244 處組裝 `EligibleScholarshipResponse`）

新增兩行：
```python
response_item = EligibleScholarshipResponse(
    # ... 既有欄位 ...
    all_sub_type_list=scholarship.get("all_sub_type_list", []),
    subtype_eligibility=scholarship.get("subtype_eligibility", {}),
    # ...
)
```

Service 層的 `get_eligible_scholarships()` 已具備這些資料（line 184-186），不需要動。

### OpenAPI 型別 re-generate

```bash
cd frontend && npm run api:generate
git add lib/api/generated/schema.d.ts
```
（後端必須跑在 `localhost:8000`）

---

## Frontend Changes

### Change 1 — Card Block 1「可申請項目」改成顯示所有子類型

**File**: `frontend/components/enhanced-student-portal.tsx`
**Region**: 約 line 1328-1358，渲染 `eligible_programs` badge 列表的區塊。

**改動前**：
```tsx
{scholarship.eligible_sub_types.map(subType => (
  <Badge variant="outline" className="bg-white text-indigo-600 border-indigo-100">
    {locale === "zh" ? subType.label : subType.label_en}
  </Badge>
))}
```
顯示僅 eligible 子類型，藍色 chip。

**改動後**（pseudocode）：
```tsx
{scholarship.all_sub_type_list?.map(subTypeKey => {
  const eligibilityInfo = scholarship.subtype_eligibility?.[subTypeKey];
  const isEligible = eligibilityInfo?.eligible !== false;
  const label = getTranslation(locale, `rule_types.${subTypeKey}`) || subTypeKey;

  if (isEligible) {
    return (
      <Badge variant="outline" className="bg-white text-indigo-600 border-indigo-100">
        ✓ {label}
      </Badge>
    );
  }

  const failedTagLabels = (eligibilityInfo?.failed_rules ?? [])
    .map(r => getTranslation(locale, `eligibility_tags.${r.tag}`))
    .filter(Boolean);
  const reasonText = failedTagLabels.length > 0
    ? `不符：${failedTagLabels.join("、")}`
    : "不符資格";

  return (
    <Badge variant="outline" className="bg-gray-100 text-gray-400 border-gray-200">
      ✗ {label} — {reasonText}
    </Badge>
  );
})}
```

**範例輸出（414708008，僑/外籍生）**：
```
[ ✓ 國科會博士生獎學金 ]   [ ✗ 教育部博士生獎學金 (指導教授配合款一萬) — 不符：中華民國國籍 ]
```

**範例輸出（csphd0002，博四）**：
```
[ ✓ 國科會博士生獎學金 ]   [ ✗ 教育部博士生獎學金 (指導教授配合款一萬) — 不符：三年級以下 ]
```

**Edge cases**:
- `all_sub_type_list` 為空或只含 `general` / `null`：照舊不顯示此區（沿用原 line 1331-1332 的判斷邏輯）。
- `subtype_eligibility[key]` 不存在：視為 eligible，僅顯示綠色 chip（防禦性 fallback）。
- `failed_rules` 全部 tag 找不到 i18n 翻譯：fallback 顯示「不符資格」（無細節）。

### Change 2 — i18n `rule_types` 改成完整 label

**File**: `frontend/lib/i18n.ts`
**Region**: line 251-255 (zh) 與 line 591-595 (en)

**改動前（zh）**：
```ts
rule_types: {
  nstc: "國科會",
  moe_1w: "教育部(1萬)",
  moe_2w: "教育部(2萬)",
}
```

**改動後（zh）**：
```ts
rule_types: {
  nstc: "國科會博士生獎學金",
  moe_1w: "教育部博士生獎學金 (指導教授配合款一萬)",
  moe_2w: "教育部博士生獎學金 (指導教授配合款兩萬)",
}
```

**改動後（en）**（待最終確認文字）：
```ts
rule_types: {
  nstc: "NSTC PhD Scholarship",
  moe_1w: "MOE PhD Scholarship (Advisor Matching Fund - 10K)",
  moe_2w: "MOE PhD Scholarship (Advisor Matching Fund - 20K)",
}
```

**注意**：原本 `rule_types` 是否在其他地方被引用？需要在實作前 grep 確認沒有其他地方依賴短名稱（例如管理後台）。

### Change 3 — 確認學籍資料新增「國籍」與「身分」

**File**: `frontend/components/student-wizard/steps/StudentDataReviewStep.tsx`

**Region**: 約 line 285-352 的 academic info card。目前 grid 渲染 4 個欄位（學位 / 在學狀態 / 入學年度學期 / 學期數）。

**改動**：

a. 在現有的 `degreeMap` / `studyingStatusMap` 旁新增 `identityMap`：

```ts
const identityMap: Record<string, string> = {
  "1":  "一般生",
  "2":  "原住民",
  "3":  "僑生(目前有中華民國國籍生)",
  "4":  "外籍生(目前有中華民國國籍生)",
  "5":  "外交子女",
  "6":  "身心障礙生",
  "7":  "運動成績優良甄試學生",
  "8":  "離島",
  "9":  "退伍軍人",
  "10": "一般公費生",
  "11": "原住民公費生",
  "12": "離島公費生",
  "13": "退伍軍人公費生",
  "14": "願景計畫生",
  "17": "陸生",
  "30": "其他",
};
```
資料來源：`backend/alembic/versions/6d5b1940bf8a_seed_reference_tables_degrees_.py:101-118`。

b. `text` 物件新增兩個 label：

```ts
zh: {
  ...
  nationality: "國籍",
  identity:    "身分",
},
en: {
  ...
  nationality: "Nationality",
  identity:    "Identity",
},
```

c. 在 academic info card 的 grid 新增兩個欄位（沿用既有 grid item 的 markup 樣式）：

```tsx
{/* Nationality */}
<div className="space-y-2">
  <label className="text-sm font-medium text-gray-600">{text.nationality}</label>
  <div className="text-base text-gray-700">
    {studentInfo.std_nation || "-"}
  </div>
</div>

{/* Identity */}
<div className="space-y-2">
  <label className="text-sm font-medium text-gray-600">{text.identity}</label>
  <div className="text-base text-gray-700">
    {studentInfo.std_identity
      ? identityMap[String(studentInfo.std_identity)] || studentInfo.std_identity
      : "-"}
  </div>
</div>
```

身分顯示**只取名稱不顯示代碼**（例如顯示「僑生(目前有中華民國國籍生)」，不顯示「3：僑生(目前有中華民國國籍生)」）。

---

## Testing Plan

### Manual Testing

| Case | Pre-condition | Expected |
|---|---|---|
| 1. 一般本國生（std_identity=1, std_nation=中華民國, trm_termcount≤6, 博士） | 符合 nstc + moe_1w | 兩個藍色 chip，無灰色 chip |
| 2. 414708008（僑/外籍生 std_identity=3 or 4, std_nation≠中華民國, 博士） | nstc 合格，moe_1w 不合格 | nstc 藍色，moe_1w 灰色「— 不符：中華民國國籍」|
| 3. csphd0002（本國博四 trm_termcount=7） | nstc 合格，moe_1w 不合格 | nstc 藍色，moe_1w 灰色「— 不符：三年級以下」|
| 4. 雙重失敗（假設外籍博四） | nstc 合格，moe_1w 兩條 fail | moe_1w 灰色「— 不符：中華民國國籍、三年級以下」|
| 5. 確認學籍資料 | 任一登入學生 | 學籍資訊 card 顯示 6 個欄位含國籍與身分名稱 |

### Build / Type Checks

```bash
# 1. Re-generate OpenAPI types after backend schema change
cd frontend && npm run api:generate

# 2. Frontend lint + build
npm run lint && npm run build

# 3. Backend lint
cd ../backend && python -m black app/schemas/scholarship.py app/api/v1/endpoints/scholarships.py && python -m flake8 app/schemas/scholarship.py app/api/v1/endpoints/scholarships.py
```

不需要新單元測試 — 純 UI / data presentation 改動，沒有新邏輯分支需測。但需確認既有測試不會因為新增 schema 欄位而失敗。

### Regression

**重點檢查**：
- 既有「申請資格」(Block 2) 區塊行為不變
- 申請流程的子類型選擇器仍只能選 eligible 子類型
- 沒有子類型的獎學金（general scholarship）卡片不顯示「可申請項目」區塊（行為不變）

---

## Risks / Open Items

1. **i18n key 同步**：`rule_types` map 從短名稱改長，需 grep 全 codebase 確認沒有其他地方期望短名稱（admin 介面、ranking 頁面、distribution 介面）。
2. **`all_sub_type_list` 來源**：service 層 `scholarship_service.py:185` 從 `scholarship_type.sub_type_list` 取（資料表欄位）。目前 phd 的 `sub_type_list = ["nstc", "moe_1w"]`，學生不會看到 `moe_2w` 的 chip。若未來 admin 啟用 `moe_2w` 需先把它加進 `scholarship_types.sub_type_list`，這對本 spec 沒有影響。
3. **`failed_rules[].tag` 可能缺翻譯**：若新增規則時忘了同步 i18n，chip 會顯示「不符：（空）」。實作中應有 fallback「不符資格」。
4. **OpenAPI types 同步**：若 `frontend/lib/api/generated/schema.d.ts` 缺 `subtype_eligibility` 或 `all_sub_type_list`，需 re-run `npm run api:generate`（CI 也會驗證）。

---

## Out of Scope (Future Considerations)

- 申請流程的子類型選擇器同步顯示灰掉的不合格子類型（更一致的 UX，但複雜度較高）
- Block 2「申請資格」也顯示不合格子類型的完整 tag 群組（資訊更完整但版面可能過長）
- Rule 18 tag「中華民國國籍」改寫成「僑生/外籍生」或類似（需要先處理 rule 5/7 共用 tag 問題）
- MOE 國籍規則改用 std_identity 判斷而非 std_nation 字串（需要釐清 SIS 資料一致性政策）
