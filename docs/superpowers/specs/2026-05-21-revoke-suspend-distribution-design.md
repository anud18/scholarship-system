# Revoke / Suspend Scholarship Distribution Design

**Date**: 2026-05-21
**Status**: Approved (pending user review of written spec)

## Overview

Split the existing single "取消" (✕) button on the admin Manual Distribution Panel into two distinct post-roster-generation actions: **撤銷 (Revoke)** and **停發 (Suspend)**.

- **撤銷 (Revoke)**: Remove the student from all non-LOCKED rosters now, AND surface a manual cleanup task for any LOCKED (historical) rosters the student still appears in. Use when previously-paid scholarships need to be reclaimed.
- **停發 (Suspend)**: Remove the student from all non-LOCKED rosters now. Past LOCKED rosters are left untouched (money already paid stays paid). Use when only future payments should stop.

Both actions move the application to `status = cancelled` (terminal). The differentiator is captured in `quota_allocation_status` (`revoked` vs `suspended`) and is the basis for the UI list displayed inside each LOCKED roster.

---

## Assumptions

Three assumptions confirmed during brainstorming, included here so they can be challenged on final review:

| ID | Assumption |
|---|---|
| A | Pre-finalize (`quota_allocation_status != 'allocated'`): the two new buttons are **disabled**. Pre-finalize allocation editing continues to use the existing checkbox UI in the same table. |
| B | Both 撤銷 and 停發 set `application.status = cancelled` (terminal). The difference is recorded in `quota_allocation_status` (`revoked` / `suspended`). No "undo" feature in this iteration — recovery is manual via audit log + DB. |
| C | After 撤銷/停發, the freed sub_type × allocation_year quota slot is **not** auto-filled with an alternate. Admin re-allocates manually. |

---

## Out of Scope

- Batch revoke/suspend (multi-select toolbar) — defer until usage data justifies it.
- Undo / restore flow — admin uses audit log + manual DB recovery if needed.
- Auto-promote alternate when slot frees up.
- Notifications to students (email/SMS) — separate workstream.

---

## Schema Changes

### `applications` table — 6 new columns

```python
# backend/app/models/application.py
revoked_at      = Column(DateTime(timezone=True), nullable=True)
revoked_by      = Column(Integer, ForeignKey("users.id"), nullable=True)
revoke_reason   = Column(Text, nullable=True)

suspended_at    = Column(DateTime(timezone=True), nullable=True)
suspended_by    = Column(Integer, ForeignKey("users.id"), nullable=True)
suspend_reason  = Column(Text, nullable=True)
```

### `payment_rosters` table — 1 new column

```python
# backend/app/models/payment_roster.py
excel_stale = Column(Boolean, default=False, nullable=False, server_default="false")
```

Set to `True` when an item is removed from a LOCKED roster (Section: Manual cleanup of LOCKED rosters). UI uses it to surface a "請重新匯出 Excel" hint.

### `quota_allocation_status` — two new string values

`applications.quota_allocation_status` is plain `String` (not a PostgreSQL enum). Two new values added by writing them in the application layer; no DDL change:

- `revoked`
- `suspended`

(Existing values: `allocated`, `rejected`, `null`.)

### Migration

One Alembic migration. All 7 `ADD COLUMN` statements wrapped in existence checks per project convention.

---

## Behavior Specification

### Revoke

| Step | What happens |
|---|---|
| 1 | Acquire row lock on the application (`SELECT ... FOR UPDATE`). |
| 2 | If `quota_allocation_status` is already `revoked` or `suspended`, return 409 Conflict. |
| 3 | If `quota_allocation_status != 'allocated'`, return 400. |
| 4 | Set `application.status = cancelled`, `quota_allocation_status = revoked`, `revoked_at`, `revoked_by`, `revoke_reason`. |
| 5 | Hard-delete this application's `PaymentRosterItem` rows in all rosters whose `status != LOCKED` (i.e., DRAFT/PROCESSING/COMPLETED). |
| 6 | For each affected roster, recompute `total_applications`, `qualified_count`, `total_amount`. |
| 7 | Write audit log entry `application.revoke` with `application_id`, `reason`, `affected_unlocked_rosters: [...]`. |

### Suspend

