# 學院查看分發結果（College views distribution results, admin-gated）

**Date:** 2026-06-30
**Status:** Approved design — ready for implementation plan

## Goal

Give the **College (學院)** role a new "分發結果" view showing **their own college's** students'
allocation outcomes (正取 / 備取 / 未錄取) grouped by sub-type. Visibility is controlled by a
**per-scholarship admin toggle** — colleges see the tab only when the admin opens it.

### Scope decisions (locked with user)

- **Data shown:** allocation outcome only — 正取 (admitted) / 備取 (backup, with position) / 未錄取
  (rejected), grouped by sub-type, each student shown as **name + 學號** only.
  - **No payment PII** (no bank account, national ID, amount). The full payment roster stays admin-only.
  - **No allocation-year label** (不必標記年度) — outcomes for the same sub-type across allocation
    years are merged into one sub-type group.
- **Toggle granularity:** per-scholarship-configuration (type × academic_year × semester), exactly
  like the existing `allow_supplementary_import` toggle.
- **UI placement:** a new "分發結果" sub-tab in `CollegeManagementShell`, alongside 申請審核 / 學生排序.
  The tab is rendered **only when the admin has opened visibility** for that scholarship config.
- **Rejected students are shown** (未錄取 appears in the list).
- **Scoping:** a college only ever sees its **own** students (by `college_code`), regardless of toggle.

## Current-state findings (why this design)

- The per-student distribution result is modeled on `CollegeRankingItem`
  (`is_allocated`, `allocated_sub_type`, `allocation_config_id` → allocation_year, `rank_position`,
  `backup_position`/`backup_allocations`, `status`), copied onto `Application` at finalize, and frozen
  into `PaymentRosterItem`.
- Distribution **execution / finalize / roster generation is admin-only**
  (`backend/app/api/v1/endpoints/manual_distribution.py`, all `get_current_admin_user`). The college
  role only ranks and reviews. This design does **not** change that.
