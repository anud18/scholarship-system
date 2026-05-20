# Admin Student Scholarship History — Design Spec

**Date:** 2026-05-21
**Owner:** howard
**Status:** Design approved, ready for implementation plan

## 1. Purpose

Give admins a single-student lookup tool that answers: *"What scholarships has this student received in the past, in which periods, how many payment records, and what is the total amount?"* The admin enters a 學號 (student number) and gets back both the student's current SIS academic data and a flat list of every locked payment roster record that paid them, with summary totals.

## 2. Scope

**In scope**
- New admin page `/admin/student-history` for single-student lookup by 學號
- New backend endpoint that returns combined academic info + payment history in one response
- Read-only — no edits, no batch operations
- Data source for payments: **`payment_rosters.status = LOCKED`** items only (no in-flight applications, no draft rosters)
- "幾個月" semantics: **count of payment records** (no monthly/yearly conversion)
- SIS-unavailable fallback: render payment history with a warning card

**Explicitly out of scope (YAGNI)**
- Export to CSV/Excel/PDF (browser print is the workaround)
- Batch / multi-student queries
- Querying in-flight applications or pending distributions
- Audit log of admin lookups (can be added later if needed)
- Re-design of existing `StudentDetailModal` or `/admin/students` flow

## 3. Architecture

```
admin browser → /admin/student-history page (Next.js client component)
                              │ (admin enters 學號)
                              ▼
                  GET /api/v1/admin/student-history/{student_number}
                              │
                              ├─ StudentService.get_student_basic_info(stdcode)   → SIS API (HMAC)
                              │   (failure tolerated; surfaced as warning)
                              │
                              └─ StudentScholarshipHistoryService.get_locked_payments(stdcode)
                                  → SELECT FROM payment_roster_items pri
                                       JOIN payment_rosters pr ON pri.roster_id = pr.id
                                     WHERE pri.student_id_number = :stdcode
                                       AND pri.is_included = TRUE
                                       AND pr.status = 'locked'
                                     ORDER BY pr.academic_year DESC, pr.period_label DESC
                              │
                              ▼
                  ApiResponse<StudentScholarshipHistoryData>
```

**Why one endpoint:** the page is a single cohesive view; SIS-failure handling is cleaner inside one response than coordinating two parallel queries on the frontend.

**Why `status='locked'`:** locked is the canonical "money was actually paid out, Excel exported, do not modify" state. `is_included=TRUE` removes verification-failed rows that the finalize step kept on the roster only for audit purposes.

## 4. API Contract

**Endpoint:** `GET /api/v1/admin/student-history/{student_number}`

**Auth:** `admin` or `super_admin` (existing `require_admin` dependency)

**Path param validation:** `student_number` must match `^[A-Za-z0-9]{4,15}$` (digit/letter combos covering NYCU 學號 patterns; rejects path-traversal and non-printables).

**Response (wrapped in standard ApiResponse format per CLAUDE.md §5):**

```jsonc
{
  "success": true,
  "message": "Student history retrieved",
  "data": {
    "student_number": "310460031",

    "academic_info": {
      "available": true,
      "error": null,                            // string when available=false
      "basic_info": {
        "std_cname": "王小明",
        "std_ename": "Wang Hsiao-Ming",
        "std_degree": "1",                       // "1"=博士, "2"=碩士, "3"=學士
        "std_studingstatus": "在學",
        "std_aca_cname": "電機學院",
        "std_depname": "電子博士班",
        "std_depno": "4460",
        "com_email": "wang@nycu.edu.tw"
      }
    },

    "summary": {
      "total_records": 5,
      "total_amount": "50000.00",                 // Decimal serialized as string
      "scholarship_type_count": 2,
      "snapshot_name": "王小明"                    // from most-recent roster item
    },

    "payment_records": [
      {
        "roster_id": 12,
        "roster_code": "ROSTER-114-114-10-NSTC001",
        "period_label": "114-10",
        "academic_year": 114,
        "roster_cycle": "monthly",
        "scholarship_name": "國科會獎學金",
        "scholarship_amount": "10000.00",
        "scholarship_subtype": "nstc",
        "allocation_year": 114,
        "locked_at": "2026-03-15T10:00:00Z"
      }
    ]
  }
}
```

