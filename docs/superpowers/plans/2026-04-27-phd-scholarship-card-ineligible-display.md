# PhD 獎學金卡片不合格子類型顯示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓學生在獎學金瀏覽卡片看到所有子類型（不合格的灰掉並列出失敗原因），並在「確認學籍資料」步驟顯示國籍與身分。

**Architecture:** 後端 service 層已備齊資料但 schema 沒 expose；只在 schema 加兩個欄位、endpoint pass through，前端拿到後改寫 chip 渲染。前端另外新增兩個學籍欄位 + 更新 i18n label。

**Tech Stack:** FastAPI / Pydantic v2（後端）, Next.js / React / TypeScript / Tailwind（前端）, Docker compose dev stack。

**Spec:** `docs/superpowers/specs/2026-04-27-phd-scholarship-card-ineligible-display-design.md`

---

## File Structure

| File | Change Type | Responsibility |
|---|---|---|
| `backend/app/schemas/scholarship.py` | Modify | 新增兩個 helper schema + 在 `EligibleScholarshipResponse` 加兩個欄位 |
| `backend/app/api/v1/endpoints/scholarships.py` | Modify | `get_scholarship_eligibility` 在組裝 response 時 pass through 兩個新欄位 |
| `frontend/lib/api/generated/schema.d.ts` | Auto-regen | OpenAPI 型別同步 |
| `frontend/lib/i18n.ts` | Modify | 更新 `rule_types` 為完整名稱、新增 `nationality` / `identity` 字串 |
| `frontend/components/enhanced-student-portal.tsx` | Modify | 卡片 Block 1 改用 `all_sub_type_list` + `subtype_eligibility` 渲染所有子類型 |
| `frontend/components/student-wizard/steps/StudentDataReviewStep.tsx` | Modify | 新增 `identityMap` + 兩個 grid 欄位 |

無新檔案，全部是既有檔案修改。

---

## Task 1: Backend Pydantic helper schemas

**Files:**
- Modify: `backend/app/schemas/scholarship.py`（在 `EligibleScholarshipResponse` 之前/之後新增 helper class，並更新 `EligibleScholarshipResponse` 本身）

- [ ] **Step 1: Read current schema**

```bash
sed -n '230,275p' backend/app/schemas/scholarship.py
```
Confirm `EligibleScholarshipResponse` is at line 247 with no `all_sub_type_list` / `subtype_eligibility`. Also confirm `Dict` is already imported.

- [ ] **Step 2: Verify Dict import**

```bash
grep -n "^from typing" backend/app/schemas/scholarship.py
```
If `Dict` not imported, add it to the typing import.

- [ ] **Step 3: Add SubtypeRuleDetail and SubtypeEligibilityInfo classes**

Insert immediately above `class EligibleScholarshipResponse(BaseModel):`:

```python
class SubtypeRuleDetail(BaseModel):
    rule_name: str
    message: Optional[str] = None
    tag: Optional[str] = None


class SubtypeEligibilityInfo(BaseModel):
    eligible: bool
    failed_rules: List[SubtypeRuleDetail] = []
    warning_rules: List[SubtypeRuleDetail] = []
```

`Optional` for `message` / `tag` because rule data may have null fields.

- [ ] **Step 4: Add two fields to EligibleScholarshipResponse**

In the existing `EligibleScholarshipResponse` class (line 247-272), add immediately before `model_config = ConfigDict(from_attributes=True)`:

```python
    all_sub_type_list: List[str] = []
    subtype_eligibility: Dict[str, SubtypeEligibilityInfo] = {}
```

- [ ] **Step 5: Format + lint**

```bash
docker compose -f docker-compose.dev.yml exec backend python -m black app/schemas/scholarship.py
docker compose -f docker-compose.dev.yml exec backend python -m flake8 app/schemas/scholarship.py
```

Expected: black reformats nothing meaningful; flake8 shows 0 errors (or only pre-existing ones unrelated to our edits).

