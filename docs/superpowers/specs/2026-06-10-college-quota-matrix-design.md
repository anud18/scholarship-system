# College Quota Matrix on the Manual Distribution Page — Design

**Date**: 2026-06-10
**Status**: Approved
**Related**: `docs/superpowers/specs/2026-06-08-config-shared-quota-pools-design.md` (shared quota pools, §6.x referenced below)

## Problem

The 造冊分發頁面 (admin manual distribution panel, `ManualDistributionPanel`) shows
remaining quota only at the **(sub_type × config)** level — the 剩餘可分配配額 block
and the allocation grid columns. Admins cannot see how many slots each **college**
has left, even though matrix-mode configs define quotas per college
(`quotas = {"nstc": {"E": 15, "C": 12, ...}}`). This also applies to linked
prior-year configs (共用往年名額, via `shared_quota_sources`), which today surface
only a config-level total/remaining.

## Decision summary (user-approved)

- Display as a dedicated **college × config matrix table** on the manual
  distribution page: rows = colleges, columns = (sub_type × config) including
  linked prior-year configs, cell = `剩餘/總額`.
- Remaining counts **live-update** by subtracting locally staged (un-saved)
  allocations on the page.
- Data delivered by **extending the existing `/quota-status` endpoint** (no new
  endpoint, no frontend-only computation — the frontend never receives linked
  configs' per-college matrices nor renewal college attribution).

## Backend

### `GET /api/v1/manual-distribution/quota-status` (extended)

Each entry of `by_config` gains a `by_college` field:

```jsonc
{
  "nstc": {
    "display_name": "國科會",
    "by_config": [
      {
        "config_id": 12,
        "config_code": "phd_115",
        "academic_year": 115,
        "is_own": true,
        "total": 35,
        "remaining": 7,
        "by_college": {                       // NEW; null for non-matrix configs
          "E": {"total": 15, "allocated": 13, "remaining": 2},
          "C": {"total": 12, "allocated": 10, "remaining": 2},
          "":  {"total": 0,  "allocated": 1,  "remaining": -1}   // 未知 bucket
        }
      }
    ]
  }
}
```

Rules:

- The shape matches the frontend `CollegeQuota` type that ALREADY exists in
  `frontend/lib/api/modules/manual-distribution.ts` (`{total, allocated,
  remaining}` keyed by college code) — the type predates the backend support;
  this feature makes the backend actually send it. The field is named
  `allocated` (not `used`) for that reason.
- `total` reads the config's `quotas[sub_type][college_code]` matrix. Works
  identically for the own config and each linked prior-year config (both store
  the same matrix shape). For configs with `has_college_quota == False`,
  `by_college` is `null` (scalar pool; no per-college split exists).
- `allocated` (the "used" count) comes from a new service method
  `consumers_by_college(config_id, sub_type) -> dict[str, int]` using the SAME
  two-half consumer partition as `consumers_count` (spec §6.2):
  1. allocated `CollegeRankingItem`s whose application is NOT a renewal
     (`is_renewal == False` guard is load-bearing — see `consumers_count`
     docstring);
  2. approved renewal `Application`s.
  Each consumer is attributed to a college via
  `application.student_data["std_academyno"]` — the same attribution
  `auto_allocate_preview` already uses. Grouping happens in Python over the
  loaded rows (no JSON-path SQL).
- A consumer with missing/empty `std_academyno` lands in the `""` bucket
  (rendered 「未知」). The `""` row is included only when its `allocated > 0`.
- Colleges appear in `by_college` if they have quota > 0 in the matrix OR have
  `allocated > 0`; a consumer from a college absent from the matrix gets
  `total: 0`.
- `remaining = total - allocated`, **not clamped** — negative values are reported
  as-is and flagged in the UI. This is safe because per-college numbers are
  advisory; the enforced gate remains the global per-(config × sub_type)
  recount under `SELECT FOR UPDATE` (`_assert_round_not_oversubscribed`).
- Per-college totals must satisfy `sum(by_college[].total) == total` for matrix
  configs (same source data as `pool_total`), and
  `sum(by_college[].allocated) == consumers_count(config_id, sub_type)`.
- No `college_name` in the payload: the frontend resolves display names via
  `getAcademyName(code, academies)` from `useReferenceData`, falling back to a
  lookup in the loaded `students` array, then the raw code.
- Response stays in the standard `{success, message, data}` wrapper.

### Invariants / consistency

- `consumers_by_college` and `consumers_count` MUST share the same filters.
  Implement `consumers_count` semantics once: either have `consumers_count`
  delegate to `sum(consumers_by_college(...).values())` or extract shared query
  builders — implementer's choice, but the two must not drift.

## Frontend

### New component: `frontend/components/admin/manual-distribution/CollegeQuotaMatrix.tsx`

Rendered in `ManualDistributionPanel` adjacent to the existing
剩餘可分配配額 (`AvailableQuotasBlock`) block. Target ≤ ~200 lines.

- **Columns**: reuse the existing `subTypeCols` derivation (own config first,
  then linked sources by descending `academic_year`; same
  `國科會 · phd_114`-style labels). Columns with `is_own === false` get a
  「共用往年」 badge. Columns with `total <= 0` stay excluded (same rule as
  today's `subTypeCols`).
- **Rows**: union of `college_code`s across all columns' `by_college`, sorted
  by code. Row label resolved via `getAcademyName(code, academies)` →
  students-array lookup → raw code; the `""` code renders 「未知」. If a column is
  a non-matrix config (`by_college === null`), it renders `—` in every college
  row; no separate 不分學院 row in v1 (the config-level card already shows its
  numbers).
- **Cell**: `liveRemaining/total`, where
  `liveRemaining = serverRemaining − Δlocal(college, sub_type, config_id)` and
  `Δlocal = (students whose CURRENT local allocation is this cell) − (students
  whose SERVER-SAVED allocation is this cell)`.
  - Both counts come from the already-loaded `students` array (which carries
    `college_code`, `is_allocated`, `allocated_sub_type`,
    `allocation_config_id`) joined with `localAllocations` (ranking_item_id →
    `{sub_type, config_id}`).
  - The delta form is required because `localAllocations` is SEEDED from
    server-saved allocations (plus auto-preview suggestions), and server
    `used` already includes saved allocations — subtracting raw local counts
    would double-count. It also correctly handles un-allocating (Δ negative →
    remaining goes back up) and moving a student between cells. NOTE: this is
    intentionally NOT the existing `localAllocCounts`-vs-`total` comparison
    used by the grid checkboxes — that ignores external consumers (approved
    renewals, cross-config borrowers) which are only in server `used`.
  - `—` when the college has no quota in that config and no usage.
  - Styling: `liveRemaining < 0` → red (over-allocated), `=== 0` → grey/muted,
    `> 0` → normal. Footnote: 「共用往年 = 往年共用名額；超額僅供參考，鎖定時以全域名額檢查為準」.
- **No new fetch / loading state**: data arrives with the existing
  `getQuotaStatus` calls (initial load, post-save, post-preview refreshes).
- **Types**: extend `QuotaStatus` types in
  `frontend/lib/api/modules/manual-distribution.ts`; regenerate OpenAPI types
  (`cd frontend && npm run api:generate`).

## Error handling

- Backend: malformed matrix entries (non-int quota values) coerce to 0,
  consistent with `pool_total`'s defensive casting; no fallback data on DB
  errors (errors propagate per project policy).
- Frontend: when `by_college` is absent (older payload mid-deploy) the matrix
  renders nothing rather than crashing (`by_college ?? null` guards).

## Testing

Backend (async, `backend/app/tests/`, follow `test_manual_distribution_pool_math.py` style):

1. `consumers_by_college` — general winner counted in own college.
2. `consumers_by_college` — approved renewal attributed to its college.
3. `consumers_by_college` — empty `std_academyno` lands in `""` bucket.
4. `consumers_by_college` — revoked/restored renewal not double-counted
   (is_renewal partition guard, mirroring existing `consumers_count` tests).
5. `get_quota_status` — matrix config returns `by_college` with correct
   total/used/remaining; sums match `pool_total`/`consumers_count`.
6. `get_quota_status` — non-matrix config returns `by_college: null`.
7. `get_quota_status` — linked prior-year config exposes its own per-college
   matrix; consumer of the linked config decrements that config's college row.
8. `get_quota_status` — over-allocation yields negative `remaining` (no clamp).

Frontend: type-check (`tsc`) + localhost smoke test of the manual distribution
panel (login as admin, verify the matrix renders, stage an allocation, verify
the cell decrements and turns red when over).

## Out of scope

- Per-college **enforcement** at allocate/finalize time (stays global).
- Changes to `AvailableQuotasBlock` or `/state` payloads.
- College-side (學院端) pages — this is the admin 造冊分發 page only.