**Status codes**

| Condition | Status | Body |
|---|---|---|
| Both SIS and payments succeed | 200 | full data |
| SIS ok, no payment records | 200 | academic info filled, `payment_records=[]`, `summary.total_records=0` |
| SIS fails, payment records exist | 200 | `academic_info.available=false`, `error="..."`, summary/records from DB |
| SIS fails *and* no payment records | 404 | `"查無此學生資料"` |
| Invalid student_number format | 400 | validation error |
| Caller not admin | 403 | existing auth error |
| Unexpected DB error | 500 | raised — no fallback (CLAUDE.md §1) |

## 5. Backend Implementation

### 5.1 New files

- `backend/app/schemas/student_scholarship_history.py` — Pydantic v2 models:
  - `AcademicBasicInfo`, `AcademicInfo`
  - `PaymentRecord`
  - `HistorySummary`
  - `StudentScholarshipHistoryData`
- `backend/app/services/student_scholarship_history_service.py`:
  - `class StudentScholarshipHistoryService`
  - `async def get_history(self, db: AsyncSession, stdcode: str) -> StudentScholarshipHistoryData`
  - Internal helpers: `_fetch_academic_info()`, `_fetch_locked_payments()`, `_build_summary()`
- `backend/app/api/v1/endpoints/admin/student_history.py`:
  - Single `GET /{student_number}` endpoint
  - Validates path param against regex
  - Returns the standard ApiResponse dict wrapping `data.model_dump()`

### 5.2 Modified files

- `backend/app/api/v1/api.py` — register the new router at prefix `/admin/student-history`

### 5.3 Service logic

```python
async def get_history(self, db, stdcode):
    # Run in parallel where it makes sense
    sis_data, payments = await asyncio.gather(
        self._fetch_academic_info(stdcode),
        self._fetch_locked_payments(db, stdcode),
        return_exceptions=True,
    )

    academic_info = self._build_academic_info(sis_data)
    payment_records = self._build_payment_records(payments)

    if not academic_info.available and not payment_records:
        raise NotFoundError("查無此學生資料")

    summary = self._build_summary(payment_records)
    return StudentScholarshipHistoryData(
        student_number=stdcode,
        academic_info=academic_info,
        summary=summary,
        payment_records=payment_records,
    )
```

`_build_summary`:
- `total_records = len(payment_records)`
- `total_amount = sum(r.scholarship_amount for r in records)` (Decimal)
- `scholarship_type_count = len({r.scholarship_name for r in records})`
- `snapshot_name` = `payment_records[0].student_name` if any, else `None`

## 6. Frontend Implementation

### 6.1 New files

- `frontend/app/admin/student-history/page.tsx` — server component shell that renders the client panel
- `frontend/components/admin/student-history/StudentHistoryPanel.tsx` — input, React Query state, top-level error/empty handling
- `frontend/components/admin/student-history/AcademicInfoCard.tsx` — renders `academic_info` or the SIS-unavailable warning
- `frontend/components/admin/student-history/SummaryCards.tsx` — three KPI cards
- `frontend/components/admin/student-history/PaymentHistoryTable.tsx` — sortable flat table
- `frontend/lib/api/modules/student-history.ts` — `apiClient.studentHistory.getByNumber(stdcode)`

### 6.2 Modified files

- `frontend/lib/api/index.ts` — register the new API module
- Admin sidebar/nav component (located during implementation) — add "學生領取歷史查詢" link

### 6.3 Page layout

