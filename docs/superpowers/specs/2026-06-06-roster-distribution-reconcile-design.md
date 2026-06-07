# Roster ↔ Distribution Reconcile (補充人) — Design

**Date:** 2026-06-06
**Status:** Approved (pre-implementation)

## Problem

Payment rosters are generated from the distribution result (`generate_rosters_from_distribution`):
one roster per unique `(allocation_year, sub_type)` group of allocated `CollegeRankingItem`s.
After generation the distribution can drift from the roster — e.g. a 備取 is promoted to
allocated, a 補發 is added, or someone is un-allocated. Today the roster only supports
**removing** items (per-item, LOCKED-only). There is **no way to add** an allocated student who
is missing from a generated roster.

This feature lets an admin **compare a roster against its slice of the distribution** and
**selectively add the missing allocated students (補充人) and/or remove orphaned items**.

## Decisions (locked during brainstorming)

| Question | Decision |
|---|---|
| Source of 補充人 | **Distribution diff only** — allocated `CollegeRankingItem`s missing from the roster. No outside students. |
| Roster states allowed | **COMPLETED and LOCKED** (reject DRAFT/PROCESSING/FAILED). |
| Diff scope | **Per-roster** — open one roster, compare against its `(allocation_year, sub_type)` slice. |
| Direction | **Bidirectional** — missing → add, orphan → remove. |
| Apply mechanic | **Selective + confirm** — checkboxes, nothing changes until confirmed. |
| Implementation shape | **Approach A** — server-computed diff + reconcile endpoints, new section in `RosterDetailDialog`. |

## Invariants

1. **Presentation-layer only.** Reconcile edits `payment_roster_items` and roster totals only.
   It NEVER touches `Application.quota_allocation_status` or quota counters. Distribution already
   consumed quota; the roster is downstream.
2. **Distribution-diff only.** A student is addable *only if* they are an allocated
   `CollegeRankingItem` whose `(allocation_year, allocated_sub_type)` matches the roster's pair.
   The server **re-derives** the allowed add/remove sets on every call; client-supplied ids are
   validated against them and rejected otherwise (prevents adding arbitrary students).
3. **Reuse the generation builder.** Adding a person runs the exact same per-application path the
   generation loop uses — no parallel item-construction logic.

## Diff key (mirrors generation grouping exactly)

For roster `R` (with its `ranking_id`s), using generation's fallbacks
(`alloc_year = item.allocation_year or academic_year`, `sub_type = item.allocated_sub_type or "general"`):

- **missing → add** = allocated `CollegeRankingItem`s in pair `(R.allocation_year, R.sub_type)`,
  whose `Application.status == "approved"`, whose `application_id` is **not** already a roster item.
- **orphan → remove** = roster items whose `application_id` is **not** in that allocated set.

Pair matching uses the same `or academic_year` / `or "general"` coalescing as
`generate_rosters_from_distribution` so the diff is the precise inverse of generation.

## Backend — `RosterService` (sync `Session`)

### `get_distribution_diff(roster_id) -> dict`
Returns roster meta + the two sets:
```python
{
  "roster_id": int, "roster_code": str, "status": str,
  "allocation_year": int | None, "sub_type": str | None,
  "missing": [
    {"application_id": int, "student_id_number": str, "student_name": str,
     "department_name": str | None, "allocation_year": int | None,
     "allocated_sub_type": str | None, "application_identity": str | None,
     "scholarship_amount": float}          # estimated from config/application
  ],
  "orphans": [
    {"item_id": int, "application_id": int | None, "student_id_number": str,
     "student_name": str, "is_included": bool, "scholarship_amount": float}
  ]
}
```

### `reconcile_roster(roster_id, add_application_ids, remove_item_ids, admin_user_id, reason) -> dict`
1. Load roster; reject if status ∉ {COMPLETED, LOCKED}.
2. **Re-derive** the missing/orphan sets (same logic as `get_distribution_diff`);
   reject any `add_application_id` not in missing, any `remove_item_id` not in orphans.
3. **Add loop** (per application): `verify_student` if `roster.student_verification_enabled` →
   `_validate_student_eligibility` → `_create_roster_item(...)`. A verification/bank/eligibility
   failure still inserts the row as `is_included=False` with `exclusion_reason` (same as
   generation) and is reported back — never silently dropped.