- [ ] **Step 6: Verify backend reloads cleanly**

```bash
docker compose -f docker-compose.dev.yml logs backend --tail 30
```

Expected: no Pydantic validation errors. If hot-reload is on, just look for the auto-reload line.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/scholarship.py
git commit -m "feat(schema): add subtype eligibility fields to EligibleScholarshipResponse

Adds SubtypeRuleDetail / SubtypeEligibilityInfo helper classes and exposes
all_sub_type_list and subtype_eligibility on the eligible scholarships
response so the frontend can render ineligible subtypes greyed out with
their failed rule tags."
```

---

## Task 2: Endpoint pass through

**Files:**
- Modify: `backend/app/api/v1/endpoints/scholarships.py`（在 `get_scholarship_eligibility` 內 line 219-244 區段新增兩行）

- [ ] **Step 1: Locate the assignment**

```bash
sed -n '219,245p' backend/app/api/v1/endpoints/scholarships.py
```
Confirm the `EligibleScholarshipResponse(...)` call constructs the response item.

- [ ] **Step 2: Add two new keyword args**

In the `EligibleScholarshipResponse(...)` call, immediately after `eligible_sub_types=sub_type_list,` add:

```python
            all_sub_type_list=scholarship.get("all_sub_type_list", []),
            subtype_eligibility=scholarship.get("subtype_eligibility", {}),
```

(Indentation must match the existing 12-space indent inside the call.)

- [ ] **Step 3: Format + lint**

```bash
docker compose -f docker-compose.dev.yml exec backend python -m black app/api/v1/endpoints/scholarships.py
docker compose -f docker-compose.dev.yml exec backend python -m flake8 app/api/v1/endpoints/scholarships.py
```

Expected: 0 new lint errors.

- [ ] **Step 4: Live API check via curl**

Get a student token first (login as `csphd0002` or any test student via the dev login flow) and:

```bash
curl -s -H "Authorization: Bearer <token>" http://localhost:8000/api/v1/scholarships/eligible \
  | python3 -c "import sys, json; d=json.load(sys.stdin); s=d['data'][0]; print('all_sub_type_list:', s.get('all_sub_type_list')); print('subtype_eligibility keys:', list((s.get('subtype_eligibility') or {}).keys()))"
```

Expected output (for csphd0002):
```
all_sub_type_list: ['nstc', 'moe_1w']
subtype_eligibility keys: ['nstc', 'moe_1w']
```

If empty / null, recheck Task 1 + Task 2 before continuing.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/endpoints/scholarships.py
git commit -m "feat(api): pass all_sub_type_list and subtype_eligibility to client

Wire the two service-layer fields into the EligibleScholarshipResponse
construction so the eligible scholarships endpoint exposes them. Service
logic untouched."
```

---

## Task 3: Re-generate frontend OpenAPI types

**Files:**
- Auto-regen: `frontend/lib/api/generated/schema.d.ts`

- [ ] **Step 1: Verify backend up on :8000**

```bash
curl -fsS http://localhost:8000/openapi.json > /dev/null && echo "OK"
```

- [ ] **Step 2: Run codegen**

```bash
cd frontend && npm run api:generate
cd ..
```

- [ ] **Step 3: Confirm new types appear**

```bash
grep -n "all_sub_type_list\|subtype_eligibility\|SubtypeEligibilityInfo" frontend/lib/api/generated/schema.d.ts | head -10
```

Expected: at least 4-6 matches showing the new fields and helper types in the generated schema.

- [ ] **Step 4: Commit generated types**

```bash
git add frontend/lib/api/generated/schema.d.ts
git commit -m "chore(types): regenerate OpenAPI schema for subtype eligibility fields"
```

---

## Task 4: Update i18n labels

**Files:**
- Modify: `frontend/lib/i18n.ts` (zh block ~line 251 and en block ~line 591; also `text` objects for student wizard if shared)

