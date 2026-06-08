# 造冊 顯示已移除者 + 回復 + 統一操作紀錄 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In 造冊「查看名單」(`RosterDetailDialog`), show people who were removed from a roster, let an admin 回復 (restore) them, and record every 移除/新增/回復 in one roster-scoped audit trail the admin can view.

**Architecture:** Convert the two hard-delete removal paths (比對分發 移除孤兒、鎖定後移除) to **soft-delete** (`is_included=False`), matching the existing 排除 path, so every removed row survives and is restorable. Route all item-level mutations (remove/add/restore) into a single `RosterAuditLog` trail. Frontend stops filtering out removed items, renders them greyed with a 回復 button, and adds an 操作紀錄 tab.

**Tech Stack:** FastAPI + SQLAlchemy (sync `RosterService`, async endpoints for exclude), PostgreSQL, Pydantic v2, Next.js + React + TypeScript, jest, pytest (`db_sync` fixtures).

**Spec:** `docs/superpowers/specs/2026-06-08-roster-removed-restore-audit-design.md`

---

## Key facts established during design (read before starting)

- **No DB unique constraint** on `payment_roster_items (roster_id, application_id)` — only plain indexes. So soft-delete never collides, but code must avoid creating a 2nd row for an app that already has one.
- Excel export, `_recompute_roster_totals_sync`, `received_months_service`, `student_scholarship_history_service` **already filter `is_included`** → converting hard-delete to soft-delete needs **no changes** there; removed people already drop out of Excel and month-counts.
- The generic `AuditLog` rows written today by `reconcile_roster` / `remove_item_from_locked_roster` (`resource_type="payment_roster"`) are **write-only — no endpoint reads them**. The plan **replaces** them with `RosterAuditLog` writes.
- `GET /{roster_id}/audit-logs` and `RosterAuditLogResponse` currently reference `log.created_by_user_id`, **a column that does not exist** on `RosterAuditLog` (it has `user_id`/`user_name`/`user_role`). This endpoint is unused today and is latently broken; Task 2 fixes it because the new panel calls it.
- `test_roster_enums_contract.py` does **not** pin `RosterAuditAction` count, so adding `ITEM_RESTORE` won't trip it.
- `RosterService` is **sync** and tested with the `db_sync` fixture (see `test_roster_item_removal_service.py`). New service tests follow that style.

## Running tests (dev container caveat)

`RosterService` tests run in the backend dev container:
```bash
docker compose -f docker-compose.dev.yml exec backend \
  python -m pytest app/tests/<file> -p no:cacheprovider -v
```
**Caveat (from project memory):** the dev container may mount the MAIN repo or a different worktree, not this worktree. Before running, confirm the container sees your edits (`docker compose -f docker-compose.dev.yml exec backend grep -n ITEM_RESTORE app/models/roster_audit.py`). If it does not, either (a) run the stack from this worktree, or (b) run local pytest in the worktree with inline env vars `DATABASE_URL`, `DATABASE_URL_SYNC`, `SECRET_KEY`, `MINIO_*` (Settings has no defaults / no host `.env`).

## Lint gates (run before each backend commit)

```bash
uvx --from "black==26.3.1" black --check --line-length=120 backend/app
flake8 app --select=B904,B014 --max-line-length=120   # restore endpoint uses `raise ... from e`
```

---

## File Structure

**Backend**
- `backend/app/models/roster_audit.py` — add `ITEM_RESTORE` enum member. (Task 1)
- `backend/app/schemas/roster.py` — fix `RosterAuditLogResponse` (`created_by_user_id` → `user_id`/`user_name`/`user_role`). (Task 2)
- `backend/app/api/v1/endpoints/payment_rosters.py` — fix `/audit-logs` response; add restore endpoint. (Tasks 2, 7)
- `backend/app/services/roster_service.py` — audit helper; soft-delete conversions; diff filter; restore method. (Tasks 3–7)

**Frontend**
- `frontend/lib/api/modules/payment-rosters.ts` — add `restoreRosterItem`; ensure `RosterItem` type carries `exclusion_reason`/`updated_at`. (Task 9)
- `frontend/components/roster/RosterDetailDialog.tsx` — show removed rows + 回復 button + 「顯示已移除」toggle + 操作紀錄 tab. (Tasks 10, 11)
- `frontend/lib/api/generated/schema.d.ts` — regenerated. (Task 8)

---

## Task 1: Add `ITEM_RESTORE` audit action

**Files:**
- Modify: `backend/app/models/roster_audit.py:16-33` (the `RosterAuditAction` enum)
- Test: `backend/app/tests/test_roster_audit_log_model.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/app/tests/test_roster_audit_log_model.py`:

```python
def test_item_restore_action_exists():
    from app.models.roster_audit import RosterAuditAction

    assert RosterAuditAction.ITEM_RESTORE.value == "item_restore"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_roster_audit_log_model.py::test_item_restore_action_exists -p no:cacheprovider -v`
Expected: FAIL — `AttributeError: ITEM_RESTORE`.

- [ ] **Step 3: Add the enum member**

In `backend/app/models/roster_audit.py`, inside `class RosterAuditAction`, after the `ITEM_UPDATE` line (currently line 33) add:

```python
    ITEM_RESTORE = "item_restore"  # 回復明細（將已移除者放回名單）
```

- [ ] **Step 4: Run test to verify it passes**