Identical to Revoke at the data layer, **except**:
- Step 4 writes `quota_allocation_status = suspended` + `suspended_*` fields.
- Step 7 writes action `application.suspend`.

The reason the action range is the same is that "removing from past LOCKED rosters" is admin-driven via the UI (next section), not automated. The split between 撤銷 and 停發 lives in:
- The `quota_allocation_status` value (drives the UI list grouping)
- The display styling on each LOCKED roster's detail page (warning vs informational)

### LOCKED rosters are never auto-modified

LOCKED rosters represent already-disbursed money. The service never deletes items from LOCKED rosters. Admin must do that explicitly via the per-row "從本造冊移除" button (Section: Manual cleanup of LOCKED rosters).

### Concurrency

The application row is locked with `with_for_update()` at the start of revoke/suspend. Two concurrent admin requests serialize; the second to land sees `quota_allocation_status` already set and returns 409.

---

## Backend API

All endpoints return the project-standard `ApiResponse` envelope (`{ success, message, data }`).

### POST `/api/v1/manual-distribution/applications/{application_id}/revoke`

```
Auth: require_admin
Body: { "reason": str (required, min_length=1, max_length=500) }
Response data:
{
  "application_id": int,
  "quota_allocation_status": "revoked",
  "revoked_at": ISO8601,
  "ranking_item_id": int,
  "affected_unlocked_rosters": [int, ...]
}
```

### POST `/api/v1/manual-distribution/applications/{application_id}/suspend`

Same shape; `quota_allocation_status = "suspended"`, `suspended_at`.

### GET `/api/v1/payment-rosters/{roster_id}/revoked-suspended`

Returns the list of students who would have appeared in this roster but were later revoked or suspended.

```
Auth: require_admin
Response data:
{
  "revoked": [
    {
      "application_id": int,
      "student_name": str,
      "student_id_number": str,
      "revoked_at": ISO8601,
      "revoke_reason": str
    }
  ],
  "suspended": [
    {
      "application_id": int,
      "student_name": str,
      "student_id_number": str,
      "suspended_at": ISO8601,
      "suspend_reason": str
    }
  ]
}
```

**Query logic**: revoke/suspend never modifies LOCKED roster items, so the original `PaymentRosterItem` rows of a LOCKED roster are an accurate snapshot of "students who were in this roster at lock time". The revoked/suspended ones are simply those whose linked `Application.quota_allocation_status` is now `revoked` or `suspended`:

```sql
SELECT pri.*, a.*
FROM payment_roster_items pri
JOIN applications a ON pri.application_id = a.id
WHERE pri.roster_id = :roster_id
  AND a.quota_allocation_status IN ('revoked', 'suspended')
```

Group by `quota_allocation_status` to split into the `revoked` / `suspended` arrays.

### DELETE `/api/v1/payment-rosters/{roster_id}/items/{item_id}`

```
Auth: require_admin
Body: { "reason": str (optional, max_length=500) }
```

Behavior:
1. Verify roster is `LOCKED` (return 400 otherwise — for non-LOCKED rosters, the item is already gone via revoke/suspend service).
2. Hard delete `PaymentRosterItem`.
3. Recompute roster `total_applications`, `qualified_count`, `total_amount`.
4. Set `roster.excel_stale = True`.
5. Write audit log `roster.item_removed_after_lock` with `roster_id`, `item_id`, `application_id`, `reason`, `removed_amount`.
6. Roster remains `LOCKED`.

---

## Service Layer

### `backend/app/services/manual_distribution_service.py`

Add two methods (use existing `AsyncSession` patterns):

```python
async def revoke_allocation(
    self, application_id: int, admin_user_id: int, reason: str
) -> dict: ...

async def suspend_allocation(
    self, application_id: int, admin_user_id: int, reason: str
) -> dict: ...
```

Both share an internal helper `_cancel_allocation(mode: Literal["revoke","suspend"], ...)` to avoid duplication.

### `backend/app/services/roster_service.py` (or new `roster_item_service.py`)

Add:

```python
def get_revoked_suspended_for_roster(self, roster_id: int) -> dict: ...

def remove_item_from_locked_roster(
    self, roster_id: int, item_id: int, admin_user_id: int, reason: str | None
) -> dict: ...
```

`roster_service.py` is currently synchronous (`get_sync_db`); keep that pattern for these new methods.