- [ ] **Step 1: Verify current `rule_types` location**

```bash
grep -n "rule_types:" frontend/lib/i18n.ts
```

Expected output: two lines (zh ~251, en ~591).

- [ ] **Step 2: Replace zh `rule_types` map (line ~251-255)**

Use Edit tool. Old:
```ts
    rule_types: {
      nstc: "國科會",
      moe_1w: "教育部(1萬)",
      moe_2w: "教育部(2萬)",
    },
```
New:
```ts
    rule_types: {
      nstc: "國科會博士生獎學金",
      moe_1w: "教育部博士生獎學金 (指導教授配合款一萬)",
      moe_2w: "教育部博士生獎學金 (指導教授配合款兩萬)",
    },
```

- [ ] **Step 3: Replace en `rule_types` map (line ~591-595)**

Use Edit tool. Old (verified at line 591-595):
```ts
    rule_types: {
      nstc: "NSTC",
      moe_1w: "MOE (10K)",
      moe_2w: "MOE (20K)",
    },
```

New:
```ts
    rule_types: {
      nstc: "NSTC PhD Scholarship",
      moe_1w: "MOE PhD Scholarship (Advisor Matching Fund - 10K)",
      moe_2w: "MOE PhD Scholarship (Advisor Matching Fund - 20K)",
    },
```

- [ ] **Step 4: Verify no other references to short names**

```bash
grep -rn "國科會\b\|教育部(1萬)\|教育部(2萬)\|MOE (10K)\|MOE (20K)" frontend/components frontend/app 2>/dev/null
```

Expected: 0 hits (or only inside admin-configuration-management.tsx as plain placeholder strings inside JSX text — those are display-only literals, leave them).

If grep shows any actual `getTranslation` lookups depending on the old short names, surface them now and decide how to handle.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/i18n.ts
git commit -m "feat(i18n): expand rule_types labels to full subtype names

Updates nstc / moe_1w / moe_2w display strings (zh + en) so the
scholarship card chips render full names like '國科會博士生獎學金'
instead of the previous short form."
```

---

## Task 5: Card Block 1 — render all subtypes with eligibility state

**Files:**
- Modify: `frontend/components/enhanced-student-portal.tsx`（line ~1328-1358，「Eligible Programs Section」區塊）

- [ ] **Step 1: Read current block**

```bash
sed -n '1325,1360p' frontend/components/enhanced-student-portal.tsx
```

Note the JSX structure: `{isEligible && scholarship.eligible_sub_types && ... map(...)}`.

- [ ] **Step 2: Replace the inner `.map(...)` with all-subtypes rendering**

Use Edit tool. Old (the entire `<div className="px-3 py-2 flex flex-wrap gap-1.5">` block):

```tsx
                        <div className="px-3 py-2 flex flex-wrap gap-1.5">
                          {scholarship.eligible_sub_types.map(
                            (subType, index) => (
                              <Badge
                                key={subType.value || index}
                                variant="outline"
                                className="bg-white text-indigo-600 border-indigo-100 shadow-sm"
                              >
                                {locale === "zh"
                                  ? subType.label
                                  : subType.label_en}
                              </Badge>
                            )
                          )}
                        </div>