```
┌────────────────────────────────────────────────┐
│ 學生領取歷史查詢                                │
├────────────────────────────────────────────────┤
│ [學號 _________________] [查詢]                │
├────────────────────────────────────────────────┤
│ ▸ 學籍資料                                      │
│   姓名 / 系所 / 學位 / 在學狀態                 │
│   (yellow warning card if SIS unavailable —    │
│    falls back to snapshot_name)                │
├────────────────────────────────────────────────┤
│ [總筆數: 5]  [總金額: NT$ 50,000]  [類型: 2]   │
├────────────────────────────────────────────────┤
│ 期間  | 獎學金     | 子類型 | 金額    | 配額年 │
│ 114-11| 國科會獎學金| nstc   | 10,000  | 114    │
│ 114-10| 國科會獎學金| nstc   | 10,000  | 114    │
│ ...                                             │
└────────────────────────────────────────────────┘
```

### 6.4 Frontend behavior

- Empty input + submit → client-side validation message, no request
- Enter key submits; Search button submits
- Loading: skeleton on academic card + spinner on table area
- 404 → friendly "查無此學生資料" empty state with input still focused
- SIS warning rendered as a yellow `Card` matching the pattern in `StudentDetailModal.tsx:171-182`
- Empty `payment_records` → "尚無領取記錄" empty state inside the table card

### 6.5 OpenAPI type sync

Per CLAUDE.md §8, after adding the endpoint run `cd frontend && npm run api:generate` and commit `lib/api/generated/schema.d.ts`.

## 7. Error Handling & Edge Cases

| Scenario | Behavior |
|---|---|
| Invalid student_number format | 400 from server; frontend also blocks submit with inline message |
| SIS API fails (timeout, 5xx, unavailable) | `academic_info.available=false`, `error="..."`; payments still served |
| SIS ok, zero payments | 200 with empty `payment_records`; "尚無領取記錄" empty state |
| SIS fails AND zero payments | 404 "查無此學生資料" |
| DB error | Bubble up — no fallback or mock data (CLAUDE.md §1) |
| Concurrent locked rosters with same student | All returned; sorted newest first |
| Non-admin caller | 403 from `require_admin` |
| Long-running SIS call | Inherits existing `student_api_timeout` (default 10s); query continues |

## 8. Testing

### 8.1 Backend

`backend/tests/test_student_scholarship_history_service.py`:
- Empty result set
- Multiple records across academic years and scholarship types
- Filters out `status=DRAFT`/`PROCESSING`/`COMPLETED`/`FAILED` rosters
- Filters out `is_included=FALSE` items
- Decimal math for `total_amount`

`backend/tests/test_admin_student_history_endpoint.py`:
- Unauthenticated → 401
- Non-admin role → 403
- Valid stdcode with seeded data → 200 with expected shape
- Stdcode with no records and SIS error → 404
- Invalid stdcode format (e.g. `"../etc/passwd"`) → 400
- SIS unavailable path: monkey-patch `StudentService.get_student_basic_info` to raise; assert `academic_info.available=false`

### 8.2 Frontend

`frontend/e2e/admin-student-history.spec.ts` (Playwright):
- Login as `admin@nycu.edu.tw`
- Navigate to `/admin/student-history`
- Submit empty → validation message visible
- Submit seeded student number → summary cards + table rows visible
- Submit nonexistent number → "查無此學生資料" empty state visible

## 9. Migration / Data Considerations

- No DB migrations required — all reads use existing `payment_rosters` and `payment_roster_items` tables
- No seed-data changes — existing locked rosters in the dev DB will populate the page
- If dev DB has no locked rosters, the manual-distribution flow needs to be exercised once to produce test data (or a fixture can be added in the backend test setup)

## 10. Open Questions

None — all decisions resolved during brainstorming:

| Decision | Resolution |
|---|---|
| Data source | Locked rosters only |
| UI placement | New standalone page `/admin/student-history` |
| "總月數" math | Count payment records (no period conversion) |
| Display organization | Summary cards + flat detail table |
| SIS lookup failure | Show payment records + warning card |
| Export | Not in v1 |
| API shape | Single unified endpoint |