---

## Frontend UI

### Manual Distribution Panel — row action column

`frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx` (line ~1188-1212).

Replace the single ✕ button with two small side-by-side buttons:

```
┌──────┬──────┐
│ 撤   │ 停   │
└──────┴──────┘
```

| Button | Class | Tooltip | Disabled when |
|---|---|---|---|
| 撤 | `bg-red-100 text-red-700 border border-red-300 hover:bg-red-200` | 撤銷 | `quota_allocation_status !== 'allocated'` |
| 停 | `bg-orange-100 text-orange-700 border border-orange-300 hover:bg-orange-200` | 停發 | `quota_allocation_status !== 'allocated'` |

- Column width: `w-8` → `w-16`
- Column header: 「取消」→「動作」

### Confirmation dialogs

Two separate `AlertDialog` components. Confirm button stays `disabled` while `reason.trim().length === 0`.

**撤銷 dialog**:
```
標題：確認撤銷 {student_name} 的獎學金分配？

撤銷後：
• 此學生將從目前所有未鎖定造冊中移除
• 此學生申請狀態變更為「已取消」
• 已鎖定的歷史造冊需手動清除（清單會列在受影響造冊頁面提示）

撤銷原因（必填）：
[textarea, maxLength=500]

[取消]  [確認撤銷] ← red
```

**停發 dialog**:
```
標題：確認停發 {student_name} 的獎學金分配？

停發後：
• 此學生將從目前所有未鎖定造冊中移除
• 此學生申請狀態變更為「已取消」
• 已鎖定的歷史造冊不受影響（金額已發放保留）

停發原因（必填）：
[textarea, maxLength=500]

[取消]  [確認停發] ← orange
```

### PaymentRoster detail page — Status change notice

In `frontend/components/roster/RosterDetailDialog.tsx` (the existing payment-roster detail component), add a collapsible "狀態變更通知" panel at the top, visible **only when `roster.status === 'LOCKED'`**.

The panel pulls from `GET /api/v1/payment-rosters/{roster_id}/revoked-suspended` and renders two sub-sections:

```
┌─────────────────────────────────────────────────┐
│ ⚠️ 此造冊有 N 位學生被撤銷，請手動處理：         │
│   • 王小明 (B12345) — 撤銷於 2026-05-21          │
│     原因：違反獎學金規範                          │
│     [從本造冊移除]                                │
│   • 李大華 (B12346) — 撤銷於 2026-05-21          │
│     ...                                          │
│                                                  │
│ ℹ️ 此造冊有 N 位學生被停發（僅資訊）：           │
│   • 陳四 (B12348) — 停發於 2026-05-20            │
│     原因：休學                                    │
└─────────────────────────────────────────────────┘
```

- 撤銷 section: red border, warning icon. Each row has a `[從本造冊移除]` button → confirmation dialog → `DELETE /payment-rosters/{id}/items/{item_id}`.
- 停發 section: blue/grey border, info icon. No per-row action button (informational only).
- Both sections collapsible; default expanded if count > 0.
- If `revoked.length === 0` AND `suspended.length === 0`, the entire panel is hidden.

### Excel stale hint

When `roster.excel_stale === true`, show a banner at the top of the roster detail page:
```
⚠️ 造冊資料已變更，請重新匯出 Excel    [重新匯出 Excel]
```
"重新匯出 Excel" uses the existing roster Excel export flow (out of scope here). On successful re-export, set `excel_stale = false`.

---

## Audit Log Actions

| action | target_type | details |
|---|---|---|
| `application.revoke` | `Application` | `{ reason, affected_unlocked_rosters: [int, ...] }` |
| `application.suspend` | `Application` | `{ reason, affected_unlocked_rosters: [int, ...] }` |
| `roster.item_removed_after_lock` | `PaymentRoster` | `{ item_id, application_id, reason, removed_amount }` |

Uses existing `audit_logs` table via existing audit helpers.

---

## Error Handling & Edge Cases

