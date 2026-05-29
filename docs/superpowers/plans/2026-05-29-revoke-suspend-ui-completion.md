# Revoke / Suspend UI Completion + Refinement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the partially-shipped 撤銷/停發 feature: remove the leftover ✕「取消」column, build the missing 停發 (suspend) UI, and let admins remove 停發 students from locked rosters — all via a shared dialog.

**Architecture:** Frontend-only (backend endpoints + service + schemas already shipped). A new shared `AllocationActionDialog` (built on shadcn `Dialog`+`Select`, following the existing exclude-dialog precedent) drives both 撤銷 (free-text reason) and 停發 (dropdown 休/退/畢 + note). `ManualDistributionPanel` drops the ✕ column and renders `[撤][停]`. `RosterDetailDialog` extracts a `RevokedSuspendedSection` used for both lists, with a remove button now on both.

**Tech Stack:** Next.js / React, TypeScript, jest (unit), Playwright (e2e), shadcn/ui.

**Spec:** `docs/superpowers/specs/2026-05-29-revoke-suspend-ui-completion-design.md`

---

## Setup (run once in the worktree before Task 1)

This is a fresh git worktree with no `node_modules`. Install frontend deps:

```bash
cd frontend && npm install
```

Sanity-check the test runner works (existing suite should pass):

```bash
cd frontend && npx jest lib/api/modules/__tests__/manual-distribution.test.ts --watchAll=false
```
Expected: PASS (14-method invariant + existing revoke tests green). If `npm install` is blocked or jest can't run in this environment, report it before proceeding — Tasks 1, 2, 4 depend on jest.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `frontend/lib/api/modules/manual-distribution.ts` | API client methods | **Modify** — add `suspendAllocation` |
| `frontend/lib/api/modules/__tests__/manual-distribution.test.ts` | API client tests | **Modify** — add suspend test, bump method count |
| `frontend/components/admin/manual-distribution/AllocationActionDialog.tsx` | Shared revoke/suspend confirm dialog | **Create** |
| `frontend/components/admin/manual-distribution/__tests__/AllocationActionDialog.test.tsx` | Dialog unit tests | **Create** |
| `frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx` | Distribution table | **Modify** — remove ✕ column, `[撤][停]`, wire shared dialog |
| `frontend/components/roster/RevokedSuspendedSection.tsx` | Reusable revoked/suspended list block | **Create** |
| `frontend/components/roster/RosterDetailDialog.tsx` | Locked-roster detail | **Modify** — use section, suspend gets remove button, drop「（僅資訊）」 |
| `frontend/e2e/specs/revoke-suspend.spec.ts` | E2E | **Create** |

---

## Task 1: Add `suspendAllocation` API method

**Files:**
- Modify: `frontend/lib/api/modules/manual-distribution.ts` (after `revokeAllocation`, ~line 585)
- Test: `frontend/lib/api/modules/__tests__/manual-distribution.test.ts`

- [ ] **Step 1: Write the failing test**

In `manual-distribution.test.ts`, (a) update the method-count invariant from 14 to 15 and insert `"suspendAllocation"` into the sorted array, and (b) add a behavior test. The array currently ends:
```ts
      "importReceivedMonths",
      "previewDistribution",
      "restoreFromHistory",
      "revokeAllocation",
    ]);
```
Change the `it("module exposes exactly 14 methods", ...)` block to `15` and make the array:
```ts
    expect(Object.keys(api).sort()).toEqual([
      "allocate",
      "finalize",
      "generateRostersFromDistribution",
      "getAutoAllocatePreview",
      "getAvailableCombinations",
      "getDistributionSummary",
      "getHistory",
      "getQuotaStatus",
      "getState",
      "getStudents",
      "importReceivedMonths",
      "previewDistribution",
      "restoreFromHistory",
      "revokeAllocation",
      "suspendAllocation",
    ]);
```
Then add a behavior test next to the existing `revokeAllocation` test (mirror its style — it stubs `global.fetch`):
```ts
  it("suspendAllocation POSTs reason to the suspend endpoint", async () => {
    const fetchMock = vi.fn
      ? undefined
      : undefined; // placeholder removed below
    const mockFetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, message: "已停發", data: {} }),
    });
    global.fetch = mockFetch as unknown as typeof fetch;
    const api = createManualDistributionApi();

    const res = await api.suspendAllocation(42, "休學：已辦理 114-2 休學");

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/v1/manual-distribution/applications/42/suspend",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ reason: "休學：已辦理 114-2 休學" }),
      })
    );
    expect(res.success).toBe(true);
  });
```
> NOTE: match the EXACT mocking style of the existing `revokeAllocation` test in this file (it may already define a `mockFetch` helper / `beforeEach`). Read that test first and copy its setup verbatim, only swapping `revoke`→`suspend` and the reason string. Delete the stray `vi.fn` placeholder line above — this project uses jest, not vitest.

