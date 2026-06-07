# Config-Level Shared Quota Pools (Cross-Config NSTC Borrowing)

- **Date:** 2026-06-08
- **Status:** Approved design — pending spec review (hardened after adversarial code review)
- **Area:** Manual distribution, scholarship configuration, roster generation
- **Branch:** `worktree-config-shared-quota-pools`

---

## 1. Problem

When distributing a scholarship for an academic year (e.g. `phd_115`), administrators need to spend **leftover National Science and Technology Council (國科會 / NSTC) quota from prior years**. Today that capability is expressed two inconsistent ways and neither matches how admins think about it:

- Each config carries `prior_quota_years` like `{"nstc": [113, 112]}` — a list of prior **years**, same scholarship type only.
- The consumed year is recorded as a bare integer `CollegeRankingItem.allocation_year`.
- Prior-year project numbers (and, in dead code, prior-year quota totals) are **duplicated into the current year's config** (`project_numbers["nstc"]["113"]`).

Admins instead want to: **on a config, select which prior config(s) to share quota with — by config code, per sub_type, with no quantity** — and have that quota behave as a **single live shared pool**: if the source config frees a slot (a winner is revoked), the borrowing config immediately gains one.

## 2. Goals

1. Replace the year-list borrow mechanism (`prior_quota_years`) with **explicit config-to-config links** (`shared_quota_sources`), selected by **config code**, **per sub_type**, **cross-type-capable**, **prior years only**, **no quantity**.
2. Make a config's quota a **live, global, shared pool**: `remaining(config, sub_type) = total − every consumer of that config anywhere`. Freeing a slot anywhere instantly updates the pool everywhere.
3. Record **which config each allocated slot consumed** (`allocation_config_id`), and drive roster 計畫編號 / amount from that consumed config.
4. Let admins **edit 計畫編號 (`project_numbers`) in the config UI**.
5. No backward compatibility: revise schema and code directly; migrate existing data.

## 3. Non-goals