4. **Remove loop**: delete each item belonging to the roster. Generalize the existing
   `remove_item_from_locked_roster` body into a shared helper usable on COMPLETED *and* LOCKED.
5. Recompute totals via the existing CASE-based recompute; set `excel_stale = True`.
6. Audit: one `AuditLog` per add (`roster.item_added_from_distribution`) and per remove
   (`roster.item_removed_after_lock`), plus one summary log.
7. Single transaction, guarded by a per-roster lock to avoid racing an export.

Returns:
```python
{
  "added":  [{"application_id": int, "item_id": int, "is_included": bool,
              "exclusion_reason": str | None}],
  "removed":[{"item_id": int, "application_id": int | None}],
  "roster": {"total_applications": int, "qualified_count": int,
             "total_amount": float, "excel_stale": True}
}
```

## API — `backend/app/api/v1/endpoints/payment_rosters.py`

Admin-only (`check_user_roles`), ApiResponse-wrapped (`{success, message, data}`).

- `GET  /{roster_id}/distribution-diff` → `data` = diff dict above.
- `POST /{roster_id}/reconcile` — body `{add_application_ids: [int], remove_item_ids: [int], reason?: str}`
  → `data` = reconcile result above.

Regenerate OpenAPI types after schema/endpoint changes:
```bash
cd frontend && npm run api:generate
git add lib/api/generated/schema.d.ts
```

## Frontend — `RosterDetailDialog.tsx` + api module

- New **「比對分發名單」** section, rendered only when `roster.status ∈ {completed, locked}`.
- Button → `getDistributionDiff(rosterId)` → two checkbox groups: **待補充** (missing) and
  **待移除** (orphans), each with select-all.
- Confirm dialog summarizes **「新增 N 人 / 移除 M 人」**; nothing mutates until confirmed.
- `reconcileRoster(rosterId, body)` → toast per-result summary (incl. any added-but-excluded),
  refresh roster items, show **「Excel 需重新匯出」** stale banner + re-export CTA.
- Empty diff → section shows **「名單一致，無需補充」**.
- New api module fns in the payment-rosters module: `getDistributionDiff`, `reconcileRoster`.

## Errors / edge cases

- **Verification/bank/eligibility failure on add** → row inserted as excluded with reason,
  surfaced in the result. Not an error, not silent.
- **New `(sub_type × year)` group with no roster yet** → cannot be surfaced per-roster (nothing
  to open). Handled by re-running generate, which creates the missing roster. **Out of scope.**
- **Empty diff** → friendly "名單一致" state, no-op.
- **Stale client ids** (diff changed between fetch and apply) → server re-derivation rejects them
  with a clear message; client refetches.

## Out of scope

- Adding students not present in the distribution (arbitrary 學號 lookup).
- Any quota / allocation mutation.
- Creating brand-new rosters for groups that were never generated.

## Testing

**Backend** (`app/tests/test_roster_*.py`, sync `Session` fixtures):
- diff correctness — a roster missing some allocated students AND holding some orphans yields the
  correct `missing` / `orphans` sets, with the `(alloc_year, sub_type)` coalescing.
- reconcile **add** — inserts item, recomputes totals, sets `excel_stale=True`, writes audit;
  passes on **COMPLETED** and on **LOCKED**.
- reconcile **remove** — deletes orphan, recomputes totals.
- validation — reject `add_application_id` not in missing; reject `remove_item_id` not in orphans;
  reject DRAFT roster; reject non-`approved` application.
- verification-fail add → row created `is_included=False` with reason, reported in result.

**Frontend**: smoke via the playwright-test-and-debug skill — open a completed roster, 比對,
add a missing student, confirm count increments and the stale banner appears.

## Reused existing code

- `RosterService._create_roster_item` — item construction (amount, sub_type, allocation_year,
  bank account, verification, exclusion reason).
- generation per-application loop (`verify_student` + `_validate_student_eligibility`) — mirrored.
- `remove_item_from_locked_roster` recompute/audit body — generalized into a shared remove helper.
- `RosterDetailDialog` item list + existing per-item remove button — unchanged, sit alongside.