```

New:

```tsx
                        <div className="px-3 py-2 flex flex-wrap gap-1.5">
                          {(scholarship.all_sub_type_list ?? []).map(
                            subTypeKey => {
                              const eligibility =
                                scholarship.subtype_eligibility?.[subTypeKey];
                              const isSubEligible =
                                eligibility?.eligible !== false;
                              const label =
                                getTranslation(
                                  locale,
                                  `rule_types.${subTypeKey}`
                                ) || subTypeKey;

                              if (isSubEligible) {
                                return (
                                  <Badge
                                    key={subTypeKey}
                                    variant="outline"
                                    className="bg-white text-indigo-600 border-indigo-100 shadow-sm"
                                  >
                                    ✓ {label}
                                  </Badge>
                                );
                              }

                              const failedTagLabels = (
                                eligibility?.failed_rules ?? []
                              )
                                .map(r =>
                                  r.tag
                                    ? getTranslation(
                                        locale,
                                        `eligibility_tags.${r.tag}`
                                      )
                                    : null
                                )
                                .filter((s): s is string => Boolean(s));
                              const reasonText =
                                failedTagLabels.length > 0
                                  ? `${locale === "zh" ? "不符" : "Missing"}：${failedTagLabels.join(
                                      "、"
                                    )}`
                                  : locale === "zh"
                                    ? "不符資格"
                                    : "Not eligible";

                              return (
                                <Badge
                                  key={subTypeKey}
                                  variant="outline"
                                  className="bg-gray-100 text-gray-400 border-gray-200 shadow-sm"
                                >
                                  ✗ {label} — {reasonText}
                                </Badge>
                              );
                            }
                          )}
                        </div>