- **Per-college quota is NOT removed.** `quotas` stays the per-college matrix `{sub_type:{college:int}}`; college-review ranking, `matrix_based`/`college_based`/`simple` modes, and `MatrixQuotaDisplay` are untouched. The shared pool operates on the **per-(config, sub_type) total** (§6). Borrowing is college-agnostic at the pool level; auto-allocate still enforces per-college caps (§6.4).
- No change to the professor/college review flow or challenge/release *semantics*. (The challenge release **fill-in** code is still re-keyed onto the consumed config — see §6.3 — so it is in scope for edits, just not a behavior change.)
- No quantity/cap on a borrow link (the borrowed amount is always the source config's live remaining).

## 4. Glossary (corrected from initial framing)

| Term | Reality in code | Example |
|---|---|---|
| `ScholarshipType.code` | **Stable, year-agnostic** | `phd`, `direct_phd`, `undergraduate_freshman` |
| `ScholarshipConfiguration.config_code` | **Year-bearing identity** | `phd_112`, `phd_113`, `phd_114` |
| "選獎學金代碼" (the link key) | = **`config_code`** | link `phd_115 → phd_114` |
| `quotas` | per-**college** matrix | `{"nstc":{"E":15,"C":12,…}}` |
| pool total | mode-aware per-(config, sub_type) total (§6.1) | `sum(quotas["nstc"].values())` for matrix configs |

`phd115` / `phd114` in discussion = the **configs** `phd_115` / `phd_114` of the same `phd` type.

## 5. Data model changes

| Object | Field | From | To |
|---|---|---|---|
| `ScholarshipConfiguration` | `prior_quota_years` | `{"nstc":[113,112]}` | **DROP** |
| `ScholarshipConfiguration` | `shared_quota_sources` *(new, JSON)* | — | `[{"source_config_code":"phd_114","sub_types":["nstc"]}]` |
| `ScholarshipConfiguration` | `project_numbers` | `{"nstc":{"114":"114R…","113":"113R…"}}` | `{"nstc":"114R…"}` (own year only) |
| `ScholarshipConfiguration` | `quotas` | `{"nstc":{"E":15,…}}` | **UNCHANGED** |
| `CollegeRankingItem` | `allocation_year` (Int) | `114` | **DROP**, replace with `allocation_config_id` (FK → `scholarship_configurations.id`, nullable) + relationship |
| `CollegeRankingItem` | `allocated_sub_type` | `"nstc"` | **UNCHANGED** |
| `Application` | `allocation_config_id` *(new, FK, nullable)* | — | the config a **renewal** consumes (§9); **never NULL for an approved renewal** |
| `Application` | `renewal_year` | int | **kept, display-only** (no longer a quota key) |
| `PaymentRoster` | `allocation_year` | int | add `allocation_config_id` FK; **keep `allocation_year` as a denormalized display snapshot** = consumed config's `academic_year` |
| `PaymentRosterItem` | `allocation_year` | int | same as `PaymentRoster` |

**`allocation_config_id` NULL has exactly ONE meaning: the "whole-period" sentinel** (the 全期/non-sliced roster path, `roster.sub_type IS NULL AND allocation_config_id IS NULL`). A *per-slice* allocated slot must never be NULL — see §11 backfill, which resolves orphans to the requesting config rather than leaving NULL.

**Storage — JSON column for `shared_quota_sources`** (not a join table): consistent with `quotas`/`project_numbers`, small set always loaded with the config. No DB FK on `source_config_code`; validated at write time (§10).

### `shared_quota_sources` shape

```json
[
  { "source_config_code": "phd_114", "sub_types": ["nstc"] },
  { "source_config_code": "phd_113", "sub_types": ["nstc"] }
]
```

- `source_config_code` must resolve to an **existing** config with `academic_year < this.academic_year` (prior years only).
- `sub_types` ⊆ the source's defined sub_types.
- Cross-type allowed (`phd_115` may list `direct_phd_114`).

## 6. Core algorithm — the live shared pool

New helper on `ManualDistributionService`, the single source of truth reused by the quota grid, distribution-state, finalize gate, and roster validation.

### 6.1 Pool total (mode-aware)

```
pool_total(C, st):
    if C.has_college_quota:            # matrix_based / college_based
        return sum(C.quotas.get(st, {}).values())
    else:                              # simple / none — quotas[st] is a scalar (or total_quota)
        return int(C.quotas.get(st, 0)) or C.total_quota_for(st)
```

> ⚠️ Implementation note: `get_sub_type_total_quota` returns 0 when `has_college_quota` is False (e.g. seeded `direct_phd_114`). The helper above must NOT call it blindly — it must handle non-matrix configs, or a cross-type borrow from such a config reads an empty pool. Verify the scalar path against each `quota_management_mode` before relying on it.

### 6.2 Live global consumers (guaranteed partition)

```
consumers(C, st) =
    count CollegeRankingItem ri
        WHERE ri.is_allocated
          AND ri.allocated_sub_type == st
          AND ri.allocation_config_id == C.id
          AND ri.application.is_renewal == False        # general/manual winners ONLY
  + count Application a
        WHERE a.is_renewal
          AND a.status == approved
          AND a.sub_scholarship_type == st
          AND a.allocation_config_id == C.id            # renewals ONLY

remaining(C, st) = pool_total(C, st) − consumers(C, st)   # GLOBAL, LIVE
```

**Why the explicit `is_renewal == False` guard:** `college_review_service` builds a `CollegeRankingItem` for *every* application **including renewals** (`college_review_service.py:636-657`, renewals sorted first). Renewal ranking items normally stay `is_allocated=False`, but `restore_allocation` flips `is_allocated=True` for any item with `allocated_sub_type` set, and revoke/suspend/restore endpoints have **no `is_renewal` guard** (`manual_distribution.py:689-759`). Without the guard, a revoked-then-restored renewal would be counted in *both* halves. The two halves must be a **guaranteed partition**, not an assumed one.

### 6.3 The distributable pool & challenge release

For a distribution of config `P` (e.g. `phd_115`):

```
pool(P, st) = remaining(P, st)
            + Σ remaining(S, st)  for each link {S, sub_types} in P.shared_quota_sources where st ∈ sub_types
```

Each pool column maps to a **specific config**; an allocation records that `allocation_config_id`. Because `consumers` counts every allocated slot pointing at a config regardless of which round created it, revoking an `S` winner raises `remaining(S, st)` and `P` sees it on the next state fetch — the shared-pool requirement.

**Challenge release / fill-in (`execute_general_distribution`)** must key the freed-slot map `released[]` on the **cancelled renewal's `allocation_config_id`** (not `renewal_year`), and the waitlist fill-in must **re-derive `remaining(freed_config, st)`** rather than trust a raw release count. Legacy renewals whose `allocation_config_id` is unresolved would mis-attribute the freed slot — mitigated by §11.3 (renewals are never left NULL).

This replaces `_pick_pool` (returns a **config**, prefer own `P` then linked configs by descending year), `_build_remaining_quota`, and the dead year-keyed readers.

### 6.4 Auto-allocate keeps per-college caps

`auto_allocate_preview`'s tracker is re-keyed to **`(allocation_config_id, sub_type, college)`** (per-college caps from the *consumed* config's matrix) while the cross-config pool cap is `pool(P, st)`. **Both caps apply (min)** so per-college matrix enforcement survives (satisfies §3). This is the largest single algorithm rewrite.