- A college-gated endpoint `GET /college-review/rankings/{ranking_id}/distribution-details` already
  exists (`backend/app/api/v1/endpoints/college_review/distribution.py:96`) but:
  - it is keyed by `ranking_id` (the college tab works off type/year/semester selectors, not a ranking id),
  - it returns an **all-colleges** summary (not scoped to the caller's `college_code`),
  - the frontend never calls it.
  So we add a **focused new college-scoped endpoint** rather than retrofit it. The existing endpoint is
  left untouched (out of scope).
- The canonical "admin toggle controls what college can do" pattern is `allow_supplementary_import`:
  - model: `ScholarshipConfiguration.allow_supplementary_import` (`backend/app/models/scholarship.py:591`)
  - admin setter: `PATCH /configurations/{id}/supplementary-import`
    (`backend/app/api/v1/endpoints/scholarship_configurations.py:1132`, `require_admin`)
  - college-side gate: 403 in `ranking_management.py:1360`
  - admin Switch: `frontend/components/admin-configuration-management.tsx:115`
  - college consumer: `frontend/components/college/ranking/RankingManagementPanel.tsx:379,445`
  This feature mirrors that pattern end-to-end.

## Design

### 1. Data model — new admin toggle

`backend/app/models/scholarship.py`, on `ScholarshipConfiguration`, immediately after
`allow_supplementary_import` (line 591):

```python
# 分發結果查看開關 — admin 控制，是否開放學院查看自己學生的分發結果（正取/備取/未錄取）
allow_college_view_distribution = Column(
    Boolean, default=False, nullable=False, server_default="false"
)
```

Alembic migration:
- Follows the project migration rules (CLAUDE.md): include an existence check before `add_column`
  (inspect columns of `scholarship_configurations`), and a matching `drop_column` in `downgrade`.
- Default `false` / `server_default="false"` means existing configs stay closed until an admin opens them.

### 2. Backend — admin setter endpoint

New endpoint in `backend/app/api/v1/endpoints/scholarship_configurations.py`, mirroring
`toggle_configuration_supplementary_import` (line 1132):

```
PATCH /api/v1/scholarship-configurations/configurations/{id}/college-view-distribution
body: { "allow": bool }
auth: require_admin
```

- Resolve config via `get_user_accessible_scholarship_ids` (404 if not accessible/not found).
- Set `config.allow_college_view_distribution = body.allow`, `config.updated_by = current_user.id`, commit.
- Return `ApiResponse(success, message, data={"id", "allow_college_view_distribution"})`.

Also surface the new flag in the config-read payloads that already include
`allow_supplementary_import` (so both the admin config UI and the college UI can read its state):
`scholarship_configurations.py` (the GET/list config responses) and the college-facing config payloads
in `college_review/ranking_management.py` that already emit `allow_supplementary_import`.

### 3. Backend — new college-facing read endpoint

New endpoint in `backend/app/api/v1/endpoints/college_review/distribution.py`:

```
GET /api/v1/college-review/distribution-results
    ?scholarship_type_id=<int>&academic_year=<int>&semester=<str|null>
auth: require_college
```

Logic:
1. Resolve the active `ScholarshipConfiguration` for `(scholarship_type_id, academic_year, semester)`
   (semester normalized; yearly → NULL). 404 if no config.
2. **Gate:** `if not config.allow_college_view_distribution: raise HTTPException(403, "分發結果尚未開放查看")`.
   Order any college-permission assertion (e.g. `assert_can_manage_ranking` / managed-college check)
   **before** reading the flag, so a cross-college caller gets a permission error rather than leaking
   the flag state (same ordering discipline as `ranking_management.py:1338-1342`).
3. **Scope to the caller's college:** restrict to the college's own students using the same mechanism
   `get_applications_for_college_review` uses (`current_user.college_code`, matched against the
   student's academy code — `student_data.std_academyno`).
4. Read the relevant `CollegeRankingItem`s (joined to `Application`, eager-loaded), skip soft-deleted
   apps, and group by `allocated_sub_type`:
   - **正取:** `is_allocated` true → include `rank_position`.
   - **備取:** has `backup_position` / `backup_allocations` for that sub-type → include backup position.
   - **未錄取:** ranked but neither allocated nor backup.
   - Each entry: `{ student_number (學號), student_name }` only. Merge across allocation years
     (no year field in the response).
5. If distribution has not been executed for the relevant ranking(s), return an empty/"尚未分發" payload
   (`distribution_executed: false`) rather than an error.

Response shape (wrapped in the standard `ApiResponse`):

```jsonc
{
  "success": true,
  "message": "...",
  "data": {
    "distribution_executed": true,
    "sub_types": [
      {
        "code": "nstc",
        "label": "國科會",
        "admitted": [ { "student_number": "310460031", "student_name": "王小明", "rank_position": 1 } ],
        "backup":   [ { "student_number": "310460052", "student_name": "陳小美", "backup_position": 1 } ],
        "rejected": [ { "student_number": "310460088", "student_name": "張三" } ]
      }
    ]
  }
}
```

Sub-type label/`label_en` resolved from `ScholarshipType.sub_type_configs` (same metadata logic the
existing `distribution-details` endpoint uses — extract a small shared helper if it reduces duplication).

### 4. Frontend — admin Switch

- `frontend/lib/api/types.ts`: add `allow_college_view_distribution?: boolean` to the scholarship
  configuration shape.
- `frontend/lib/api/modules/college.ts`: add `toggleConfigCollegeViewDistribution(configId, allow)`
  calling the new PATCH endpoint (mirror `toggleConfigSupplementaryImport`).
- `frontend/components/admin-configuration-management.tsx`: add a `<Switch>` labeled
  "開放學院查看分發結果" next to the 補充匯入 switch (line 115), with an optimistic handler mirroring the
  supplementary-import one.

### 5. Frontend — college "分發結果" tab

- `frontend/lib/api/modules/college.ts`: add `getDistributionResults({ scholarshipTypeId, academicYear, semester })`.
- `frontend/components/college/distribution/DistributionResultPanel.tsx` (new): fetches the endpoint for
  the selected type/year/semester, renders per-sub-type sections with 正取 / 備取 / 未錄取 lists
  (name + 學號). Empty state for 尚未分發 and for 403 (treated as "not open"). zh-TW UI.
- `frontend/components/college/CollegeManagementShell.tsx`: when the selected config's
  `allow_college_view_distribution` is true, render a third tab "分發結果" (change `grid-cols-2` →
  `grid-cols-3`) with `<TabsContent value="distribution">` → `DistributionResultPanel`. Hidden when the
  flag is off. The flag is read from the config the college shell already loads (thread it through
  `college-management-context` if needed).

### 6. Type sync + tests

- Regenerate OpenAPI types: `cd frontend && npm run api:generate` (CLAUDE.md §8), commit
  `lib/api/generated/schema.d.ts`.
- Backend tests (async, integration suite):
  - flag **off** → endpoint returns **403**.
  - flag **on** + distribution executed → correct 正取/備取/未錄取 grouping, **scoped to the caller's
    college only** (a student from another college does not appear).
  - flag **on** + distribution **not** executed → `distribution_executed: false`, empty groups.
  - admin PATCH toggle flips the flag and is rejected for non-accessible scholarships.
  - migration applies cleanly on a fresh DB (`./scripts/reset_database.sh`).
- Lint gate before commit (CLAUDE.md): black (line-length 120), `flake8 --select=B904,B014`,
  `B904 raise ... from`.

## Out of scope

- No change to who can execute/finalize/roster a distribution (admin-only stays).
- No change to the existing unused `GET /college-review/rankings/{ranking_id}/distribution-details`.
- No payment-roster / PII exposure to colleges.
- No global system-wide setting (per-scholarship toggle only).

## Risks / notes

- **College scoping correctness** is the main risk — must confirm the exact field/relationship used to
  match a `CollegeRankingItem`'s student to `current_user.college_code` (the existing endpoint reads
  `student_data.std_academyno`; college-review-service has a canonical scoping path). The
  implementation must reuse the canonical scoping, not invent a new match.
- **N+1:** eager-load `CollegeRankingItem.application` and the sub-type configs (joinedload/selectinload)
  as the existing endpoint does.
- **Flag-state read on the college side:** the tab's visibility depends on the college frontend knowing
  the flag value; ensure it is included in a payload the college already fetches (config / available
  options), not only in admin payloads.