| Scenario | Behavior |
|---|---|
| Repeat revoke/suspend on same application | 409 Conflict — message includes prior action and timestamp |
| Application with `quota_allocation_status != 'allocated'` | 400 Bad Request — UI buttons also disabled, this is server-side defense |
| Revoke after suspend (or vice versa) | 409 Conflict — no undo in this iteration |
| Revoke when no unlocked roster items exist | Success; `affected_unlocked_rosters: []` |
| Remove last item from LOCKED roster | Allowed; `qualified_count = 0` roster permitted; roster stays LOCKED |
| Reason contains hostile payload | Pydantic `constr(min_length=1, max_length=500)`; frontend escapes display |
| Two admins act concurrently | DB row lock (`with_for_update`) on `applications`; second request → 409 |
| DELETE LOCKED-roster-item by non-admin | 403 (via `require_admin`) |
| DELETE on non-LOCKED roster | 400 — for non-LOCKED rosters the item is already gone via revoke/suspend service |

---

## Testing

### Backend unit (`backend/tests/test_revoke_suspend.py`)

- `test_revoke_updates_status_and_removes_unlocked_items`
- `test_revoke_leaves_locked_rosters_untouched`
- `test_suspend_updates_status_and_removes_unlocked_items`
- `test_suspend_leaves_locked_rosters_untouched`
- `test_revoke_writes_audit_log_with_affected_rosters`
- `test_revoke_twice_returns_conflict`
- `test_suspend_then_revoke_returns_conflict`
- `test_revoke_non_allocated_returns_400`
- `test_reason_required_returns_422`
- `test_revoke_recomputes_unlocked_roster_totals`

### Backend service (`backend/tests/test_roster_item_removal.py`)

- `test_remove_item_from_locked_roster_updates_totals_and_sets_excel_stale`
- `test_remove_item_from_unlocked_roster_returns_400`
- `test_remove_item_writes_audit_log`
- `test_remove_item_keeps_roster_locked`

### Backend integration (`backend/tests/test_revoke_suspend_flow.py`)

End-to-end: finalize → generate roster A → lock roster A → generate roster B (DRAFT) → revoke student → assert:
- Roster A still contains the student's item
- `GET /revoked-suspended` for roster A returns the student under `revoked`
- Roster B no longer contains the student's item
- `application.status == 'cancelled'`, `quota_allocation_status == 'revoked'`
- Admin removes item from LOCKED roster A → roster A `qualified_count` decremented, `excel_stale = True`, roster still LOCKED

### Frontend Playwright E2E (`frontend/e2e/admin/revoke-suspend.spec.ts`)

- Admin login → Manual Distribution Panel → find allocated student → click 撤 → fill reason → confirm → row shows 已撤銷 indicator
- Admin opens a LOCKED roster detail page → sees 撤銷名單 panel with student's name → clicks 從本造冊移除 → confirm → row disappears, "請重新匯出 Excel" banner appears
- Pre-finalize student row: both 撤/停 buttons disabled
- Empty reason → 確認 button disabled

---

## Files Affected

| File | Change |
|---|---|
| `backend/app/models/application.py` | + 6 columns (revoke/suspend metadata) |
| `backend/app/models/payment_roster.py` | + `excel_stale` boolean |
| `backend/alembic/versions/xxx_revoke_suspend.py` | New migration: 7 ADD COLUMN with existence checks |
| `backend/app/services/manual_distribution_service.py` | + `revoke_allocation`, `suspend_allocation` |
| `backend/app/services/roster_service.py` | + `get_revoked_suspended_for_roster`, `remove_item_from_locked_roster` |
| `backend/app/api/v1/endpoints/manual_distribution.py` | + 2 POST endpoints |
| `backend/app/api/v1/endpoints/payment_rosters.py` | + 1 GET + 1 DELETE endpoint |
| `backend/app/schemas/application.py` | + `RevokeRequest`, `SuspendRequest` schemas |
| `backend/app/schemas/payment_roster.py` | + `RevokedSuspendedListResponse`, `RemoveLockedItemRequest` schemas |
| `frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx` | Row column rewrite + 2 AlertDialogs |
| `frontend/components/roster/RosterDetailDialog.tsx` | + 狀態變更通知 panel, excel_stale banner |
| `frontend/lib/api/modules/manual-distribution.ts` | + `revoke`, `suspend` API calls |
| `frontend/lib/api/modules/payment-rosters.ts` | + `getRevokedSuspended`, `removeItemFromLockedRoster` API calls |
| `frontend/lib/api/generated/schema.d.ts` | Regenerate via `npm run api:generate` |