## 7. Distribution flow + grid UI

- Grid columns change from **(sub_type × year)** to **(sub_type × source-config)**: the own config column plus one per linked source config, each labeled by config (e.g. `nstc · phd_114`) with live `remaining`. Linked columns keep the existing "backfill" treatment.
- `allocate` request item: `{ranking_item_id, sub_type_code, allocation_config_id}` (was `allocation_year`). Server validates `allocation_config_id ∈ allowed set` = **{own config P} ∪ {linked S whose `shared_quota_sources` entry lists this sub_type}**, and re-derives `remaining` server-side; the FE count is advisory.
- Auto-allocate suggestion output: `{ranking_item_id, sub_type_code, allocation_config_id}`.
- **Frontend pool-grid changes are contained to** `ManualDistributionPanel.tsx` + `lib/api/modules/manual-distribution.ts`. Other FE modules (`student-history`, `payment-rosters`, `PaymentHistoryTable`, `RosterListTable`, `RosterDetailDialog`, `StudentRosterPreview`) read `allocation_year` only as a **roster display value**, preserved by §8's denormalized snapshot — they need no change but should be audited (§13).

## 8. Roster generation

- Group allocated `CollegeRankingItem`s by **(allocation_config_id, sub_type)** (was `(allocation_year, sub_type)`). `allocation_config_id NULL` ⇒ the whole-period bucket (unchanged sentinel).
- **Resolve the consumed config per group** (not one up-front config): `generate_rosters_from_distribution` currently fetches a single requesting config before grouping (`roster_service.py:1494-1503`); the consumed config must be loaded per `allocation_config_id` group and passed into `_generate_one_sub_type_roster`.
- **Per consumed config:** `project_number = consumed_config.project_numbers.get(sub_type)` (flattened, no year key); `scholarship_amount = application.amount or consumed_config.amount` (keep the per-application override; only the fallback changes from requesting → consumed config). `_create_roster_item` (`roster_service.py:819-880`) must load the consumed config via `allocation_config_id` and re-key its independent allocation re-derivation onto it.
- **Cross-type borrow field sourcing (decided):** for a borrowed slot, `project_number`, `scholarship_amount`, and the `allocation_year` display snapshot (= consumed config's `academic_year`) come from the **consumed** config; `scholarship_name` stays the **requesting** config's scholarship type name (the award the student actually holds). For same-type borrows (the common case) the two configs share a name so this is moot.
- `PaymentRoster`/`PaymentRosterItem` store `allocation_config_id`; `allocation_year` is set to the consumed config's `academic_year` as a frozen display snapshot (keeps Excel export / student-history / list views working with no join).
- **Rebuilt unique index** `uq_roster_scholarship_period_alloc` = `(scholarship_configuration_id, period_label, COALESCE(allocation_config_id,-1), COALESCE(sub_type,''))` — **sub_type retained** (two rosters share a config but differ by sub_type, e.g. `nstc` vs `moe_1w`).
- Reconcile (`_resolve_distribution_for_roster`, `get_distribution_diff_for_roster`, `reconcile_roster`) and the `payment_rosters.py:589-637` `allocation_map` builder match/read on `allocation_config_id`.
- **Alternate promotion** (`alternate_promotion_service.py:112-117`) currently copies `allocated_sub_type` only and sets **no** allocation year/config (a pre-existing gap). It must now copy `allocation_config_id` from the displaced item; otherwise the promoted alternate becomes a whole-period NULL and lands in the wrong roster. This code change must ship atomically with the migration.

## 9. Renewals

A renewal (續領) continues a specific prior award, so it **consumes the same config that prior slot consumed**. (Renewals **are** `CollegeRankingItem`s — `is_allocated=False` — not separate from them; the §6.2 partition handles this.)

- At renewal creation (`create_renewal_from_previous`), resolve `previous_application_id → previous app's CollegeRankingItem.allocation_config_id` and snapshot it onto the new renewal's `Application.allocation_config_id`. **Fallback when the prior slot is unresolved: the renewal's own `scholarship_configuration_id`** — an approved renewal is **never** left NULL (NULL would make it uncounted in §6.2 → pool inflation → over-allocation).
- `consumers()` counts approved renewals by `Application.allocation_config_id` — one indexed query, no recursive `previous_application_id` walk. `_count_approved_renewals_per_pool` is replaced by / re-keyed onto this.
- `renewal_year` is **display-only** (e.g. `RenewalOccupiedBlock`, challenged-renewal payloads) and out of quota math.
- `_batch_load_previous_allocation_years` returns the prior slot's `allocation_config_id` (to seed the renewal snapshot and suggest its column).

## 10. Concurrency & validation

- **Server-side quota gate (net-new).** Before commit, `allocate` and `finalize` must **`SELECT … FOR UPDATE` the consumed `scholarship_configurations` rows for the round — the own config `P` and every linked source `S`** (locking the config rows is what serializes two overlapping rounds; locking the disjoint ranking items would provide no mutual exclusion). Under that lock, recompute `remaining(C, st)` via §6.2 and reject (or truncate with an explicit error) if any consumed config is oversubscribed. Today neither path locks or recounts, so this is entirely new logic.
- **Link write validation** (config create/update, imperative — see §13): each `source_config_code` must exist, have `academic_year < this.academic_year`, and define every listed sub_type. Fail-fast otherwise.

## 11. Migration plan

One Alembic migration, `down_revision = '20260531_perf_indexes'` (verified single head), existence-checked per project convention. **Order matters** — the project_numbers data-move precedes the flatten.

1. **`college_ranking_items`**: add `allocation_config_id` INT FK nullable. Backfill from `allocation_year` resolving `(ranking.scholarship_type_id, academic_year = allocation_year, semester)` → `ScholarshipConfiguration.id`, using the **existing 3-way semester normalization** (`_ranking_semester_condition`/`_config_semester_condition`: ranking `semester ∈ {NULL,'annual','yearly'}` ↔ config `semester ∈ {NULL,'yearly'}`) — a raw equality join orphans the dominant yearly-PhD case. If `>1` config matches (NULL-semester is not uniquely constrained), tie-break `ORDER BY id DESC LIMIT 1` (matches `get_quota_status`). **Per-slice items that still fail to resolve are pointed at the requesting config's id (never left NULL)** and counted; log the orphan count. Then **drop `allocation_year`** from this table.
2. **`payment_roster_items` / `payment_rosters`**: add `allocation_config_id`, backfill from `allocation_year` (same normalization); **keep `allocation_year`** repurposed as the display snapshot (= consumed config `academic_year`). Rebuild `uq_roster_scholarship_period_alloc` to `COALESCE(allocation_config_id,-1)` **retaining `COALESCE(sub_type,'')`**.
3. **`applications`**: add `allocation_config_id` INT FK nullable. Backfill renewals from `previous_application_id`'s slot config; **on failure fall back to the renewal's own `scholarship_configuration_id` — never NULL for an approved renewal** (§9).
4. **`scholarship_configurations` project_numbers data-move + flatten** *(before drop):* for each config holding borrowed-year project codes (e.g. `phd_114.project_numbers["nstc"]["113"] = "113R000001"`), **push that code into the source config's own-year entry** (`phd_113.project_numbers["nstc"] = "113R000001"`) — the source configs `phd_112/113` currently have `project_numbers=NULL`, so without this the codes are permanently lost. Then flatten every config's `project_numbers` to `{sub_type: own-year code}` (keep only the entry whose year == own `academic_year`).
5. **`scholarship_configurations` links:** add `shared_quota_sources` JSON. Backfill from `prior_quota_years` (each year → same-type `config_code`). **Drop (and log) any link whose target config does not exist** (e.g. `phd_114`'s `prior_quota_years` lists `112` but **no `phd_112` config exists**) — consistent with §10. **DROP `prior_quota_years`.**
6. **History JSON re-key:** `manual_distribution_history.allocations_snapshot` stores per-item `{sub_type, allocation_year, status}` and `restore_from_history` writes `item.allocation_year` from it. Re-key existing snapshots `allocation_year → allocation_config_id` (same semester-aware resolution) and update save/restore-history to read/write `allocation_config_id`, or in-flight undo silently corrupts.
7. **Seed** (`seed_scholarship_configs.py`, `seed_distribution_test_data.py`): create the prior-year sibling configs that seeded `shared_quota_sources` point to (e.g. `phd_112`) each carrying its own `quotas` + own-year `project_numbers`; replace `prior_quota_years` with `shared_quota_sources`; single-year `project_numbers`; add `shared_quota_sources` to the existing-config re-sync block; replace `CollegeRankingItem(allocation_year=…)` with `allocation_config_id`.

**Pre-drop audits (fail loud):** count allocated per-slice items resolving to NULL; count approved renewals resolving to NULL; count `shared_quota_sources` links with missing target configs. Run against real data before the destructive drops.

## 12. Dead-code reconciliation

Two contradictory live interpretations of `quotas` exist; this design settles them:

- **College-matrix family — KEPT** (model helpers, **`get_quota_status` ← the LIVE quota-grid driver**, `quota_service`, college-review, matrix endpoints, `MatrixQuotaDisplay`): reads `{sub_type:{college:int}}`. `get_quota_status` (`manual_distribution_service.py:385`) is what the panel grid actually calls (`/quota-status` → `by_year`); it must move onto `remaining()`/`pool()` (§6). This is the real rewrite, and it introduces the renewal-visibility behavior change (§17.1).
- **Year-keyed Phase-6 family — DEAD in production, REWRITTEN** (`_build_remaining_quota`, `_pick_pool`, `compute_distribution_state.available_quotas`, `execute_general_distribution`): assumes `{sub_type:{year_str:total}}`, silently skips the real college data → computes empty pools today. `execute_general_distribution` has only test callers (no endpoint), so its rewrite is lower-risk — but it is still the canonical general-phase + challenge-release algorithm and must be rebuilt onto §6.

`get_quota_status`'s prior-year join (loads sibling configs by `prior_quota_years` years) is replaced by loading configs named in `shared_quota_sources`.

## 13. Affected files (full surface map + adversarial additions)

**Backend models:** `college_review.py` (allocation_config_id), `scholarship.py` (shared_quota_sources / project_numbers flatten; matrix helpers unchanged), `payment_roster.py` (mirror cols + unique index), `application.py` (allocation_config_id).

**Backend services:** `manual_distribution_service.py` (`allocate`, `finalize` + lock gate, `restore_from_history` + save-history snapshot, `get_quota_status`, `compute_distribution_state`, `_pick_pool`, `_build_remaining_quota`, `_count_approved_renewals_per_pool`, `_batch_load_previous_allocation_years`, `_compute_suggestions`, `auto_allocate_preview`, `execute_general_distribution`), `roster_service.py` (`generate_rosters_from_distribution` per-group config, `_generate_one_sub_type_roster`, `_create_roster_item` consumed-config load, `_resolve_distribution_for_roster`, `get_distribution_diff_for_roster`, `reconcile_roster`), `alternate_promotion_service.py` (copy `allocation_config_id` — **new behavior**), `excel_export_service.py` (display year from snapshot), `application_service.py` (`create_renewal_from_previous` snapshot + fallback), `student_scholarship_history_service.py`, `college_review_service.py` (renewal ranking-item awareness for §6.2 partition).

**Backend endpoints/schemas:** `manual_distribution.py` (`AllocationItem.allocation_config_id`, grouping, lock gate), `payment_rosters.py` (`allocation_map` from `allocation_config_id`), `renewal.py`, `scholarship_configurations.py` — **project_numbers + shared_quota_sources are written via the untyped `config_data` dict in THREE places**: the primary create constructor (`:757`, currently omits `project_numbers`), the **duplicate-config** path (`:1208`, copies none of `quotas`/`prior_quota_years`/`project_numbers` — must carry all over), and update (`:1032`, add `flag_modified` branches for both new fields). `scholarship_configuration.py` schema (`quotas` stays nested `Dict[str,Dict[str,int]]`; add `project_numbers: Optional[Dict[str,str]]`, `shared_quota_sources: Optional[List[SharedQuotaSource]]`). `roster.py` / `payment_roster.py` / `student_scholarship_history.py` schemas. **§10 link validation is imperative in the endpoint** (no schema-level FK).

**Frontend:** `ManualDistributionPanel.tsx`, `lib/api/modules/manual-distribution.ts`, `admin-configuration-management.tsx` (link picker + project_numbers field; both create & edit forms + `formData` init + `openEditDialog`), `lib/api/types.ts` (narrow `quotas`, add `shared_quota_sources`; `project_numbers: Record<string,string>`), regenerate `lib/api/generated/schema.d.ts`.

**Backend tests (fixture + assertion rewrites — were missing):** `test_distribution_state_endpoint.py` (year-keyed quotas + prior_quota_years fixture; available_quotas-by-allocation_year asserts), `test_challenge_release_distribution.py`, `test_renewal_end_to_end.py`, `test_restore_allocation_service.py`, `test_roster_distribution_reconcile_service.py`, `backend/tests/test_auto_allocate_preview.py` (`_compute_suggestions` allocation_year output + (sub_type,year,college) tracker), `test_excel_export*pure_helpers` (display year). **Frontend test:** `lib/api/modules/__tests__/manual-distribution.test.ts` (allocate body pins `allocation_year`).

**Migration/seed:** new Alembic migration; `seed_scholarship_configs.py`; `backend/scripts/seed_distribution_test_data.py`.

## 14. Testing strategy

- **Unit (pool math):** `pool_total` for matrix AND non-matrix (`has_college_quota=False`) configs; `consumers()` partition (general winner counted once; renewal counted once via Application half; revoked-then-restored renewal not double-counted); `remaining()` global; `pool()` = own + linked; revoking a source winner raises the borrower's pool; cross-type link; prior-year-only + missing-target-config validation.
- **Integration (async):** allocate into a linked config → roster consumes that config's project_number/amount; finalize lock rejects oversubscription under concurrent rounds; renewal snapshot attribution + never-NULL fallback; alternate promotion inherits `allocation_config_id`.
- **Migration:** fresh DB via `reset_database.sh`; backfill `allocation_year → allocation_config_id` incl. `'annual'`-semester yearly-PhD, NULL/whole-period, renewal_year-derived; **project_numbers data-move preserves `113R000001`/`112R000001`**; `prior_quota_years → shared_quota_sources` drops the missing-`phd_112` link with a log; history JSON re-key; pre-drop audit counts are zero (or expected).
- **Roster reconcile:** diff matches on `allocation_config_id`; whole-period roster still holds all items.
- **Frontend:** grid renders config columns with live remaining; allocate payload carries `allocation_config_id`; config editor link picker + project_numbers field round-trip.
- Lint gate: `black --line-length=120`, `flake8 --select=B904,B014`, logger-traceback invariants.

## 15. Open risks

1. **Backfill orphans** — per-slice items / approved renewals that can't resolve are pointed at the requesting / own config respectively (never NULL); the audit must confirm counts are sane before the drop. A wrong tie-break (duplicate NULL-semester configs) could mis-attribute slots.
2. **`auto_allocate_preview`** is the largest rewrite (per-college tracker re-keyed onto `(allocation_config_id, sub_type, college)` while honoring the cross-config pool cap).
3. **Display-snapshot drift** — roster `allocation_year` snapshot is frozen at generation; editing a config's `academic_year` later won't update it (acceptable — rosters are point-in-time).
4. **Missing sibling configs** — borrowing only works if the source config row exists; the seed must create `phd_112` etc. Dangling `prior_quota_years` years are dropped, so an admin who relied on a 112 borrow loses it until a `phd_112` config + link is created.

## 16. Resolved during spec review

1. **Cross-type roster naming (§8):** `scholarship_name` follows the **requesting** config; `project_number` / `amount` / display-year follow the **consumed** config. (Moot for same-type borrows.)
2. **Quota gate (§10):** enforce at **both** allocate and finalize — `SELECT … FOR UPDATE` on the consumed config rows + recount at each.

## 17. Behavior changes vs today (QA call-outs)

1. **Renewals now consume the displayed pool.** Today the grid driver `get_quota_status` counts only `is_allocated` ranking items and **never subtracts renewals**; `remaining()` (§6) subtracts them. After this change the grid's remaining will be **lower** than today for any config with approved renewals. Intentional — renewals genuinely occupy slots.
2. **Server-side quota enforcement is net-new.** Today `_validate_allocations` defers quota checks to the frontend ("Quota validation is done real-time via the quota-status endpoint on the frontend", `manual_distribution_service.py:918-919`); allocate/finalize never lock or recount. §10 adds a server gate.
3. **Roster 計畫編號 / amount source moves** from the requesting config (keyed by year string) to the consumed config.
