# 匯入續領生 (Import Renewal Students) — Design

- **Date:** 2026-07-09
- **Branch:** `worktree-import-renewal-students` (forked from `origin/main` @ 68104776)
- **Status:** Approved design — ready for implementation plan
- **Author:** Design brainstormed with the maintainer (anud18)

## 1. Summary

Add an admin feature to import a spreadsheet of renewal candidates ("續領生"). The system imports **only the renewal-passed rows** as **approved renewal applications** attached to an admin-chosen scholarship + academic year, so that the existing 造冊 (payment-roster generation) includes them.

A row is imported iff `學生是否申請續領 = 是` **and** `續領審核結果 = 通過`.

## 2. Background & the core gap

The system already has a general **batch importer** (`batch_import_service.py` / `batch_import.py` / `batch-import-panel.tsx`) that parses a student spreadsheet, SIS-looks-up each 學號, upserts `UserProfile` (postal account, advisor), auto-assigns the reviewing professor, and creates applications that **enter the review flow** (`status=submitted → under_review`). This renewal import reuses that plumbing but produces the opposite kind of record: **approved, review-bypassing** applications.

Renewal ("續領") is modelled as a flag + lineage on `Application` (`is_renewal`, `previous_application_id`, `allocation_config_id`, `renewal_year`) plus dedicated date windows on `ScholarshipConfiguration`. Approved renewals consume quota via the Application table.

**The core gap this feature must close:** approved renewals **never appear in matrix-mode 造冊 today.** `RosterService.generate_rosters_from_distribution` (`roster_service.py:1478`) builds roster groups *exclusively* from `CollegeRankingItem` rows with `is_allocated=True` (lines 1556-1577), and `ManualDistributionService._winner_filters` (`manual_distribution_service.py:213`) explicitly pins `Application.is_renewal.is_(False)`. Renewals get no allocated ranking item, so the roster generator cannot see them — for *any* renewal, not just imported ones. The system already defines the correct predicate for "an approved renewal consuming `(allocation_config_id, sub_scholarship_type)`" in `ManualDistributionService._renewal_filters` (`manual_distribution_service.py:216-224`); roster generation is the one place that never applies it. Bridging that is part of this feature and fixes the latent gap for all renewals.

## 3. Requirements