- [ ] **Step 2: Run the tests — verify they fail**

```bash
cd frontend && npx jest lib/api/modules/__tests__/manual-distribution.test.ts --watchAll=false
```
Expected: FAIL — method count 15 ≠ 14 / `api.suspendAllocation is not a function`.

- [ ] **Step 3: Implement `suspendAllocation`**

In `manual-distribution.ts`, immediately after the `revokeAllocation` method's closing `},` (~line 585), add (mirrors revoke's raw-fetch mechanism exactly):
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
      try {
        body = await response.json();
      } catch {
        // ignore parse error
      }
      if (!response.ok) {
        const b = body as { detail?: string; message?: string } | null;
        return {
          success: false,
          message: b?.detail || b?.message || "停發失敗",
          data: undefined,
        };
      }
      return body as ApiResponse<unknown>;
    },
```

- [ ] **Step 4: Run the tests — verify they pass**

```bash
cd frontend && npx jest lib/api/modules/__tests__/manual-distribution.test.ts --watchAll=false
```
Expected: PASS (15 methods + suspend behavior test green).

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api/modules/manual-distribution.ts frontend/lib/api/modules/__tests__/manual-distribution.test.ts
git commit -m "feat(manual-distribution): add suspendAllocation api method"
```

---

## Task 2: Create the shared `AllocationActionDialog`

**Files:**
- Create: `frontend/components/admin/manual-distribution/AllocationActionDialog.tsx`
- Test: `frontend/components/admin/manual-distribution/__tests__/AllocationActionDialog.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `__tests__/AllocationActionDialog.test.tsx`:
```tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AllocationActionDialog } from "../AllocationActionDialog";
import { apiClient } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  apiClient: {
    manualDistribution: {
      revokeAllocation: jest.fn().mockResolvedValue({ success: true }),
      suspendAllocation: jest.fn().mockResolvedValue({ success: true }),
    },
  },
}));

const target = { applicationId: 7, studentName: "王小明" };

describe("AllocationActionDialog", () => {
  beforeEach(() => jest.clearAllMocks());

  it("revoke mode: free-text reason, placeholder 違反獎學金要點, confirm disabled when empty", () => {
    render(
      <AllocationActionDialog mode="revoke" target={target} onClose={() => {}} onConfirmed={() => {}} />
    );
    expect(screen.getByPlaceholderText("違反獎學金要點")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "確認撤銷" })).toBeDisabled();
  });

  it("revoke mode: enabling + confirm calls revokeAllocation with trimmed reason", async () => {
    const onConfirmed = jest.fn();
    render(
      <AllocationActionDialog mode="revoke" target={target} onClose={() => {}} onConfirmed={onConfirmed} />
    );
    fireEvent.change(screen.getByPlaceholderText("違反獎學金要點"), {
      target: { value: "  違反第三條  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "確認撤銷" }));
    await waitFor(() =>
      expect(apiClient.manualDistribution.revokeAllocation).toHaveBeenCalledWith(7, "違反第三條")
    );
    expect(onConfirmed).toHaveBeenCalledWith("王小明");
  });

  it("suspend mode: composes 「label：note」 and calls suspendAllocation", async () => {
    const onConfirmed = jest.fn();
    render(
      <AllocationActionDialog mode="suspend" target={target} onClose={() => {}} onConfirmed={onConfirmed} />
    );
    // default option is 休學; add a note
    fireEvent.change(screen.getByPlaceholderText("選填"), {
      target: { value: "已辦理休學" },
    });
    fireEvent.click(screen.getByRole("button", { name: "確認停發" }));
    await waitFor(() =>
      expect(apiClient.manualDistribution.suspendAllocation).toHaveBeenCalledWith(
        7,
        "休學：已辦理休學"
      )
    );
    expect(onConfirmed).toHaveBeenCalledWith("王小明");
  });
});
```
> If the shadcn `Select` does not expose options by accessible name in jsdom (Radix portals can be awkward in tests), keep the suspend test focused on the default option (休學) + note path as written above — do not try to open the dropdown in jsdom. The 其他-requires-note behavior is covered by e2e (Task 5).

- [ ] **Step 2: Run the test — verify it fails**

```bash
cd frontend && npx jest components/admin/manual-distribution/__tests__/AllocationActionDialog.test.tsx --watchAll=false
```
Expected: FAIL — module `../AllocationActionDialog` not found.

- [ ] **Step 3: Implement the component**

Create `AllocationActionDialog.tsx` (modeled on the exclude-dialog at `RosterDetailDialog.tsx:606-700`):
```tsx
"use client";

import { useState } from "react";
import { apiClient } from "@/lib/api";
import { logger } from "@/lib/utils/logger";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Loader2 } from "lucide-react";

