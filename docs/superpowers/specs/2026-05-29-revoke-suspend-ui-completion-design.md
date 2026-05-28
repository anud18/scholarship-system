# Revoke / Suspend UI Completion + Refinement Design

**Date**: 2026-05-29
**Status**: Draft (pending user review of written spec)
**Builds on**: [`2026-05-21-revoke-suspend-distribution-design.md`](./2026-05-21-revoke-suspend-distribution-design.md)

## Overview

The 2026-05-21 spec defined a 撤銷 (Revoke) / 停發 (Suspend) feature to replace the old per-student "取消" (✕) button on the admin Manual Distribution Panel. That feature shipped **partially**: the full backend, the 撤銷 UI, and the locked-roster 撤銷 cleanup all work. Three intended pieces were never finished, and the user now requests two deliberate changes to the original design.

This spec specifies **only the remaining + changed work**. It does not re-describe the parts already shipped (see the 2026-05-21 spec for those).

### What already shipped ✅ (do not rebuild)

- `applications` revoke/suspend columns + `payment_rosters.excel_stale` (migration `revoke_suspend_001`).
- `quota_allocation_status` values `revoked` / `suspended`.
- Service: `manual_distribution_service._cancel_allocation(mode)` + `revoke_allocation` + `suspend_allocation` (both: status→cancelled, delete items in non-LOCKED rosters, recompute totals, audit log).
- Service: `roster_service.get_revoked_suspended_for_roster` + `remove_item_from_locked_roster` (mode-agnostic hard-delete from LOCKED roster, sets `excel_stale`).
- Endpoints: `POST /manual-distribution/applications/{id}/revoke`, `POST .../suspend`, `GET /payment-rosters/{id}/revoked-suspended`, `DELETE /payment-rosters/{id}/items/{item_id}`.
- Schemas: `RevokeRequest`, `SuspendRequest`, `RevokedSuspendedEntry`, `RevokedSuspendedList`.
- Frontend: per-student **撤** button + revoke dialog (`ManualDistributionPanel.tsx`); `revokeAllocation` api method; RosterDetailDialog showing 撤銷名單 + 停發名單 with count + names + reason, and a 「從本造冊移除」 button on the **撤銷** rows only.

### Gaps + changes this spec covers

| # | Item | Type | Origin |
|---|---|---|---|
| G1 | The ✕ "取消此學生的分配" column still exists on the distribution table. Remove it. | Gap (intended in old spec, never done) | old spec §"Manual Distribution Panel" |
| G2 | The 停發 (停) button + suspend dialog + `suspendAllocation` api method were never built. Build them. | Gap | old spec §"row action column" |
| G3 | 撤銷 reason field: confirm free-text with a placeholder hint「違反獎學金要點」. | Refinement | brainstorm Q3 |
| C1 | Suspend reason input = **dropdown 休學/退學/畢業 (+ 其他) + optional note**, not free textarea. | Change vs old spec | brainstorm 停發-reason |
| C2 | In a LOCKED roster, **停發 rows also get a「從本造冊移除」button** (old spec made them info-only). | Change vs old spec §304 | brainstorm Q4 |
| R1 | Extract a shared revoke/suspend dialog (DRY) instead of duplicating; same for the RosterDetailDialog revoked/suspended sections. (No separate hook unless the component grows.) | Refactor (code quality) | brainstorm Option B |

---

## Decisions (locked during brainstorming)

1. **取消 → 撤銷 + 停發.** Delete the ✕ staged-cancel column. Unstaging a not-yet-saved allocation is done by unchecking its checkbox (already supported). The persisted per-student action column shows **two** buttons: 撤 (撤銷) and 停 (停發).
2. **停發 trigger** = manual button + reason. No automatic SIS-enrollment-status detection in this iteration (deferred).
3. **撤銷 reason** = free text, required, placeholder「違反獎學金要點」.
4. **停發 reason** = dropdown {休學, 退學, 畢業, 其他} + optional free-text note. Composed reason sent to backend is always non-empty (the dropdown label, optionally `「{label}：{note}」`), satisfying `SuspendRequest.reason` (min_length=1).
5. **Locked roster 停發** = gets a「從本造冊移除」button, same behavior as 撤銷 (calls the same mode-agnostic `DELETE /payment-rosters/{id}/items/{item_id}`).
6. **Code structure** = Option B: extract a shared dialog component (`AllocationActionDialog`) reused by revoke + suspend, and a shared `RevokedSuspendedSection` in RosterDetailDialog. Reduces duplication and shrinks `ManualDistributionPanel.tsx` (currently ~2200 lines / 87 KB, far over the 800-line guideline). No separate custom hook unless the component grows too large.