### Functional
1. Admin selects **scholarship type + academic year + semester**; the selected `ScholarshipConfiguration` **must be in its renewal period** (`renewal_application_start_date … renewal_application_end_date` bracket "now"), else the import is rejected.
2. Admin downloads a template and uploads a filled Excel; a **preview** is returned before anything is created.
3. Only `是 + 通過` rows are imported; other rows are shown as *skipped* with a reason.
4. Each imported row becomes an **approved renewal `Application`** structurally identical to a normal approved renewal.
5. The `獎學金類別` column selects the sub-type: `國科會 → nstc`, `教育部 → moe_1w` (validated against the scholarship's real `sub_type_list`).
6. `郵局帳號` and `指導教授本校人事編號` are carried onto the application/profile exactly as the batch importer does.
7. `造冊` (existing generate-rosters-from-distribution flow) includes the imported (and all other approved) renewals, and can generate a roster from **renewals alone** for a year/sub-type with no new-student distribution.

### Non-goals
- No student self-apply, no professor/college review windows (these bypass review entirely).
- No handling of 否/failed rows beyond showing them skipped in the preview.
- No per-record inline editing in the preview (admin fixes the sheet and re-uploads — YAGNI).
- No document/ZIP upload step (renewals don't need per-application documents here).
- No change to the general batch importer's behaviour.

## 4. Decisions (made during brainstorming)

| # | Decision | Choice |
|---|----------|--------|
| D1 | Purpose | Import renewal-**passed** students so 造冊 includes them (not a full outcome recorder) |
| D2 | Decision driver | `是` + passing `續領審核結果` (`通過`); both columns required |
| D3 | Target scholarship | Matrix / sub-typed (NSTC-MOE PhD), goes through manual-distribution → 造冊 |
| D4 | Sub-type / allocation source | A `獎學金類別` column **in the sheet**; admin picks the year to import into; that year's config must be in its renewal window |
| D5 | Code structure | **Dedicated** renewal-import module (not overloading the batch importer) |
| D6 | Roster bridge | **Extend the shared roster generator** to include approved renewals (fixes the systemic gap) |
| D7 | Import record storage | **Reuse `BatchImport`** + an `import_type` discriminator |
| D8 | Quota policy | **Warn, don't block** on over-quota |
| D9 | Pure-renewal roster | **Supported** — relax generator guards so renewals alone can produce a roster |

## 5. Detailed design

### 5.1 Data model

No new columns on `Application`; reuse existing ones. Two additive changes only:

- **`BatchImport.import_type`** — new `String(20)`, `NOT NULL`, default `"application"`, indexed. Values: `"application"` (existing batch import) | `"renewal"` (this feature). Migration includes an existence check (per CLAUDE.md).
- **`Application.import_source`** — already `String(20)`; use the new string value `"renewal_import"` (no migration; existing values are `online`/`batch_import`).

`BatchImport.college_code` is `NOT NULL`; for an admin-run renewal import set it to `current_user.college_code or ""`.

### 5.2 Spreadsheet & template

Columns (existing 10 + one new). Header-based parser (not positional):

```
編號 · 學院 · 系所 · 學生姓名 · 學號 · 學生年級 · 學生是否申請續領 · 續領審核結果 · 獎學金類別 · 郵局帳號 · 指導教授本校人事編號
```

- **`獎學金類別`** (new): cell value `國科會` → `nstc`, `教育部` → `moe_1w`. The mapping is derived from the scholarship's `sub_type_list` labels (`sub_type_labels`), so it extends automatically if the scholarship defines more sub-types.
- `學院 / 系所 / 學生姓名 / 學生年級` are **human-readable only**; the source of truth is the SIS snapshot (`std_academyno / std_depno / std_cname`; grade derived from termcount). Displayed in the preview, optionally flagged on mismatch, never required.
- Required headers for a valid file: `學號`, `學生姓名`, `學生是否申請續領`, `續領審核結果`, `獎學金類別`. Optional: `郵局帳號`, `指導教授本校人事編號`.
- A `GET /template` endpoint generates the sample file with one example row and a comment documenting the `獎學金類別` values.

### 5.3 Parsing & validation rules

**Import filter (row kept iff both):**
- `學生是否申請續領` normalizes to `是`
- `續領審核結果` normalizes to `通過`

Non-passing rows are retained in the preview payload marked `skipped` with the reason; they are never created.

**Row errors (kept row excluded from creation, surfaced per-row):**
- SIS student not found for 學號 (cannot populate `std_stdcode/std_cname/std_pid`, which the roster requires).
- `獎學金類別` not mappable, or the mapped code not in the config's `sub_type_list` (reject the `general` fallback, per PR #845).
- Student already has an approved renewal for this config (would violate the `uq_user_renewal_app` partial unique index).
- In-file duplicate 學號.

**Warnings (non-blocking):**
- `郵局帳號` blank → the student will be flagged `缺少銀行帳戶資訊` at roster time and dropped from the roster Excel.
- Optional: `學院`/`系所` in the sheet mismatch the SIS `std_academyno`/`std_depno` (informational only).
- **Over-quota (D8):** if the count of passed renewals for a `(config, sub_type)` plus current `consumers_count(config_id, sub_type)` exceeds the configured quota, warn with the numbers; do not block.

### 5.4 Application creation contract (per imported 通過 row)

One `Application` per row, in a single all-or-nothing transaction, structurally identical to a normal approved renewal so quota/roster code treats it the same:

| Field | Value |
|-------|-------|
| `is_renewal` | `True` |
| `renewal_year` | selected academic year (ROC) |
| `previous_application_id` | best-effort lookup of the student's prior approved app for this scholarship type (optional; used for lineage) |
| `status` | `approved` |
| `review_stage` | `quota_distributed` (matches `RenewalDistributionService.auto_approve_passed_reviews`) |
| `approved_at` | now |
| `quota_allocation_status` | `allocated` |
| `sub_scholarship_type` | mapped code (`nstc`/`moe_1w`); `scholarship_subtype_list=[code]` |
| `scholarship_configuration_id` / `allocation_config_id` | the selected year's config id (both equal — the renewal consumes the year it's imported into) |
| `academic_year` / `semester` | from the selection |
| `amount` | `scholarship_config.amount` — **must be non-NULL**, because the roster reads `application.amount or consumed_config.amount` into the `NOT NULL` `PaymentRosterItem.scholarship_amount` (`roster_service.py:920`). |
| `student_data` | SIS snapshot via `student_service.get_student_snapshot(學號, academic_year, semester)` (`std_stdcode/std_cname/std_pid/com_email`) |
| `submitted_form_data` | **flat** dict `{"postal_account": <郵局帳號>, "advisor_name": ..., "advisor_nycu_id": ..., "custom_fields": {}}` — matches how `create_applications_from_batch` builds it (`batch_import_service.py:816-822`); the roster's `_create_roster_item` reads the postal account from the flat structure (`roster_service.py:837-839`). |
| `app_id` | generated **inline** — lock `ApplicationSequence` `with_for_update`, `ApplicationSequence.format_app_id(...)`, then append suffix `"R"` (batch uses `"U"`; `batch_import_service.py:757-794`). Not via `_generate_app_id` (which takes no suffix). |
| `import_source` | `"renewal_import"` |
| `imported_by_id`, `batch_import_id` | set |
| `User` (student) | resolve/create via the batch service's `_get_or_create_users_bulk` |

**Ground-truth correction (verified against `origin/main`):** there is **no** `application_builder.py`, `_upsert_user_profile`, `_build_submitted_form_data`, or `assign_professor_from_profile` in this branch (those were from the unmerged PR #1129 refactor). Accordingly, this import — like the real `create_applications_from_batch` — does **not** upsert `UserProfile` and does **not** auto-assign a professor; the advisor personnel id / name are carried in `submitted_form_data`. Reuse is limited to `_get_or_create_users_bulk` and the inline app-id sequence pattern; the renewal field-set mirrors `ApplicationService.create_renewal_from_previous` (`application_service.py:3027`), overriding `status=approved` / `review_stage=quota_distributed`.

### 5.5 Roster-generator extension (the bridge)

All changes in `roster_service.py` (sync), keyed on the existing `_renewal_filters` semantics replicated as sync predicates: `is_renewal=True, status=approved, sub_scholarship_type==sub_type, allocation_config_id==config_id`, `deleted_at IS NULL`.

**`generate_rosters_from_distribution` (`:1478`):**
1. After building `groups` from `is_allocated` ranking items, **query approved renewals** scoped to the run — approved renewals whose `allocation_config_id` belongs to a config of `scholarship_type_id`, with `academic_year == academic_year` and matching semester bucket.
2. For each renewal, compute `key = (allocation_config_id, sub_scholarship_type or "general")`; append its `application_id` to `groups[key]`, creating the group (and loading its `consumed_config`) if absent.
3. **Relax guards (D9):** `if not rankings: raise` and `if not allocated_items: raise` become "raise only if there are also no approved renewals." When rankings are absent, `ranking_ids = []` and renewal-only groups get `roster.ranking_id = None` (column is nullable).

**`_generate_one_sub_type_roster` (`:1641`):** the per-group application set already re-fetches by `id.in_(application_ids) + status=='approved'` — renewals satisfy this. No change beyond feeding the merged id set.

**`_create_roster_item` (`:795`) — two fixes for renewals (which have no `CollegeRankingItem`):**
- `application_identity` (line 906): change `if application.is_renewal and application.previous_application_id:` → `if application.is_renewal:` so imported renewals are labelled `{year}續領`, not `{year}新申請`.
- `allocated_sub_type` (after lines 855-892): fall back to `application.sub_scholarship_type` when no ranking item is found, so the item's sub-type snapshot is populated for renewals.

No new roster endpoint: the admin triggers the existing `POST /college-review/…/generate-rosters-from-distribution` (the 生成造冊 button) and renewals are now swept in.

### 5.6 Backend structure (new, focused files)

- `backend/app/services/renewal_import_service.py` — `RenewalImportService` (async): parse → filter → SIS-lookup → validate → preview → create. Reuses the batch service's `_get_or_create_users_bulk` and inline app-id pattern.
- `backend/app/api/v1/endpoints/renewal_import.py` — endpoints under `/college-review/renewal-import`, same `require_college_role` guard as batch import:
  - `POST /upload` (scholarship_type, academic_year, semester query params; validates renewal window; returns preview)
  - `POST /{id}/confirm`
  - `GET /{id}/details`
  - `GET /history`
  - `GET /template`
- `backend/app/schemas/renewal_import.py` — `RenewalImportRow` (all fields **explicitly declared** — avoids the `ApplicationDataRow` silent-drop trap from PR #1129), upload/preview/confirm/detail responses. Standard `{success, message, data}` envelope.
- Edits: `batch_import.py` history query filtered to `import_type == "application"`; `roster_service.py` (§5.5); OpenAPI regen.

### 5.7 Frontend

- `frontend/components/renewal-import-panel.tsx` — mirrors `BatchImportPanel` but simpler (no document step): selectors, renewal-window status indicator, template download, upload → preview table (per row: 學號, 姓名, 獎學金類別, 是否申請, 審核結果, matched student ✓, professor ✓/warn, 郵局帳號 ✓/warn, will-import?), confirm, history.
- `frontend/lib/api/modules/renewal-import.ts` — `apiClient.renewalImport` methods (upload/confirm/details/history/downloadTemplate), token-authenticated `fetch` for the template download.
- Mounted next to the batch-import entry (`frontend/app/page.tsx`), likely as a sibling tab/panel.
- Field-label i18n additions under a `renewal_import.*` namespace.

## 6. Edge cases & invariants

- **Idempotency / re-upload:** a student who already has an approved renewal for the config is a row error (and the DB partial unique index `uq_user_renewal_app` is the backstop).
- **§9 invariant:** every created renewal has non-NULL `allocation_config_id`.
- **No double-counting:** the roster extension uses `_renewal_filters` (which is disjoint from `_winner_filters` via the `is_renewal=False` guard on winners), so a renewal is counted once. Covered by a test asserting parity with `consumers_count`.
- **Semester buckets:** yearly scholarships store `semester = NULL`; reuse `_build_semester_filter`.
- **Renewal-only roster:** `PaymentRoster.ranking_id = NULL`, `trigger_type` set, `sub_type`/`allocation_year`/`allocation_config_id` from the consumed config.
- **SIS unavailable:** a row whose 學號 cannot be resolved is a row error (excluded), because an approved renewal missing `std_pid` cannot be rostered.

## 7. Testing strategy

Async service → async tests (per CLAUDE.md test-suite layout).

- **Parser:** `是+通過` filter; skip reasons; `獎學金類別` mapping and rejection of unmapped / non-`sub_type_list` values; header detection; in-file duplicate detection.
- **Preview validation:** SIS-not-found row error; professor_not_found warning; blank 郵局帳號 warning; existing-renewal duplicate; over-quota warning math.
- **Create:** the full approved-renewal field contract (§5.4); `submitted_form_data.postal_account`; `UserProfile` upsert; professor assignment; all-or-nothing rollback.
- **Roster extension:** renewals merged into an existing `(config, sub_type)` group; renewal-only group creates a roster with `ranking_id=NULL`; `application_identity` = `續領`; `allocated_sub_type` populated from the application; `consumers_count` parity / no double-count; guard relaxation.
- **Lint gates:** black (line-length 120), flake8 `B904,B014`, logger-traceback AST invariant.

## 8. Migration & rollout

- Alembic migration: add `batch_imports.import_type` with an existence check; backfill existing rows to `"application"`.
- Test on a fresh DB via `./scripts/reset_database.sh`.
- Regenerate OpenAPI types (`cd frontend && npm run api:generate`) after the endpoints exist.

## 9. File-by-file change list

**New**
- `backend/app/services/renewal_import_service.py`
- `backend/app/api/v1/endpoints/renewal_import.py`
- `backend/app/schemas/renewal_import.py`
- `backend/alembic/versions/<rev>_add_batch_import_import_type.py`
- `frontend/components/renewal-import-panel.tsx`
- `frontend/lib/api/modules/renewal-import.ts`
- backend tests: `test_renewal_import_service_unit.py`, roster-extension tests

**Edited**
- `backend/app/models/batch_import.py` (+`import_type`)
- `backend/app/services/roster_service.py` (§5.5)
- `backend/app/api/v1/endpoints/batch_import.py` (history filter `import_type=="application"`)
- `backend/app/api/v1/api.py` (register new router)
- `frontend/app/page.tsx` (mount panel) + i18n
- `frontend/lib/api/generated/schema.d.ts` (regen)