Run: same command as Step 2.
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/roster_audit.py backend/app/tests/test_roster_audit_log_model.py
git commit -m "feat(roster): add ITEM_RESTORE audit action"
```

---

## Task 2: Fix the `/audit-logs` endpoint + schema (latent `created_by_user_id` bug)

The panel (Task 11) reads `GET /{roster_id}/audit-logs`. Today it returns `log.created_by_user_id`, which does not exist on `RosterAuditLog` → AttributeError at call time. Fix to return the real operator fields.

**Files:**
- Modify: `backend/app/schemas/roster.py` (`RosterAuditLogResponse`, around lines 78-90)
- Modify: `backend/app/api/v1/endpoints/payment_rosters.py:2076-2087` (the dict built per log)
- Test: `backend/app/tests/test_payment_rosters_api.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/app/tests/test_payment_rosters_api.py` (follow the file's existing client/fixture style — an admin-authed client and a roster with one `RosterAuditLog`):

```python
def test_audit_logs_endpoint_returns_operator_name(admin_client, roster_with_audit_log):
    roster_id, expected_user_name = roster_with_audit_log
    resp = admin_client.get(f"/api/v1/payment-rosters/{roster_id}/audit-logs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    first = body["data"]["items"][0]
    # The latent bug returned a non-existent created_by_user_id field; we now
    # return real operator identity from the snapshot columns.
    assert first["user_name"] == expected_user_name
    assert "user_id" in first
    assert "user_role" in first
```

Add a `roster_with_audit_log` fixture in the test file if one does not already exist, creating a `PaymentRoster` plus one `RosterAuditLog.create_audit_log(..., user_name="Admin X", user_role="admin", action=RosterAuditAction.ITEM_REMOVE, title="排除 測試生")` and returning `(roster.id, "Admin X")`.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_payment_rosters_api.py::test_audit_logs_endpoint_returns_operator_name -p no:cacheprovider -v`
Expected: FAIL — either `KeyError: 'user_name'` or a 500 from `AttributeError: created_by_user_id`.

- [ ] **Step 3: Fix the endpoint dict**

In `backend/app/api/v1/endpoints/payment_rosters.py`, replace the per-log dict (currently lines 2077-2086) with:

```python
                    {
                        "id": log.id,
                        "action": log.action.value,
                        "level": log.level.value,
                        "title": log.title,
                        "description": log.description,
                        "user_id": log.user_id,
                        "user_name": log.user_name,
                        "user_role": log.user_role,
                        "audit_metadata": log.audit_metadata,
                        "created_at": log.created_at,
                    }
```

- [ ] **Step 4: Fix the schema**

In `backend/app/schemas/roster.py`, in `RosterAuditLogResponse`, replace the `created_by_user_id: Optional[int] = None` line with:

```python
    user_id: Optional[int] = None
    user_name: Optional[str] = None
    user_role: Optional[str] = None
```

- [ ] **Step 5: Run test + black + flake8**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_payment_rosters_api.py::test_audit_logs_endpoint_returns_operator_name -p no:cacheprovider -v`
Expected: PASS.
Then: `uvx --from "black==26.3.1" black --check --line-length=120 backend/app && flake8 app --select=B904,B014 --max-line-length=120` (run flake8 from `backend/`).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/endpoints/payment_rosters.py backend/app/schemas/roster.py backend/app/tests/test_payment_rosters_api.py
git commit -m "fix(roster): /audit-logs returns real operator (user_id/name/role), not missing created_by_user_id"
```

---

## Task 3: Add `RosterService._write_roster_item_audit` helper

One helper that all sync paths (reconcile add/remove, locked-remove, restore) use to write a `RosterAuditLog` with consistent structured metadata.

**Files:**
- Modify: `backend/app/services/roster_service.py` (add method near the other audit/recompute helpers, e.g. after `_recompute_roster_totals_sync`)
- Test: `backend/app/tests/test_roster_item_audit_helper.py` (create)

- [ ] **Step 1: Write the failing test**

Create `backend/app/tests/test_roster_item_audit_helper.py`:

```python
"""Pin: _write_roster_item_audit emits one RosterAuditLog with operator
snapshot + structured audit_metadata."""

from app.models.roster_audit import RosterAuditAction, RosterAuditLog
from app.models.payment_roster import PaymentRoster, PaymentRosterItem
from app.services.roster_service import RosterService


def test_write_roster_item_audit_records_metadata(db_sync, locked_roster_two_items, admin_db_user_sync):
    roster, items = locked_roster_two_items
    item = items[0]
    svc = RosterService(db_sync)

    svc._write_roster_item_audit(
        roster_id=roster.id,
        action=RosterAuditAction.ITEM_REMOVE,
        item=item,
        admin_user_id=admin_db_user_sync.id,
        source="locked_remove",
        reason="測試移除",
    )
    db_sync.flush()

    log = (
        db_sync.query(RosterAuditLog)
        .filter(RosterAuditLog.roster_id == roster.id, RosterAuditLog.action == RosterAuditAction.ITEM_REMOVE)
        .order_by(RosterAuditLog.id.desc())
        .first()
    )
    assert log is not None
    assert log.user_id == admin_db_user_sync.id
    assert log.user_name == admin_db_user_sync.name
    assert log.audit_metadata["source"] == "locked_remove"
    assert log.audit_metadata["application_id"] == item.application_id
    assert log.audit_metadata["reason"] == "測試移除"
    assert log.affected_items_count == 1
```

Reuse the `locked_roster_two_items` and `admin_db_user_sync` fixtures from `test_roster_item_removal_service.py` — copy them into a shared conftest or duplicate the minimal versions in this test file (the fixture must return `(roster, [item, item])`).

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_roster_item_audit_helper.py -p no:cacheprovider -v`
Expected: FAIL — `AttributeError: _write_roster_item_audit`.

- [ ] **Step 3: Implement the helper**

In `backend/app/services/roster_service.py`, add (ensure `from app.models.roster_audit import RosterAuditAction, RosterAuditLog` and `from app.models.user import User` are imported at module top — add if missing):

```python
    _AUDIT_ACTION_LABELS = {
        RosterAuditAction.ITEM_REMOVE: "移除",
        RosterAuditAction.ITEM_ADD: "新增",
        RosterAuditAction.ITEM_RESTORE: "回復",
    }

    def _write_roster_item_audit(
        self,
        roster_id: int,
        action: "RosterAuditAction",
        item: "PaymentRosterItem",
        admin_user_id: int,
        source: str,
        reason: Optional[str] = None,
    ) -> None:
        """Add (not commit) one RosterAuditLog row for an item-level mutation.
        Caller commits. `source` is one of exclude/reconcile/locked_remove/restore."""
        user = self.db.get(User, admin_user_id)
        student_id = None
        if item.application is not None and item.application.student_data:
            student_id = item.application.student_data.get("std_stdcode")
        label = self._AUDIT_ACTION_LABELS.get(action, action.value)
        self.db.add(
            RosterAuditLog.create_audit_log(
                roster_id=roster_id,
                action=action,
                title=f"{label} {item.student_name}",
                description=f"{label} {item.student_name}（原因：{reason or '—'}）",
                user_id=admin_user_id,
                user_name=user.name if user else None,
                user_role=(user.role.value if user and user.role else None),
                audit_metadata={
                    "student_name": item.student_name,
                    "student_id": student_id,
                    "application_id": item.application_id,
                    "source": source,
                    "reason": reason,
                },
                affected_items_count=1,
            )
        )
```

(`Optional` is already imported in this module; confirm.)

- [ ] **Step 4: Run test to verify it passes**

Run: same command as Step 2.
Expected: PASS.

- [ ] **Step 5: black + flake8 + commit**

```bash
uvx --from "black==26.3.1" black --line-length=120 backend/app/services/roster_service.py backend/app/tests/test_roster_item_audit_helper.py
git add backend/app/services/roster_service.py backend/app/tests/test_roster_item_audit_helper.py
git commit -m "feat(roster): add _write_roster_item_audit helper for unified item audit trail"
```

---

## Task 4: Convert `remove_item_from_locked_roster` to soft-delete + RosterAuditLog

**Files:**
- Modify: `backend/app/services/roster_service.py:2167-2219` (`remove_item_from_locked_roster`)
- Test: `backend/app/tests/test_roster_item_removal_service.py`

- [ ] **Step 1: Update/replace the existing removal test to assert soft-delete**

In `test_roster_item_removal_service.py`, the existing test asserts the item is gone (hard delete) and a generic `AuditLog` was written. Replace those assertions. Add/adjust to:

```python
def test_remove_item_from_locked_roster_soft_deletes_and_audits(db_sync, locked_roster_two_items, admin_db_user_sync):
    from app.models.roster_audit import RosterAuditAction, RosterAuditLog

    roster, items = locked_roster_two_items
    target = items[0]
    svc = RosterService(db_sync)

    svc.remove_item_from_locked_roster(
        roster_id=roster.id, item_id=target.id, admin_user_id=admin_db_user_sync.id, reason="繳回"
    )

    # Row still exists, soft-removed
    refreshed = db_sync.get(PaymentRosterItem, target.id)
    assert refreshed is not None
    assert refreshed.is_included is False
    assert "鎖定後移除" in (refreshed.exclusion_reason or "")
    # Roster stays LOCKED + excel_stale
    db_sync.refresh(roster)
    assert roster.status == RosterStatus.LOCKED
    assert roster.excel_stale is True
    # RosterAuditLog ITEM_REMOVE written
    log = (
        db_sync.query(RosterAuditLog)
        .filter(RosterAuditLog.roster_id == roster.id, RosterAuditLog.action == RosterAuditAction.ITEM_REMOVE)
        .first()
    )
    assert log is not None
    assert log.audit_metadata["source"] == "locked_remove"
```

Remove or update any prior assertion in this file that expected the row to be `None` or expected a generic `AuditLog` for this action.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_roster_item_removal_service.py::test_remove_item_from_locked_roster_soft_deletes_and_audits -p no:cacheprovider -v`
Expected: FAIL — item is `None` (still hard-deleted) and/or no `RosterAuditLog`.

- [ ] **Step 3: Convert to soft-delete**

In `backend/app/services/roster_service.py`, in `remove_item_from_locked_roster`, replace the deletion + generic-audit block (currently lines 2187-2211, from `removed_amount = item.scholarship_amount` through the `AuditLog.create_log(...)` add) with:

```python
        item.is_included = False
        item.exclusion_reason = f"鎖定後移除：{reason}" if reason else "鎖定後移除"
        self.db.flush()

        # Recompute totals via the shared sync helper.
        qualified, total_count, total_amount = self._recompute_roster_totals_sync(roster_id)
        roster.excel_stale = True

        self._write_roster_item_audit(
            roster_id=roster_id,
            action=RosterAuditAction.ITEM_REMOVE,
            item=item,
            admin_user_id=admin_user_id,
            source="locked_remove",
            reason=reason,
        )
```

Keep the existing `self.db.commit()` and the return dict that follows; change `"removed_item_id": item_id` to stay as-is (item still exists, but the id is still the removed item's id — fine). Remove the now-unused local `removed_app_id` reference from the return only if it errors; the return dict currently uses `item_id`, `qualified`, `total_amount` which all remain valid.

- [ ] **Step 4: Run test to verify it passes**

Run: same as Step 2.
Expected: PASS. Also run the whole file to catch updated old assertions: `... pytest app/tests/test_roster_item_removal_service.py -p no:cacheprovider -v`.

- [ ] **Step 5: black + flake8 + commit**

```bash
uvx --from "black==26.3.1" black --line-length=120 backend/app/services/roster_service.py backend/app/tests/test_roster_item_removal_service.py
git add backend/app/services/roster_service.py backend/app/tests/test_roster_item_removal_service.py
git commit -m "feat(roster): locked-roster removal soft-deletes + writes RosterAuditLog"
```

---

## Task 5: Convert `reconcile_roster` remove→soft-delete, gate soft-removed, write RosterAuditLog

**Files:**
- Modify: `backend/app/services/roster_service.py:2037-2165` (`reconcile_roster`)
- Test: `backend/app/tests/test_roster_distribution_reconcile_service.py`

- [ ] **Step 1: Write/adjust tests**

Add to `test_roster_distribution_reconcile_service.py`:

```python
def test_reconcile_remove_soft_deletes_and_audits(db_sync, reconcilable_roster, admin_db_user_sync):
    from app.models.roster_audit import RosterAuditAction, RosterAuditLog
    from app.models.payment_roster import PaymentRosterItem

    roster, orphan_item_id = reconcilable_roster  # orphan = in roster but not allocated
    svc = RosterService(db_sync)

    svc.reconcile_roster(
        roster_id=roster.id,
        add_application_ids=[],
        remove_item_ids=[orphan_item_id],
        admin_user_id=admin_db_user_sync.id,
        reason="比對移除",
    )

    item = db_sync.get(PaymentRosterItem, orphan_item_id)
    assert item is not None  # soft, not hard
    assert item.is_included is False
    log = (
        db_sync.query(RosterAuditLog)
        .filter(RosterAuditLog.roster_id == roster.id, RosterAuditLog.action == RosterAuditAction.ITEM_REMOVE)
        .first()
    )
    assert log is not None
    assert log.audit_metadata["source"] == "reconcile"


def test_reconcile_does_not_reflag_already_softremoved_orphan(db_sync, reconcilable_roster, admin_db_user_sync):
    """After a soft-remove, the same orphan must not appear again in allowed_remove."""
    roster, orphan_item_id = reconcilable_roster
    svc = RosterService(db_sync)
    svc.reconcile_roster(roster.id, [], [orphan_item_id], admin_db_user_sync.id, "first")

    diff = svc.get_distribution_diff_for_roster(roster.id)
    assert all(e.item_id != orphan_item_id for e in diff["to_remove"])

    # And a second reconcile attempt on it is rejected as not-removable.
    import pytest
    with pytest.raises(ValueError):
        svc.reconcile_roster(roster.id, [], [orphan_item_id], admin_db_user_sync.id, "again")
```

Use/extend the existing reconcile fixtures in this file; add a `reconcilable_roster` fixture returning `(roster, orphan_item_id)` where the orphan item's `application_id` is **not** in the roster's distribution slice (so it is removable), modeled on the existing fixtures in this file.

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_roster_distribution_reconcile_service.py -k "soft_deletes_and_audits or reflag" -p no:cacheprovider -v`
Expected: FAIL — orphan item is `None` (hard-deleted) and/or no `RosterAuditLog`; reflag test fails because soft-removed orphan reappears.

- [ ] **Step 3a: Gate soft-removed out of `allowed_remove`**

In `reconcile_roster`, change the `allowed_remove` set (currently line 2075) from:

```python
        allowed_remove = {it.id for it in existing_items if it.application_id not in allocated_map}
```
to:
```python
        allowed_remove = {
            it.id for it in existing_items if it.is_included and it.application_id not in allocated_map
        }
```

- [ ] **Step 3b: Replace the remove loop (hard-delete → soft-delete + RosterAuditLog)**

Replace the entire remove loop (currently lines 2119-2139, `for item_id in remove_ids:` … through the `AuditLog.create_log(...)` add) with:

```python
        for item_id in remove_ids:
            item = items_by_id[item_id]
            item.is_included = False
            item.exclusion_reason = "比對分發移除：不在分發名單"
            removed.append({"item_id": item_id, "application_id": item.application_id})
            self._write_roster_item_audit(
                roster_id=roster_id,
                action=RosterAuditAction.ITEM_REMOVE,
                item=item,
                admin_user_id=admin_user_id,
                source="reconcile",
                reason=reason,
            )
```

- [ ] **Step 3c: Replace the add loop's generic audit with RosterAuditLog + dup guard**

Replace the add loop (currently lines 2086-2117) with:

```python
        for app_id in add_ids:
            application = self.db.get(Application, app_id)
            if application is None:
                raise ValueError(f"Application {app_id} not found")
            # Defensive: if a (soft-removed) item already exists for this app,
            # restore it instead of creating a duplicate row (no DB unique
            # constraint protects us). Unreachable via the gated diff today,
            # but keeps the invariant if gating changes.
            existing = next((it for it in existing_items if it.application_id == app_id), None)
            if existing is not None:
                existing.is_included = True
                existing.exclusion_reason = None
                item = existing
                action = RosterAuditAction.ITEM_RESTORE
            else:
                item = self._verify_and_create_item(roster, application)
                action = RosterAuditAction.ITEM_ADD
            self.db.flush()
            added.append(
                {
                    "application_id": app_id,
                    "item_id": item.id,
                    "is_included": item.is_included,
                    "exclusion_reason": item.exclusion_reason,
                }
            )
            self._write_roster_item_audit(
                roster_id=roster_id,
                action=action,
                item=item,
                admin_user_id=admin_user_id,
                source="reconcile",
                reason=reason,
            )
```

- [ ] **Step 3d: Drop the generic reconcile-summary AuditLog**

Remove the trailing summary `self.db.add(AuditLog.create_log(... action="roster.reconciled" ...))` block (currently lines 2146-2155). The per-item RosterAuditLog rows are the trail now. Leave the totals recompute, `roster.excel_stale = True`, `self.db.commit()`, and the return dict intact.

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_roster_distribution_reconcile_service.py -p no:cacheprovider -v`
Expected: PASS (whole file — existing reconcile tests still green; update any that asserted hard delete or generic `AuditLog`).

- [ ] **Step 5: black + flake8 + commit**

```bash
uvx --from "black==26.3.1" black --line-length=120 backend/app/services/roster_service.py backend/app/tests/test_roster_distribution_reconcile_service.py
git add backend/app/services/roster_service.py backend/app/tests/test_roster_distribution_reconcile_service.py
git commit -m "feat(roster): reconcile removal soft-deletes, gates soft-removed orphans, unified RosterAuditLog"
```

---

## Task 6: Diff (`get_distribution_diff_for_roster`) skips soft-removed items

**Files:**
- Modify: `backend/app/services/roster_service.py:1974-1996` (the `to_remove` loop)
- Test: `backend/app/tests/test_roster_distribution_reconcile_service.py`

- [ ] **Step 1: Write the failing test**

```python
def test_diff_to_remove_excludes_softremoved_items(db_sync, reconcilable_roster, admin_db_user_sync):
    roster, orphan_item_id = reconcilable_roster
    svc = RosterService(db_sync)
    svc.reconcile_roster(roster.id, [], [orphan_item_id], admin_db_user_sync.id, "soft")

    diff = svc.get_distribution_diff_for_roster(roster.id)
    assert all(e.item_id != orphan_item_id for e in diff["to_remove"])
```

(If Task 5's reflag test already covers this via `get_distribution_diff_for_roster`, this is a focused duplicate — keep it; it documents the diff contract directly.)

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_roster_distribution_reconcile_service.py::test_diff_to_remove_excludes_softremoved_items -p no:cacheprovider -v`
Expected: FAIL — soft-removed orphan still listed in `to_remove`.

- [ ] **Step 3: Skip soft-removed in the `to_remove` loop**

In `get_distribution_diff_for_roster`, the `to_remove` loop starts (currently line 1975) with `for item in existing_items:` then `if item.application_id in allocated_map: continue`. Add a sibling guard immediately after that continue:

```python
        for item in existing_items:
            if item.application_id in allocated_map:
                continue
            if not item.is_included:
                # Already soft-removed — not an actionable orphan anymore.
                continue
```

(Leave `orphan_app_ids` as-is; it only feeds student_data enrichment and an over-broad set is harmless.)

- [ ] **Step 4: Run test to verify it passes**

Run: same as Step 2.
Expected: PASS.

- [ ] **Step 5: black + commit**

```bash
uvx --from "black==26.3.1" black --line-length=120 backend/app/services/roster_service.py backend/app/tests/test_roster_distribution_reconcile_service.py
git add backend/app/services/roster_service.py backend/app/tests/test_roster_distribution_reconcile_service.py
git commit -m "fix(roster): distribution diff ignores soft-removed items in to_remove"
```

---

## Task 7: `RosterService.restore_item` + `POST /items/{item_id}/restore` endpoint

**Files:**
- Modify: `backend/app/services/roster_service.py` (add `restore_item`, near `remove_item_from_locked_roster`)
- Modify: `backend/app/api/v1/endpoints/payment_rosters.py` (add endpoint; reuse `RemoveLockedItemRequest`-style body or a new `RestoreItemRequest`)
- Test: `backend/app/tests/test_roster_item_removal_service.py` (service), `backend/app/tests/test_payment_rosters_api.py` (endpoint)

- [ ] **Step 1: Write the failing service test**

Add to `test_roster_item_removal_service.py`:

```python
def test_restore_item_reincludes_and_audits(db_sync, locked_roster_two_items, admin_db_user_sync):
    from app.models.roster_audit import RosterAuditAction, RosterAuditLog
    from app.models.payment_roster import PaymentRosterItem

    roster, items = locked_roster_two_items
    target = items[0]
    svc = RosterService(db_sync)
    svc.remove_item_from_locked_roster(roster.id, target.id, admin_db_user_sync.id, "繳回")

    result = svc.restore_item(roster.id, target.id, admin_db_user_sync.id, "誤刪回復")

    item = db_sync.get(PaymentRosterItem, target.id)
    assert item.is_included is True
    assert item.exclusion_reason is None
    db_sync.refresh(roster)
    assert roster.excel_stale is True  # locked roster → re-export needed
    log = (
        db_sync.query(RosterAuditLog)
        .filter(RosterAuditLog.roster_id == roster.id, RosterAuditLog.action == RosterAuditAction.ITEM_RESTORE)
        .first()
    )
    assert log is not None
    assert log.audit_metadata["source"] == "restore"
    assert result["excel_stale"] is True


def test_restore_item_rejects_already_included(db_sync, locked_roster_two_items, admin_db_user_sync):
    import pytest
    roster, items = locked_roster_two_items
    svc = RosterService(db_sync)
    with pytest.raises(ValueError):
        svc.restore_item(roster.id, items[0].id, admin_db_user_sync.id, "noop")  # already included
```

- [ ] **Step 2: Run to verify it fails**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_roster_item_removal_service.py -k restore -p no:cacheprovider -v`
Expected: FAIL — `AttributeError: restore_item`.

- [ ] **Step 3: Implement `restore_item`**

In `backend/app/services/roster_service.py`, add after `remove_item_from_locked_roster`:

```python
    def restore_item(
        self,
        roster_id: int,
        item_id: int,
        admin_user_id: int,
        reason: Optional[str] = None,
    ) -> dict:
        """Re-include a soft-removed PaymentRosterItem. Works on COMPLETED and
        LOCKED rosters. Recompute totals, set excel_stale=True, write
        RosterAuditLog(ITEM_RESTORE). Caller-facing 409 maps from ValueError."""
        roster = self.db.get(PaymentRoster, roster_id)
        if roster is None:
            raise ValueError(f"Roster {roster_id} not found")

        item = self.db.get(PaymentRosterItem, item_id)
        if item is None or item.roster_id != roster_id:
            raise ValueError(f"Item {item_id} not found in roster {roster_id}")
        if item.is_included:
            raise ValueError("明細未被移除，無需回復")

        item.is_included = True
        item.exclusion_reason = None
        self.db.flush()

        qualified, total_count, total_amount = self._recompute_roster_totals_sync(roster_id)
        roster.excel_stale = True

        self._write_roster_item_audit(
            roster_id=roster_id,
            action=RosterAuditAction.ITEM_RESTORE,
            item=item,
            admin_user_id=admin_user_id,
            source="restore",
            reason=reason,
        )
        self.db.commit()
        return {
            "roster_id": roster_id,
            "restored_item_id": item_id,
            "qualified_count": qualified,
            "total_amount": float(total_amount),
            "excel_stale": True,
        }
```

- [ ] **Step 4: Run service test — PASS**

Run: same as Step 2. Expected: PASS.

- [ ] **Step 5: Write the failing endpoint test**

Add to `test_payment_rosters_api.py` (mirror the existing exclude/remove endpoint tests):

```python
def test_restore_endpoint_reincludes_item(admin_client, locked_roster_with_removed_item):
    roster_id, item_id = locked_roster_with_removed_item  # item is is_included=False
    resp = admin_client.post(
        f"/api/v1/payment-rosters/{roster_id}/items/{item_id}/restore",
        json={"reason_note": "誤刪"},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # Idempotent: restoring again → 409
    resp2 = admin_client.post(
        f"/api/v1/payment-rosters/{roster_id}/items/{item_id}/restore", json={}
    )
    assert resp2.status_code == 409


def test_restore_endpoint_forbidden_for_non_admin(non_admin_client, locked_roster_with_removed_item):
    roster_id, item_id = locked_roster_with_removed_item
    resp = non_admin_client.post(
        f"/api/v1/payment-rosters/{roster_id}/items/{item_id}/restore", json={}
    )
    assert resp.status_code == 403
```

Add a `locked_roster_with_removed_item` fixture (build a roster + one item with `is_included=False, exclusion_reason="鎖定後移除：繳回"`, return `(roster.id, item.id)`). Reuse `admin_client` / `non_admin_client` patterns already in the file.

- [ ] **Step 6: Run endpoint test to verify it fails**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_payment_rosters_api.py -k restore_endpoint -p no:cacheprovider -v`
Expected: FAIL — 404 (route not registered).

- [ ] **Step 7: Implement the endpoint**

In `backend/app/api/v1/endpoints/payment_rosters.py`, add a request model near the other Pydantic request models (where `RemoveLockedItemRequest` is defined):

```python
class RestoreItemRequest(BaseModel):
    reason_note: Optional[str] = None
```

Then add the endpoint (place it alongside the other sync `get_sync_db` roster-item routes, e.g. just after `remove_locked_roster_item`):

```python
@router.post("/{roster_id}/items/{item_id}/restore")
def restore_roster_item(
    roster_id: int,
    item_id: int,
    request: RestoreItemRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    """Re-include a soft-removed roster item (回復). Admin only. Works on
    COMPLETED and LOCKED rosters; sets excel_stale; audits ITEM_RESTORE."""
    _require_admin(current_user)
    svc = RosterService(db)
    try:
        result = svc.restore_item(
            roster_id=roster_id,
            item_id=item_id,
            admin_user_id=current_user.id,
            reason=request.reason_note,
        )
    except ValueError as e:
        msg = str(e)
        # "未被移除" is the idempotency conflict → 409; other ValueErrors → 400.
        code = status.HTTP_409_CONFLICT if "未被移除" in msg else status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=code, detail=msg) from e
    return {"success": True, "message": "已回復造冊明細", "data": result}
```

Confirm `BaseModel`, `Optional`, `status`, `Session`, `get_sync_db`, `RosterService`, `_require_admin` are already imported in this file (they are used by neighbouring routes).

- [ ] **Step 8: Run endpoint test — PASS + lint**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_payment_rosters_api.py -k restore_endpoint -p no:cacheprovider -v`
Expected: PASS.
Then: `uvx --from "black==26.3.1" black --check --line-length=120 backend/app && flake8 app --select=B904,B014 --max-line-length=120`.

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/roster_service.py backend/app/api/v1/endpoints/payment_rosters.py backend/app/tests/test_roster_item_removal_service.py backend/app/tests/test_payment_rosters_api.py
git commit -m "feat(roster): add restore_item service + POST /items/{id}/restore endpoint"
```

---

## Task 8: Regenerate OpenAPI TypeScript types

**Files:**
- Modify: `frontend/lib/api/generated/schema.d.ts` (generated)

- [ ] **Step 1: Ensure backend is running, then generate**

Run (backend must be on `localhost:8000`):
```bash
cd frontend && npm run api:generate
```

- [ ] **Step 2: Verify the new route + schema appear**

Run: `grep -n "items/{item_id}/restore\|user_name" frontend/lib/api/generated/schema.d.ts | head`
Expected: the restore path and the audit-log `user_name`/`user_role` fields are present.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api/generated/schema.d.ts
git commit -m "chore(api): regenerate types for restore endpoint + audit-log operator fields"
```

---

## Task 9: Frontend API client — `restoreRosterItem` + `RosterItem` type fields

**Files:**
- Modify: `frontend/lib/api/modules/payment-rosters.ts` (add `restoreRosterItem` after `excludeRosterItem`, line ~257; ensure `RosterItem` type has `exclusion_reason`/`updated_at`)
- Test: `frontend/lib/api/modules/__tests__/payment-rosters.test.ts` (create if absent, else add)

- [ ] **Step 1: Write the failing test**

Add a jest test that mocks `typedClient.raw.POST` and asserts `restoreRosterItem` calls the right path/body (mirror any existing module test; if none exists for this module, model it on another `frontend/lib/api/modules/__tests__/*.test.ts`):

```typescript
it("restoreRosterItem POSTs to the restore path with reason_note", async () => {
  const post = jest.spyOn(typedClient.raw, "POST").mockResolvedValue({ data: { success: true } } as any);
  await paymentRosters.restoreRosterItem(7, 42, "誤刪");
  expect(post).toHaveBeenCalledWith(
    "/api/v1/payment-rosters/{roster_id}/items/{item_id}/restore",
    expect.objectContaining({
      params: { path: { roster_id: 7, item_id: 42 } },
      body: { reason_note: "誤刪" },
    })
  );
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx jest lib/api/modules/__tests__/payment-rosters.test.ts -t restoreRosterItem`
Expected: FAIL — `restoreRosterItem is not a function`.

- [ ] **Step 3: Add the client method**

In `frontend/lib/api/modules/payment-rosters.ts`, after `excludeRosterItem` (line ~257) add:

```typescript
    /**
     * 回復造冊明細（將已移除者放回名單）
     * POST /api/v1/payment-rosters/{roster_id}/items/{item_id}/restore
     */
    restoreRosterItem: async (
      roster_id: number,
      item_id: number,
      reason_note?: string
    ): Promise<ApiResponse<unknown>> => {
      const response = await typedClient.raw.POST(
        '/api/v1/payment-rosters/{roster_id}/items/{item_id}/restore',
        {
          params: { path: { roster_id, item_id } },
          body: { reason_note: reason_note ?? null },
        }
      );
      return toApiResponse(response);
    },
```

- [ ] **Step 4: Ensure `RosterItem` type exposes removal fields**

Confirm the `RosterItem` type (used by `RosterDetailDialog`) includes `is_included: boolean`, `exclusion_reason?: string | null`, and `updated_at?: string | null`. If it is locally declared and missing these, add them. (The backend `RosterItemResponse` already returns all three.)

- [ ] **Step 5: Run test — PASS + commit**

Run: `cd frontend && npx jest lib/api/modules/__tests__/payment-rosters.test.ts -t restoreRosterItem`
Expected: PASS.

```bash
git add frontend/lib/api/modules/payment-rosters.ts frontend/lib/api/modules/__tests__/payment-rosters.test.ts
git commit -m "feat(roster): add restoreRosterItem API client + RosterItem removal fields"
```

---

## Task 10: RosterDetailDialog — show removed rows + 回復 button + 「顯示已移除」toggle

**Files:**
- Modify: `frontend/components/roster/RosterDetailDialog.tsx` (`renderStudentTable`, lines 418-499; add toggle state near other `useState` at top of component; add a restore handler near `handleExclude`)

- [ ] **Step 1: Add toggle state + restore handler**

Near the other dialog `useState` declarations (e.g. after the exclude state at lines 116-121) add:

```typescript
  const [showRemoved, setShowRemoved] = useState(true);
  const [restoringId, setRestoringId] = useState<number | null>(null);
```

Add a handler next to the exclude submit handler (after `handleExclude`, ~line 260):

```typescript
  const handleRestore = async (item: RosterItem) => {
    if (!period.roster_id) return;
    if (!window.confirm(`確定回復 ${item.student_name}？此操作會將造冊標記為「需重新匯出 Excel」`)) {
      return;
    }
    setRestoringId(item.id);
    try {
      const resp = await apiClient.paymentRosters.restoreRosterItem(
        period.roster_id,
        item.id
      );
      if (resp.success) {
        toast.success(`已回復 ${item.student_name}`);
        setExcelStale(true);
        await fetchItems(); // existing refetch used after exclude/reconcile
      } else {
        toast.error(resp.message || "回復失敗");
      }
    } catch (e) {
      logger.error("restore roster item failed", { error: e });
      toast.error("回復失敗");
    } finally {
      setRestoringId(null);
    }
  };
```

(Use the same refetch function the exclude flow calls — confirm its name in the file, e.g. `fetchItems` / `loadItems`; match it.)

- [ ] **Step 2: Render removed rows in `renderStudentTable`**

Replace the body of `renderStudentTable` (lines 418-499). Key changes: do **not** drop removed rows; honor the `showRemoved` toggle; grey out removed rows; swap the 排除 button for a 回復 button on removed rows.

```tsx
  const renderStudentTable = (items: RosterItem[]) => {
    const visibleItems = showRemoved ? items : items.filter(i => i.is_included);

    if (visibleItems.length === 0) {
      return (
        <div className="text-center py-8 text-muted-foreground">
          此學院無納入造冊的學生
        </div>
      );
    }

    return (
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>姓名</TableHead>
            <TableHead>學號</TableHead>
            <TableHead>系所</TableHead>
            <TableHead>申請身分</TableHead>
            <TableHead>分發獎學金</TableHead>
            <TableHead className="text-right">金額</TableHead>
            <TableHead className="text-right w-20">操作</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {visibleItems.map((item, index) => {
            const removed = !item.is_included;
            return (
              <TableRow
                key={index}
                className={removed ? "opacity-50 line-through" : undefined}
              >
                <TableCell className="font-medium">
                  {item.student_name}
                  {removed && (
                    <Badge variant="destructive" className="ml-2 no-underline">
                      已移除
                    </Badge>
                  )}
                  {removed && item.exclusion_reason && (
                    <span className="ml-2 text-xs text-muted-foreground no-underline">
                      {item.exclusion_reason}
                    </span>
                  )}
                </TableCell>
                <TableCell className="font-mono text-sm">
                  {item.student_id || "-"}
                </TableCell>
                <TableCell>{item.department_name || "-"}</TableCell>
                <TableCell>
                  <Badge
                    variant={
                      item.application_identity?.includes("續領")
                        ? "secondary"
                        : "outline"
                    }
                  >
                    {item.application_identity || "-"}
                  </Badge>
                </TableCell>
                <TableCell>
                  {item.allocated_sub_type ? (
                    <span className="text-sm">
                      {item.allocation_year && (
                        <span className="font-medium">
                          {item.allocation_year}年{" "}
                        </span>
                      )}
                      {item.allocated_sub_type === "nstc"
                        ? "國科會"
                        : item.allocated_sub_type === "moe_1w"
                          ? "教育部(1萬)"
                          : item.allocated_sub_type === "moe_2w"
                            ? "教育部(2萬)"
                            : item.allocated_sub_type}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">-</span>
                  )}
                </TableCell>
                <TableCell className="text-right font-medium">
                  {formatCurrency(item.scholarship_amount)}
                </TableCell>
                <TableCell className="text-right">
                  {removed ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={restoringId === item.id}
                      onClick={() => handleRestore(item)}
                      title="回復此明細（放回名單）"
                      className="no-underline"
                    >
                      <RotateCcw className="h-4 w-4" />
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => openExcludeDialog(item)}
                      title="排除此明細（學生繳回 / 放棄）"
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    );
  };
```

Add `RotateCcw` to the `lucide-react` import (the file already imports `X` from it).

- [ ] **Step 3: Add the 「顯示已移除」 toggle near the list header**

Where the list/人數 header renders (around lines 700-715, the `{rosterItems.filter(item => item.is_included).length} 人` block), add a checkbox/switch bound to `showRemoved`:

```tsx
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <input
                type="checkbox"
                checked={showRemoved}
                onChange={e => setShowRemoved(e.target.checked)}
              />
              顯示已移除
            </label>
```

Leave all `人數` / per-college counts computing on `item.is_included` (unchanged — removed people must not inflate counts).

- [ ] **Step 4: Verify the dialog compiles + smoke test**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json` (or the project's typecheck script).
Expected: no new type errors.
Then drive the UI per Task 12.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/roster/RosterDetailDialog.tsx
git commit -m "feat(roster): show removed students inline with 回復 button + 顯示已移除 toggle"
```

---

## Task 11: RosterDetailDialog — 操作紀錄 tab

**Files:**
- Modify: `frontend/components/roster/RosterDetailDialog.tsx` (add a `TabsTrigger`/`TabsContent` — the file already imports `Tabs, TabsContent, TabsList, TabsTrigger` at line 24)
- Reuse: `frontend/components/audit-trail/AuditLogItem.tsx` (check its props; if incompatible, render a simple list inline)

- [ ] **Step 1: Add audit-log state + fetch**

Near the other `useState`:

```typescript
  const [auditLogs, setAuditLogs] = useState<RosterAuditLogEntry[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditFilter, setAuditFilter] = useState<"all" | "item_remove" | "item_add" | "item_restore">("all");
```

Define the entry type near the top of the file:

```typescript
type RosterAuditLogEntry = {
  id: number;
  action: string;
  title: string;
  description?: string | null;
  user_name?: string | null;
  created_at: string;
};
```

Add a fetch function and call it when the dialog opens (extend the existing open-effect, or add a new `useEffect` keyed on `open` + `period.roster_id`):

```typescript
  const fetchAuditLogs = async () => {
    if (!period.roster_id) return;
    setAuditLoading(true);
    try {
      const resp = await apiClient.paymentRosters.getAuditLogs(period.roster_id, { limit: 200 });
      const raw = (resp.data as { items?: RosterAuditLogEntry[] })?.items ?? [];
      setAuditLogs(raw);
    } catch (e) {
      logger.error("fetch roster audit logs failed", { error: e });
    } finally {
      setAuditLoading(false);
    }
  };
```

Call `fetchAuditLogs()` alongside the existing items fetch on open, and after `handleRestore` / exclude / reconcile so the log stays fresh.

- [ ] **Step 2: Render the tab**

Wrap the existing list body in a `Tabs` (if not already) and add an 操作紀錄 tab. Minimal addition:

```tsx
            <TabsTrigger value="audit">操作紀錄</TabsTrigger>
```
and the content:
```tsx
            <TabsContent value="audit">
              <div className="mb-2 flex gap-2 text-sm">
                {(["all", "item_remove", "item_add", "item_restore"] as const).map(f => (
                  <button
                    key={f}
                    className={auditFilter === f ? "font-semibold underline" : "text-muted-foreground"}
                    onClick={() => setAuditFilter(f)}
                  >
                    {{ all: "全部", item_remove: "移除", item_add: "新增", item_restore: "回復" }[f]}
                  </button>
                ))}
              </div>
              {auditLoading ? (
                <div className="py-8 text-center text-muted-foreground">載入中…</div>
              ) : (
                <ul className="space-y-2">
                  {auditLogs
                    .filter(l => auditFilter === "all" || l.action === auditFilter)
                    .map(l => (
                      <li key={l.id} className="border rounded p-2 text-sm">
                        <div className="font-medium">{l.title}</div>
                        {l.description && (
                          <div className="text-muted-foreground">{l.description}</div>
                        )}
                        <div className="text-xs text-muted-foreground">
                          {l.user_name || "系統"} · {new Date(l.created_at).toLocaleString("zh-TW")}
                        </div>
                      </li>
                    ))}
                  {auditLogs.length === 0 && (
                    <li className="py-8 text-center text-muted-foreground">尚無操作紀錄</li>
                  )}
                </ul>
              )}
            </TabsContent>
```

If `AuditLogItem.tsx` accepts a compatible shape, render it instead of the inline `<li>`; otherwise the inline list above is the deliverable.

- [ ] **Step 3: Typecheck + smoke test**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json`. Expected: no new errors. Then Task 12.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/roster/RosterDetailDialog.tsx
git commit -m "feat(roster): add 操作紀錄 tab to roster detail dialog"
```

---

## Task 12: End-to-end smoke test (manual / Playwright)

Use the `playwright-test-and-debug` skill / localhost dev env.

- [ ] **Step 1:** `docker compose -f docker-compose.dev.yml up -d` and confirm the container mounts THIS worktree (see "Running tests" caveat). **Migration REQUIRED (corrected after bug):** `RosterAuditAction` is a native PG enum — run `alembic upgrade head` so `add_item_restore_audit_001` adds `item_restore` to the `rosterauditaction` enum, else restore 500s on PostgreSQL (SQLite tests don't catch it).
- [ ] **Step 2:** Log in as `admin`, open a COMPLETED roster's 查看名單. Exclude a student (繳回) → confirm they now appear greyed with 「已移除」 + a 回復 button (previously they vanished).
- [ ] **Step 3:** Click 回復 → confirm dialog → student returns to normal styling; 人數 unchanged while removed, +1 after restore; Excel-stale banner appears.
- [ ] **Step 4:** Open 操作紀錄 tab → see 移除 then 回復 entries with operator + timestamp; filter by 回復 shows only restores.
- [ ] **Step 5:** Lock the roster, remove a student (鎖定後移除) → row greyed not vanished; restore works; both logged.
- [ ] **Step 6:** Toggle 顯示已移除 off → removed rows hide; on → reappear.

---

## Self-Review (completed by plan author)

**1. Spec coverage**
- Spec §3 (soft-delete all 3 paths): exclude already soft (no task needed); reconcile → Task 5; locked-remove → Task 4. ✔
- §3.1 ITEM_RESTORE enum → Task 1. ✔
- §3.3 diff skips soft-removed → Task 6 (+ gate in Task 5); 補充人 restore-not-duplicate → Task 5 Step 3c. ✔
- §4.1 restore endpoint (admin, 409 idempotent, LOCKED allowed + excel_stale, recompute) → Task 7. ✔
- §4.2 unified RosterAuditLog (remove/add/restore), drop write-only generic AuditLog → Tasks 3/4/5; audit-logs endpoint fix → Task 2. ✔
- §5.1 inline removed rows + 回復 + 顯示已移除 toggle, counts stay on is_included → Task 10. ✔
- §5.2 操作紀錄 panel + action filter → Task 11. ✔
- §6 admin-only, LOCKED restore allowed, orphan-restore semantics, no-duplicate → Tasks 7/5. ✔
- §7 tests + CI lint + api:generate → in each task + Task 8. ✔

**2. Placeholder scan:** No TBD/TODO; every code step shows real code; fixtures referenced point to concrete existing files. Two intentional "confirm the refetch function name / RosterItem type locally" notes remain because the exact local symbol name must be read from the file at edit time — these are verification instructions, not missing logic.

**3. Type/name consistency:** `_write_roster_item_audit(roster_id, action, item, admin_user_id, source, reason)` used identically in Tasks 3/4/5/7. `restore_item(roster_id, item_id, admin_user_id, reason)` defined Task 7, called in tests with same args. `restoreRosterItem(roster_id, item_id, reason_note?)` consistent across client (Task 9), handler (Task 10), test. `RosterAuditLogEntry` fields match the Task 2 endpoint output (`user_name`, `created_at`, `action`, `title`, `description`). ✔