```

- [ ] **Step 3: Update outer condition to use `all_sub_type_list` instead of `eligible_sub_types`**

Old (around line 1328-1332):
```tsx
                  {isEligible &&
                    scholarship.eligible_sub_types &&
                    scholarship.eligible_sub_types.length > 0 &&
                    scholarship.eligible_sub_types[0]?.value !== "general" &&
                    scholarship.eligible_sub_types[0]?.value !== null && (
```

New:
```tsx
                  {isEligible &&
                    scholarship.all_sub_type_list &&
                    scholarship.all_sub_type_list.length > 0 &&
                    scholarship.all_sub_type_list[0] !== "general" &&
                    scholarship.all_sub_type_list[0] !== null && (
```

This preserves the existing skip-when-only-general logic but using the new field.

- [ ] **Step 4: Confirm `getTranslation` import already exists in this file**

```bash
grep -n "getTranslation" frontend/components/enhanced-student-portal.tsx | head -3
```

Expected: at least one match (it's already used elsewhere on the page).

- [ ] **Step 5: Lint check**

```bash
cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | grep -i "enhanced-student-portal" | head -20
cd ..
```

Expected: 0 errors specific to this file.

- [ ] **Step 6: Visual smoke test**

Open `http://localhost:3000`, log in as `csphd0002`. On the scholarship list, find 博士生獎學金 card. Confirm:
- Green chip `✓ 國科會博士生獎學金`
- Grey chip `✗ 教育部博士生獎學金 (指導教授配合款一萬) — 不符：三年級以下`

Switch to en: confirm chips render in English. (English failed-tag text might be empty if `eligibility_tags.三年級以下` lacks an en version — that's an existing tag i18n issue, not in scope.)

- [ ] **Step 7: Commit**

```bash
git add frontend/components/enhanced-student-portal.tsx
git commit -m "feat(student): render all subtypes on scholarship card with eligibility state

Switches the eligible-programs chip list to iterate all_sub_type_list and
subtype_eligibility, rendering ineligible subtypes greyed out with their
failed rule tags inline. Eligible chips keep the current blue style with
a leading ✓; ineligible chips are grey with ✗ and a 不符: tag、tag suffix."
```

---

## Task 6: 確認學籍資料 — 新增國籍與身分欄位

**Files:**
- Modify: `frontend/components/student-wizard/steps/StudentDataReviewStep.tsx`

- [ ] **Step 1: Read text dictionary + maps**

```bash
sed -n '40,130p' frontend/components/student-wizard/steps/StudentDataReviewStep.tsx
```

Note: `t = { zh: {...}, en: {...} }`, then `degreeMap`, `studyingStatusMap`. We will mirror the pattern.

- [ ] **Step 2: Add `nationality` + `identity` keys to both locales**

Use Edit tool. In the zh block (around the existing `text` definitions for degree / enrollmentStatus / etc.), add inside the zh object:

```ts
      nationality: "國籍",
      identity: "身分",
```

And inside the en object:

```ts
      nationality: "Nationality",
      identity: "Identity",
```

(Use Read first to find exact placement next to `semesterCount` or similar.)

- [ ] **Step 3: Add `identityMap`**

After the existing `studyingStatusMap` declaration (around line 129), insert:

```ts
  const identityMap: Record<string, string> = {
    "1": "一般生",
    "2": "原住民",
    "3": "僑生(目前有中華民國國籍生)",
    "4": "外籍生(目前有中華民國國籍生)",
    "5": "外交子女",
    "6": "身心障礙生",
    "7": "運動成績優良甄試學生",
    "8": "離島",
    "9": "退伍軍人",
    "10": "一般公費生",
    "11": "原住民公費生",
    "12": "離島公費生",
    "13": "退伍軍人公費生",
    "14": "願景計畫生",
    "17": "陸生",
    "30": "其他",
  };
```

Source: `backend/alembic/versions/6d5b1940bf8a_seed_reference_tables_degrees_.py:101-118`.

- [ ] **Step 4: Add two grid items in the academic info card**

Use Edit tool. Find the closing `</div>` of the existing grid (after the `Semester Count` block, around line 350). Immediately before that closing `</div>` insert:

```tsx
                      {/* Nationality */}
                      <div className="space-y-2">
                        <label className="text-sm font-medium text-gray-600">
                          {text.nationality}
                        </label>
                        <div className="text-base text-gray-700">
                          {studentInfo.std_nation || "-"}
                        </div>
                      </div>

                      {/* Identity */}
                      <div className="space-y-2">
                        <label className="text-sm font-medium text-gray-600">
                          {text.identity}
                        </label>
                        <div className="text-base text-gray-700">
                          {studentInfo.std_identity
                            ? identityMap[
                                String(studentInfo.std_identity)
                              ] || studentInfo.std_identity
                            : "-"}
                        </div>
                      </div>
```

- [ ] **Step 5: Lint check**

```bash
cd frontend && npx tsc --noEmit -p tsconfig.json 2>&1 | grep -i "StudentDataReviewStep" | head -20
cd ..
```

Expected: 0 errors specific to this file. If `studentInfo` typing complains about missing `std_nation` / `std_identity`, those fields likely exist on the API type already — re-run codegen if not.

- [ ] **Step 6: Visual smoke test**

Open the application wizard for any logged-in student, navigate to 確認學籍資料 step. Confirm:
- 6 fields shown: 學位 / 在學狀態 / 入學年度學期 / 學期數 / **國籍** / **身分**
- 國籍 shows `std_nation` raw string (e.g., "中華民國")
- 身分 shows the mapped name (e.g., "一般生" or "僑生(目前有中華民國國籍生)") — never the raw integer code

- [ ] **Step 7: Commit**

```bash
git add frontend/components/student-wizard/steps/StudentDataReviewStep.tsx
git commit -m "feat(student): show std_nation and std_identity in 確認學籍資料

Adds 國籍 (std_nation, raw string) and 身分 (std_identity, mapped via
identityMap) rows to the academic info card so students can verify the
identity classification that drives subtype eligibility."
```

---

## Task 7: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Frontend build**

```bash
cd frontend && npm run build 2>&1 | tail -30
cd ..
```

Expected: build succeeds with no new errors.

- [ ] **Step 2: Backend test suite (regression check)**

```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest tests/ -x --tb=short 2>&1 | tail -30
```

Expected: existing tests pass. New schema fields default-empty, should not break anything.

- [ ] **Step 3: End-to-end manual matrix**

Run through the test matrix from the spec (Testing Plan → Manual Testing). Tick off each row:

| # | Student | Expected on card |
|---|---|---|
| 1 | 一般本國博士生 | `[✓ 國科會博士生獎學金] [✓ 教育部博士生獎學金 (指導教授配合款一萬)]` |
| 2 | 414708008 (僑/外籍) | `[✓ 國科會博士生獎學金] [✗ 教育部博士生獎學金 (指導教授配合款一萬) — 不符：中華民國國籍]` |
| 3 | csphd0002 (博四) | `[✓ 國科會博士生獎學金] [✗ 教育部博士生獎學金 (指導教授配合款一萬) — 不符：三年級以下]` |
| 4 | 假設博四+外籍 | `[✓ 國科會博士生獎學金] [✗ 教育部博士生獎學金 (...) — 不符：中華民國國籍、三年級以下]` |
| 5 | 任意學生在 確認學籍資料 | 6 個欄位含國籍 + 身分 |

For row 4 if no test fixture matches, document and skip — it's a derived assertion, not blocking.

- [ ] **Step 4: Push branch and open PR**

```bash
git push -u origin investigate/csphd0002-moe-visibility
gh pr create --title "feat: show ineligible scholarship subtypes greyed out + add 國籍/身分 to 確認學籍資料" \
  --body "$(cat <<'EOF'
## Summary
- Backend: expose `all_sub_type_list` and `subtype_eligibility` on `/api/v1/scholarships/eligible` (schema + endpoint plumbing only; service logic untouched).
- Frontend: scholarship card 「可申請項目」 now lists every subtype — eligible chips stay blue with ✓, ineligible chips are grey with ✗ and an inline `不符：tag、tag` reason.
- Frontend: 確認學籍資料 step now also shows 國籍 (`std_nation`) and 身分 (`std_identity` mapped to its reference-table name).
- i18n: `rule_types` updated from short names to full subtype titles for both zh and en.

## Background
Triggered by two cases — csphd0002 (PhD year 4, fails the 一至三年級 rule) and 414708008 (僑/外籍生, fails the 中華民國國籍 rule). Both situations match the existing scholarship policy but the UI silently filtered the ineligible subtype out, leaving students confused. The fix surfaces the result of policy without changing the policy itself.

Spec: `docs/superpowers/specs/2026-04-27-phd-scholarship-card-ineligible-display-design.md`

## Test plan
- [ ] Login as a regular PhD student → both subtypes show ✓
- [ ] Login as csphd0002 → MOE shows ✗ with `不符：三年級以下`
- [ ] Login as 414708008 → MOE shows ✗ with `不符：中華民國國籍`
- [ ] 確認學籍資料 step shows 國籍 and 身分 with mapped name
- [ ] `npm run build` and backend tests pass
EOF
)"
```

---

## Risks / Things to Watch

1. **`rule_types` was orphaned**: Pre-implementation grep showed `rule_types` is currently defined in `i18n.ts` but **never referenced**. So changing the labels is safe — Task 5 introduces the first real consumer (via `getTranslation(locale, "rule_types.${key}")`). Risk #1 from spec is essentially eliminated.
2. **`failed_rules[].tag` lacks i18n** for some tags (e.g., `三年級以下` not yet in `eligibility_tags`): chip falls back to `不符資格` with no detail. To verify after Task 5 — if any failure tag shows up empty, add it to `eligibility_tags` in the same commit.
3. **`std_nation` / `std_identity` types**: confirmed appear in the OpenAPI student snapshot schema. If `studentInfo` type lacks them after codegen, re-run `npm run api:generate`.

---

## Self-Review Notes

- ✅ Spec coverage: every Backend / Frontend Change in spec maps to a task (Task 1-2 = 0a/0b, Task 3 = OpenAPI re-gen, Task 4 = Change 2, Task 5 = Change 1, Task 6 = Change 3).
- ✅ Placeholder scan: no TBDs in actionable steps. The English label text is concrete in Task 4 step 3 (no longer "TBD").
- ✅ Type consistency: `SubtypeRuleDetail` / `SubtypeEligibilityInfo` introduced in Task 1 are referenced by name in Task 3 (codegen verification) and used implicitly via codegen in Task 5/6.