---

## Out of Scope

- Automatic 停發 from SIS verification (graduated/suspended/withdrawn) — deferred. `StudentVerificationStatus` already exists if revisited later.
- Batch revoke/suspend (multi-select toolbar).
- Undo / restore flow (recovery via audit log + DB, as in old spec).
- Auto-promote alternate when a slot frees up.
- Student notifications (email/SMS).
- Any new backend service/endpoint/migration. **Backend is complete; this iteration is frontend + tests only.** The one allowed backend touch is adding tests if coverage is missing (see Testing).

---

## Behavior

No data-layer behavior changes. Revoke and suspend already share `_cancel_allocation`; `remove_item_from_locked_roster` already deletes any item regardless of revoke/suspend. The only behavioral delta is in the **UI surface**:

- **Distribution table**: ✕ column removed. For a student with a persisted allocation (gate: `student.allocated_sub_type` present — same gate the current 撤 button uses), render `[撤] [停]`. Each opens its mode's dialog. Backend still defends with the `quota_allocation_status == 'allocated'` → 400 check and `with_for_update` row lock.
- **撤 dialog**: free-text reason, required. Placeholder「違反獎學金要點」. Confirm disabled while `reason.trim()` empty.
- **停 dialog**: dropdown {休學, 退學, 畢業, 其他} (required) + optional note textarea. Confirm disabled until a dropdown option is chosen. Composed `reason`:
  - no note → the option label (e.g. `休學`)
  - with note → `「{label}：{note}」` (e.g. `休學：已辦理 114-2 休學`)
- **Locked-roster RosterDetailDialog**: 撤銷 section unchanged. **停發 section gains a「從本造冊移除」button per row**, identical handler to the 撤銷 rows. After removal, refetch the revoked/suspended list; the existing `excel_stale` → "請重新匯出 Excel" banner already fires from the backend flag.

### Edge cases (deltas only; rest inherited from old spec)

| Scenario | Behavior |
|---|---|
| 停發 with no dropdown option selected | Confirm button disabled (client). Backend 422s on empty reason as defense. |
| 停發 option = 其他 with empty note | Confirm stays disabled — note is **required** when 其他 is chosen, so the composed reason is always `「其他：{note}」` (never bare `其他`). |
| Removing a 停發 student from a LOCKED roster | Same as 撤銷 removal: hard-delete item, recompute totals, set `excel_stale`, roster stays LOCKED, audit `roster.item_removed_after_lock`. |
| Student already revoked/suspended | After any action, `fetchData` refreshes the row. A second action is rejected by the backend (409). **No client-side hide/disable of the buttons in this iteration** — the distribution-student payload (`DistributionStudent`, manual-distribution.ts:12-37) does not expose `quota_allocation_status`, and adding it is a backend change explicitly out of scope. Rely on backend 409 + refresh. |

---

## Frontend Changes

### 1. `frontend/lib/api/modules/manual-distribution.ts`

Add `suspendAllocation`, mirroring `revokeAllocation` (~line 553). Endpoint already present in generated schema (`POST /api/v1/manual-distribution/applications/{application_id}/suspend`).

**IMPORTANT — mirror the *actual* mechanism.** `revokeAllocation` (verified at manual-distribution.ts:553-584) does **not** use `typedClient.raw.POST`. It uses a raw `fetch()` with a manually-attached bearer token, `JSON.stringify({ reason })`, manual `!response.ok` handling, and returns `Promise<ApiResponse<unknown>>`. Copy that shape exactly:

```ts
/**
 * Suspend an allocated student's scholarship distribution.
 * Removes from unlocked rosters and marks application as cancelled/suspended.
 */
suspendAllocation: async (
  application_id: number,
  reason: string
): Promise<ApiResponse<unknown>> => {
  const token = typedClient.getToken();
  const response = await fetch(
    `/api/v1/manual-distribution/applications/${application_id}/suspend`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ reason }),
    }
  );
  let body: unknown = null;
  try { body = await response.json(); } catch { /* ignore */ }
  if (!response.ok) {
    const b = body as { detail?: string; message?: string } | null;
    return { success: false, message: b?.detail || b?.message || "停發失敗", data: undefined };
  }
  return body as ApiResponse<unknown>;
},
```

### 2. New `frontend/components/admin/manual-distribution/AllocationActionDialog.tsx`

Shared dialog for both modes. Props:

```ts
type AllocationMode = "revoke" | "suspend";

interface AllocationActionDialogProps {
  mode: AllocationMode;
  target: { applicationId: number; studentName: string } | null;
  onClose: () => void;
  onConfirmed: (studentName: string) => void; // parent does fetchData + success toast
}
```

- Open when `target !== null`.
- **revoke**: title「撤銷獎學金分發」, free-text `<textarea>` reason (placeholder「違反獎學金要點」 — note: this **replaces** the currently-shipped placeholder「請說明撤銷原因」at Panel:1904), confirm「確認撤銷」(red), disabled while `reason.trim()` empty or in-flight.
- **suspend**: title「停發獎學金分發」, dropdown {休學, 退學, 畢業, 其他} (required) + optional note `<textarea maxLength={400}>`, confirm「確認停發」(orange), disabled until an option is chosen (and note required when option === 其他).
- **Primitive decision (resolves the AlertDialog-has-no-Select problem):** build the shared dialog on **shadcn `Dialog` + `Select`**, following the existing precedent — the sibling exclude-dialog in `RosterDetailDialog.tsx` (~607-691) already uses `Dialog` + shadcn `Select`. Do **not** force a `<select>` inside `AlertDialog` (the current revoke dialog's `AlertDialog` primitives have no Select sub-pattern). Revoke mode simply renders the textarea and no `Select`.
- Owns its own `reason` / `option` / `note` / `isSubmitting` state; calls `revokeAllocation` or `suspendAllocation` based on `mode` (both return `ApiResponse<unknown>`); on success calls `onConfirmed(studentName)` then closes; on failure surfaces `resp.message`.
- **Composed reason** sent to the backend:
  - 休/退/畢 with no note → the label alone (e.g. `休學`).
  - any option with a note → `「{label}：{note}」` (e.g. `休學：已辦理 114-2 休學`, `其他：…`).
  - 其他 → a note is required, so it always sends `「其他：{note}」` (never bare `其他`).
  - The `note maxLength={400}` keeps the composed string under `SuspendRequest.reason`'s `max_length=500` ceiling.

Do **not** pre-extract a `useAllocationAction` hook — the user asked only to share the dialog (Option B). Keep submit logic inside the component unless it demonstrably grows too large.

### 3. `frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx`

- **Delete** the ✕ "取消此學生的分配" column (JSX ~1404-1428) and the `setLocalAllocations(... null)` onClick it carried. Confirm no other code path depends on that button (unstaging stays available via checkbox uncheck at ~1487).
- **Action column** (currently the 撤-only column ~1573-1593): render `[撤] [停]` side-by-side when `student.allocated_sub_type` is set; otherwise「—」.
  - 撤: `bg-red-50 text-red-600 border-red-200`, tooltip「撤銷此學生獎學金」.
  - 停: `bg-orange-50 text-orange-600 border-orange-200`, tooltip「停發此學生獎學金」.
- Replace the inline revoke `useState` block (`revokeTarget`, `revokeReason`, `isRevoking`) and the inline revoke `AlertDialog` (~1890-1923) and `handleRevoke` (~583-610) with:
  - one `actionTarget` state `{ applicationId, studentName, mode } | null`,
  - the shared `<AllocationActionDialog>` rendered once,
  - an `onConfirmed` callback that runs `fetchData()` then sets the success `saveMessage` (preserving the post-`fetchData` ordering fix from commit `2dd0f611` — set the message **after** `fetchData` so it isn't cleared).
- Net effect: panel loses the duplicated revoke dialog + the ✕ column, gains a single shared-dialog hookup. Expect a net line reduction.

### 4. `frontend/components/roster/RosterDetailDialog.tsx`

- **Add the「從本造冊移除」button to the 停發 rows** (~lines 483-499), identical to the 撤銷 rows' button (~454-466): `onClick={() => handleRemoveLockedItem(s.item_id!, s.student_name)}`, gated on `s.item_id !== null`, disabled while `removingItemId === s.item_id`.
- **Drop the「（僅資訊）」label** from the suspended summary (currently `RosterDetailDialog.tsx:480`「…位學生被停發（僅資訊）」). Since 停發 rows now have a remove action, change the heading to match the revoked tone, e.g.「…位學生被停發，請手動處理」.
- **Use the shipped flattened entry shape**, not the old-spec field names. `RevokedSuspendedEntry` (verified at payment-rosters.ts:18-25) is `{ application_id, student_name, student_id_number, event_at, reason, item_id }`. The section renders `s.event_at` (date), `s.reason`, and gates the button on `s.item_id !== null`. Do **not** reference `revoke_reason`/`revoked_at`/`suspend_reason` in the frontend — those are backend column names, already flattened by the API layer.
- **Refactor** the two near-identical `<details>` blocks (revoked ~422-470, suspended ~473-501) into one reusable inline section/component, e.g. `RevokedSuspendedSection`, parameterized by:
  - `kind: "revoked" | "suspended"` (border/icon/heading: red「⚠️…被撤銷，請手動處理」vs slate「ℹ️…被停發，請手動處理」),
  - `entries`, `removingItemId`, `onRemove`.
  Both kinds now render the remove button (per C2), so the only differences are heading text + border/icon styling.
- `handleRemoveLockedItem` (~139-169) already does confirm → `removeItemFromLockedRoster` → refetch `getRevokedSuspended` → toast; no change to it.
- **Known limitation (pre-existing, do not expand scope):** after a locked-roster removal the dialog refetches the revoked/suspended list, but the「請重新匯出 Excel」banner is keyed on the `period.excel_stale` **prop**, which stays stale until the dialog is reopened (there is an explicit TODO at `RosterDetailDialog.tsx:159-161` — no `onChanged` prop). This already affects the shipped 撤銷 path. Leave as-is for this iteration; wiring an `onChanged`/refresh callback is a separate, optional improvement.

### 5. `frontend/lib/api/generated/schema.d.ts`

No backend schema change in this iteration, so regeneration is likely a no-op. Run `cd frontend && npm run api:generate` after wiring and commit only if it produces a diff (CI validates sync).

---

## Audit Log

No new actions. Existing `application.suspend` and `roster.item_removed_after_lock` already cover the newly-wired UI paths.

---

## Testing

### Frontend Playwright E2E — **write a new spec** (none exists)

There is **no** `frontend/e2e/admin/` directory and **no** existing revoke/suspend e2e spec (the 2026-05-21 spec only *planned* one). E2E specs live under **`frontend/e2e/specs/`**. Create a new `frontend/e2e/specs/revoke-suspend.spec.ts` (use the existing helpers in `frontend/e2e/helpers` + `global-setup.ts` fixtures):

- Distribution panel: allocated student row shows **both** 撤 and 停; the ✕ "取消此學生的分配" column is **gone**.
- Click 停 → suspend dialog → select 休學 → confirm → row reflects cancelled / success toast.
- 停 dialog: confirm disabled until an option is chosen; 其他 requires a note.
- 撤 dialog: placeholder「違反獎學金要點」visible; empty reason disables confirm.
- Locked roster detail: a 停發 student shows「從本造冊移除」; click → confirm → row disappears, 「請重新匯出 Excel」banner appears on reopen.

### Frontend unit/component

- `AllocationActionDialog`: revoke mode renders textarea + correct disabled logic; suspend mode renders dropdown + note + correct disabled logic; composes reason `「{label}：{note}」` correctly; 其他 requires a note.
- `frontend/lib/api/modules/__tests__/manual-distribution.test.ts`: add a `suspendAllocation` test asserting the POST path + `{ reason }` body. **Update the method-count invariant**: the test currently pins `"module exposes exactly 14 methods"` (test:388) with a 14-entry sorted array ending at `revokeAllocation`. Change the title/count to **15** and insert `"suspendAllocation"` into the sorted array immediately after `"revokeAllocation"`.

### Backend (verify only — likely no change)

Backend is unchanged. The suspend service + locked-removal paths already have coverage under **`backend/app/tests/`**: `test_revoke_suspend_service.py`, `test_revoke_suspend_flow.py`, `test_roster_item_removal_service.py`. Confirm `test_roster_item_removal_service.py` exercises a **suspended** (not only revoked) application; the removal is mode-agnostic, but C2 makes the suspend remove-path user-reachable for the first time. Add a case only if that assertion is missing. (Note: these files are under `backend/app/tests/`, **not** `backend/tests/`.)

---

## Files Affected

| File | Change |
|---|---|
| `frontend/lib/api/modules/manual-distribution.ts` | + `suspendAllocation` method |
| `frontend/components/admin/manual-distribution/AllocationActionDialog.tsx` | **New** — shared revoke/suspend dialog on `Dialog`+`Select` (no separate hook) |
| `frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx` | Remove ✕ column; action column → `[撤][停]`; replace inline revoke dialog/state/handler with shared dialog |
| `frontend/components/roster/RosterDetailDialog.tsx` | Add remove button to 停發 rows; drop「（僅資訊）」label; extract `RevokedSuspendedSection` for both kinds |
| `frontend/lib/api/modules/manual-distribution.ts` | + `suspendAllocation` (raw-fetch mechanism, mirroring `revokeAllocation`) |
| `frontend/lib/api/modules/__tests__/manual-distribution.test.ts` | + `suspendAllocation` test; method-count 14 → 15 + insert in sorted array |
| `frontend/components/**/__tests__/` | + `AllocationActionDialog` component tests |
| `frontend/e2e/specs/revoke-suspend.spec.ts` | **New** spec: 撤+停 buttons, ✕ removed, locked-roster suspend removal |
| `frontend/lib/api/generated/schema.d.ts` | Regenerate (expected no-op) |
| `backend/app/tests/test_roster_item_removal_service.py` | + suspended-application case **only if** not already covered |

---

## Verification Checklist (implementation done when)

- [ ] ✕ "取消此學生的分配" column no longer renders anywhere on the distribution panel.
- [ ] Allocated student row shows 撤 + 停; both open the shared `Dialog`-based dialog in the correct mode.
- [ ] 撤 dialog placeholder「違反獎學金要點」(replaced the old「請說明撤銷原因」); required reason.
- [ ] 停 dialog dropdown 休/退/畢/其他 + optional note (maxLength 400); 其他 requires note; reason composed as `「{label}：{note}」`.
- [ ] LOCKED roster detail: both 撤銷 and 停發 rows show「從本造冊移除」; 停發 summary no longer says「（僅資訊）」.
- [ ] RosterDetailDialog section uses flattened fields `s.event_at` / `s.reason` / `s.item_id` (no `revoke_reason`/`revoked_at`).
- [ ] `manual-distribution.test.ts` method-count updated to 15 with `suspendAllocation` inserted.
- [ ] `npm run lint`, `npm run test` (frontend), affected `backend/app/tests/` green.
- [ ] `cd frontend && npm run api:generate` produces no unexpected diff.
- [ ] `ManualDistributionPanel.tsx` is no larger than before (goal: move toward the 800-line guideline by extracting the dialog; raw subtraction not required, but the panel must not grow).