export type AllocationMode = "revoke" | "suspend";

export interface AllocationActionTarget {
  applicationId: number;
  studentName: string;
}

interface AllocationActionDialogProps {
  mode: AllocationMode;
  target: AllocationActionTarget | null;
  onClose: () => void;
  /** Parent runs fetchData + success messaging. */
  onConfirmed: (studentName: string) => void;
}

const SUSPEND_OPTIONS = ["休學", "退學", "畢業", "其他"] as const;

export function AllocationActionDialog({
  mode,
  target,
  onClose,
  onConfirmed,
}: AllocationActionDialogProps) {
  const isRevoke = mode === "revoke";
  const [revokeReason, setRevokeReason] = useState("");
  const [suspendOption, setSuspendOption] = useState<string>("休學");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const reset = () => {
    setRevokeReason("");
    setSuspendOption("休學");
    setNote("");
  };

  const handleClose = () => {
    if (submitting) return;
    reset();
    onClose();
  };

  const composedReason = isRevoke
    ? revokeReason.trim()
    : note.trim()
      ? `${suspendOption}：${note.trim()}`
      : suspendOption;

  const confirmDisabled =
    submitting ||
    (isRevoke
      ? revokeReason.trim().length === 0
      : suspendOption === "其他" && note.trim().length === 0);

  const handleConfirm = async () => {
    if (!target || confirmDisabled) return;
    setSubmitting(true);
    try {
      const resp = isRevoke
        ? await apiClient.manualDistribution.revokeAllocation(
            target.applicationId,
            composedReason
          )
        : await apiClient.manualDistribution.suspendAllocation(
            target.applicationId,
            composedReason
          );
      if (resp.success) {
        const name = target.studentName;
        reset();
        onConfirmed(name);
      } else {
        logger.error(`${mode} failed`, { message: resp.message });
        alert(resp.message || (isRevoke ? "撤銷失敗" : "停發失敗"));
      }
    } catch (err) {
      logger.error(`${mode} error`, { err });
      alert(isRevoke ? "撤銷時發生錯誤" : "停發時發生錯誤");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={target !== null} onOpenChange={open => !open && handleClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{isRevoke ? "撤銷獎學金分發" : "停發獎學金分發"}</DialogTitle>
          <DialogDescription>
            {target && (
              <>
                {isRevoke ? "確定要撤銷 " : "確定要停發 "}
                <strong>{target.studentName}</strong>
                {" 的獎學金分發嗎？此操作將從未鎖定造冊中移除該學生，並標記申請為"}
                {isRevoke ? "已撤銷。" : "已停發。"}
              </>
            )}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {isRevoke ? (
            <div className="space-y-2">
              <Label htmlFor="revoke-reason">撤銷原因</Label>
              <Textarea
                id="revoke-reason"
                value={revokeReason}
                onChange={e => setRevokeReason(e.target.value)}
                placeholder="違反獎學金要點"
                rows={3}
                maxLength={500}
                disabled={submitting}
              />
            </div>
          ) : (
            <>
              <div className="space-y-2">
                <Label htmlFor="suspend-option">停發原因</Label>
                <Select
                  value={suspendOption}
                  onValueChange={setSuspendOption}
                  disabled={submitting}
                >
                  <SelectTrigger id="suspend-option">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SUSPEND_OPTIONS.map(o => (
                      <SelectItem key={o} value={o}>
                        {o}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="suspend-note">
                  補充說明
                  {suspendOption === "其他" && (
                    <span className="text-red-500 ml-1">*</span>
                  )}
                </Label>
                <Textarea
                  id="suspend-note"
                  value={note}
                  onChange={e => setNote(e.target.value)}
                  placeholder={
                    suspendOption === "其他"
                      ? "選擇「其他」時必填，請說明原因"
                      : "選填"
                  }
                  rows={3}
                  maxLength={400}
                  disabled={submitting}
                />
              </div>
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleClose} disabled={submitting}>
            取消
          </Button>
          <Button
            variant="destructive"
            onClick={handleConfirm}
            disabled={confirmDisabled}
          >
            {submitting ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
            {isRevoke ? "確認撤銷" : "確認停發"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 4: Run the test — verify it passes**

```bash
cd frontend && npx jest components/admin/manual-distribution/__tests__/AllocationActionDialog.test.tsx --watchAll=false
```
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/components/admin/manual-distribution/AllocationActionDialog.tsx frontend/components/admin/manual-distribution/__tests__/AllocationActionDialog.test.tsx
git commit -m "feat(manual-distribution): shared AllocationActionDialog for revoke/suspend"
```

---

## Task 3: Wire dialog into `ManualDistributionPanel`, remove ✕, add 停

**Files:**
- Modify: `frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx`

This task is a refactor (no new unit test — verified by lint/typecheck + existing tests + Task 5 e2e). Work in order:

- [ ] **Step 1: Import the shared dialog**

Add near the other `@/components/...` imports (top of file, ~line 47):
```tsx
import {
  AllocationActionDialog,
  type AllocationMode,
} from "@/components/admin/manual-distribution/AllocationActionDialog";
```

- [ ] **Step 2: Replace revoke state with a single action target**

Find (~lines 205-210):
```tsx
  const [revokeTarget, setRevokeTarget] = useState<{
    applicationId: number;
    studentName: string;
  } | null>(null);
  const [revokeReason, setRevokeReason] = useState("");
  const [isRevoking, setIsRevoking] = useState(false);
```
Replace with:
```tsx
  const [action, setAction] = useState<{
    mode: AllocationMode;
    applicationId: number;
    studentName: string;
  } | null>(null);
```

- [ ] **Step 3: Delete the `handleRevoke` function**

Delete the entire `handleRevoke` function (~lines 583-611, from `const handleRevoke = async () => {` through its closing `};`). Its logic now lives in the dialog + the `onConfirmed` callback (Step 6).

- [ ] **Step 4: Delete the ✕ "取消此學生的分配" column**

Delete the whole `<td>` block that starts with the comment `{/* Cancel allocation button */}` (~lines 1404-1428, through the `</td>` that closes it). Do **not** touch the `curAlloc` variable (still used by the checkbox columns) or the checkbox-uncheck path at ~1487.

- [ ] **Step 5: Render `[撤][停]` in the persisted-allocation action column**

Find the revoke action column (~lines 1573-1593):
```tsx
                                <td className="px-1 py-1.5 border-r border-slate-100 text-center">
                                  {student.allocated_sub_type ? (
                                    <button
                                      title="撤銷此學生獎學金"
                                      onClick={() => {
                                        setRevokeTarget({
                                          applicationId: student.application_id,
                                          studentName: student.student_name,
                                        });
                                        setRevokeReason("");
                                      }}
                                      className="px-2 py-0.5 text-[11px] bg-red-50 text-red-600 hover:bg-red-100 rounded border border-red-200 cursor-pointer transition-colors"
                                    >
                                      撤
                                    </button>
                                  ) : (
                                    <span className="text-[10px] text-slate-300">
                                      —
                                    </span>
                                  )}
                                </td>
```
Replace with:
```tsx
                                <td className="px-1 py-1.5 border-r border-slate-100 text-center">
                                  {student.allocated_sub_type ? (
                                    <div className="flex items-center justify-center gap-1">
                                      <button
                                        title="撤銷此學生獎學金"
                                        onClick={() =>
                                          setAction({
                                            mode: "revoke",
                                            applicationId: student.application_id,
                                            studentName: student.student_name,
                                          })
                                        }
                                        className="px-2 py-0.5 text-[11px] bg-red-50 text-red-600 hover:bg-red-100 rounded border border-red-200 cursor-pointer transition-colors"
                                      >
                                        撤
                                      </button>
                                      <button
                                        title="停發此學生獎學金"
                                        onClick={() =>
                                          setAction({
                                            mode: "suspend",
                                            applicationId: student.application_id,
                                            studentName: student.student_name,
                                          })
                                        }
                                        className="px-2 py-0.5 text-[11px] bg-orange-50 text-orange-600 hover:bg-orange-100 rounded border border-orange-200 cursor-pointer transition-colors"
                                      >
                                        停
                                      </button>
                                    </div>
                                  ) : (
                                    <span className="text-[10px] text-slate-300">
                                      —
                                    </span>
                                  )}
                                </td>
```

- [ ] **Step 6: Replace the inline revoke `AlertDialog` with the shared dialog**

Find the revoke dialog block (~lines 1890-1923), from the comment `{/* Revoke allocation dialog */}` through `</AlertDialog>`. Replace the entire block with:
```tsx
    {/* Revoke / Suspend allocation dialog */}
    <AllocationActionDialog
      mode={action?.mode ?? "revoke"}
      target={
        action
          ? { applicationId: action.applicationId, studentName: action.studentName }
          : null
      }
      onClose={() => setAction(null)}
      onConfirmed={async studentName => {
        const mode = action?.mode;
        setAction(null);
        await fetchData();
        // Set success message AFTER fetchData so it isn't cleared by
        // fetchData's own setSaveMessage(null) (preserves the race fix
        // from commit 2dd0f611).
        setSaveMessage({
          type: "success",
          text: `已${mode === "suspend" ? "停發" : "撤銷"} ${studentName} 的獎學金分發`,
        });
      }}
    />
```

- [ ] **Step 7: Verify — lint, typecheck, existing tests**

```bash
cd frontend && npx tsc --noEmit && npm run lint && npx jest --watchAll=false
```
Expected: no TS errors; lint clean; jest green. Grep to confirm the leftovers are gone:
```bash
grep -n "取消此學生的分配\|revokeTarget\|setRevokeReason\|isRevoking\|handleRevoke" frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx
```
Expected: no matches.

- [ ] **Step 8: Commit**

```bash
git add frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx
git commit -m "feat(manual-distribution): remove ✕ column, add 撤/停 buttons via shared dialog"
```

---

## Task 4: `RosterDetailDialog` — extract section, suspend gets remove button

**Files:**
- Create: `frontend/components/roster/RevokedSuspendedSection.tsx`
- Modify: `frontend/components/roster/RosterDetailDialog.tsx`

- [ ] **Step 1: Create the reusable section component**

Create `frontend/components/roster/RevokedSuspendedSection.tsx`:
```tsx
import type { RevokedSuspendedEntry } from "@/lib/api/modules/payment-rosters";

interface RevokedSuspendedSectionProps {
  kind: "revoked" | "suspended";
  entries: RevokedSuspendedEntry[];
  removingItemId: number | null;
  onRemove: (itemId: number, studentName: string) => void;
}

export function RevokedSuspendedSection({
  kind,
  entries,
  removingItemId,
  onRemove,
}: RevokedSuspendedSectionProps) {
  if (entries.length === 0) return null;
  const isRevoked = kind === "revoked";
  const verb = isRevoked ? "撤銷" : "停發";

  return (
    <details
      open
      className={
        isRevoked
          ? "border border-red-300 bg-red-50 rounded p-3"
          : "border border-slate-300 bg-slate-50 rounded p-3"
      }
    >
      <summary
        className={
          isRevoked
            ? "text-red-800 font-semibold cursor-pointer text-sm"
            : "text-slate-700 font-semibold cursor-pointer text-sm"
        }
      >
        {isRevoked ? "⚠️ " : "ℹ️ "}此造冊有 {entries.length} 位學生被{verb}，請手動處理
      </summary>
      <ul className="mt-2 space-y-2">
        {entries.map(s => (
          <li
            key={s.application_id}
            className="text-sm flex items-start justify-between gap-3"
          >
            <div>
              <div>
                <span className="font-medium">{s.student_name}</span>
                <span className="text-slate-500"> ({s.student_id_number})</span>
                <span className="text-xs text-slate-500 ml-2">
                  {verb}於 {new Date(s.event_at).toLocaleDateString()}
                </span>
              </div>
              {s.reason && (
                <div className="text-xs text-slate-600">原因：{s.reason}</div>
              )}
            </div>
            {s.item_id !== null && (
              <button
                onClick={() => onRemove(s.item_id!, s.student_name)}
                disabled={removingItemId === s.item_id}
                className="px-2 py-1 text-xs bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50 whitespace-nowrap"
              >
                {removingItemId === s.item_id ? "處理中…" : "從本造冊移除"}
              </button>
            )}
          </li>
        ))}
      </ul>
    </details>
  );
}
```
> Confirm `RevokedSuspendedEntry` is exported from `payment-rosters.ts` (it is, at ~line 18). If not exported, add `export`.

- [ ] **Step 2: Use the section in `RosterDetailDialog`**

Add the import near the other component imports:
```tsx
import { RevokedSuspendedSection } from "@/components/roster/RevokedSuspendedSection";
```
Replace the two `<details>` blocks (~lines 419-503 — the `{(revokedSuspended.revoked.length > 0 || revokedSuspended.suspended.length > 0) && (` wrapper and both `<details>` inside it) with:
```tsx
            {(revokedSuspended.revoked.length > 0 ||
              revokedSuspended.suspended.length > 0) && (
              <div className="mb-4 space-y-3">
                <RevokedSuspendedSection
                  kind="revoked"
                  entries={revokedSuspended.revoked}
                  removingItemId={removingItemId}
                  onRemove={handleRemoveLockedItem}
                />
                <RevokedSuspendedSection
                  kind="suspended"
                  entries={revokedSuspended.suspended}
                  removingItemId={removingItemId}
                  onRemove={handleRemoveLockedItem}
                />
              </div>
            )}
```
This removes the old「（僅資訊）」suspended summary and gives suspended rows the「從本造冊移除」button (same `handleRemoveLockedItem`).

- [ ] **Step 3: Verify — lint, typecheck, grep**

```bash
cd frontend && npx tsc --noEmit && npm run lint
grep -n "僅資訊" frontend/components/roster/RosterDetailDialog.tsx
```
Expected: no TS errors; lint clean; `僅資訊` → no matches.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/roster/RevokedSuspendedSection.tsx frontend/components/roster/RosterDetailDialog.tsx
git commit -m "feat(roster): suspended students get 從本造冊移除 button; extract RevokedSuspendedSection"
```

---

## Task 5: E2E spec (new)

**Files:**
- Create: `frontend/e2e/specs/revoke-suspend.spec.ts`

Requires the full dev stack running (`docker compose -f docker-compose.dev.yml up`) and seeded data. E2E specs live under `frontend/e2e/specs/`; there is no existing revoke/suspend spec.

- [ ] **Step 1: Read an existing spec for the login/navigation pattern**

```bash
ls frontend/e2e/specs/ && sed -n '1,60p' frontend/e2e/helpers/*.ts 2>/dev/null | head -120
```
Pick the closest admin/manual-distribution spec and reuse its login helper + navigation to the Manual Distribution Panel verbatim.

- [ ] **Step 2: Write the spec**

Create `frontend/e2e/specs/revoke-suspend.spec.ts`. Use the helper-based login/navigation from Step 1; the feature-specific assertions are:
```ts
import { test, expect } from "@playwright/test";
// import { loginAsAdmin, gotoManualDistribution } from "../helpers/...";  // use the real helper paths from Step 1

test.describe("revoke / suspend distribution", () => {
  test("✕ 取消 column is gone; allocated rows show 撤 and 停", async ({ page }) => {
    // loginAsAdmin(page); gotoManualDistribution(page, <seeded scholarship/year/sem>);
    await expect(page.getByTitle("取消此學生的分配")).toHaveCount(0);
    await expect(page.getByTitle("撤銷此學生獎學金").first()).toBeVisible();
    await expect(page.getByTitle("停發此學生獎學金").first()).toBeVisible();
  });

  test("停發 dialog: dropdown + note, confirm 停發", async ({ page }) => {
    // ...navigate to an allocated student row...
    await page.getByTitle("停發此學生獎學金").first().click();
    await expect(page.getByRole("dialog")).toContainText("停發獎學金分發");
    // default 休學 selected → confirm enabled
    await expect(page.getByRole("button", { name: "確認停發" })).toBeEnabled();
    await page.getByRole("button", { name: "確認停發" }).click();
    await expect(page.getByText(/已停發 .* 的獎學金分發/)).toBeVisible();
  });

  test("撤銷 dialog placeholder 違反獎學金要點; empty reason disables confirm", async ({ page }) => {
    await page.getByTitle("撤銷此學生獎學金").first().click();
    await expect(page.getByPlaceholder("違反獎學金要點")).toBeVisible();
    await expect(page.getByRole("button", { name: "確認撤銷" })).toBeDisabled();
  });

  test("locked roster: 停發 student shows 從本造冊移除", async ({ page }) => {
    // ...open a LOCKED roster detail that contains a suspended student...
    await expect(page.getByText(/位學生被停發，請手動處理/)).toBeVisible();
    await expect(page.getByRole("button", { name: "從本造冊移除" }).first()).toBeVisible();
  });
});
```
> Fill the `// ...` navigation using the seeded fixtures + helpers identified in Step 1. The text/title selectors above are exact matches for the strings introduced in Tasks 2-4.

- [ ] **Step 3: Run the spec**

```bash
cd frontend && npx playwright test e2e/specs/revoke-suspend.spec.ts
```
Expected: PASS (stack must be up). If the stack isn't available in this environment, report and defer the run, but still commit the spec.

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e/specs/revoke-suspend.spec.ts
git commit -m "test(e2e): revoke/suspend distribution + locked-roster suspend removal"
```

---

## Task 6: Verify backend coverage + regenerate types (verify-only)

- [ ] **Step 1: Confirm suspend removal coverage exists**

```bash
grep -n "suspend" backend/app/tests/test_roster_item_removal_service.py
```
If a suspended-application removal case exists, no change. If **only** revoked is covered, add a parallel test that sets `quota_allocation_status="suspended"` and asserts `remove_item_from_locked_roster` deletes the item + sets `excel_stale` (copy the revoked case in that file, swap the status). Run:
```bash
cd backend && python -m pytest app/tests/test_roster_item_removal_service.py -q
```
Expected: PASS.

- [ ] **Step 2: Regenerate OpenAPI types (expected no-op)**

No backend schema changed, so this should produce no diff. Only run if the backend is reachable on `localhost:8000`:
```bash
cd frontend && npm run api:generate && git diff --stat lib/api/generated/schema.d.ts
```
Expected: no diff. If a diff appears, investigate (it shouldn't).

- [ ] **Step 3: Commit (only if anything changed)**

```bash
git add -A && git commit -m "test(roster): cover suspended-application locked-roster removal" || echo "nothing to commit"
```

---

## Self-Review (completed by plan author)

- **Spec coverage:** G1 (Task 3 Step 4), G2 (Tasks 1-3), G3 (Task 2 revoke placeholder), C1 (Task 2 suspend dropdown), C2 (Task 4 suspend remove button + drop 僅資訊), R1 (Tasks 2 & 4 extraction). ✓
- **Placeholders:** the one `vi.fn` line in Task 1 Step 1 is explicitly flagged for deletion (jest, not vitest); the e2e `// ...` navigation is explicitly delegated to existing helpers (Task 5 Step 1) because helper APIs weren't read. No other placeholders.
- **Type consistency:** `AllocationMode` / `AllocationActionTarget` defined in Task 2, imported in Task 3. `RevokedSuspendedEntry` reused from `payment-rosters.ts`. `suspendAllocation(application_id, reason)` signature matches across Tasks 1, 2. Composed-reason format `「label：note」` consistent (Task 2 component + Task 5 e2e expectation `休學：已辦理休學`).
