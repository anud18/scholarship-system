# 造冊名單 Excel：資格驗證資訊 + 不符合儲存格紅底

**Date:** 2026-06-30
**Status:** Approved (design)
**Scope:** `backend/app/services/excel_export_service.py` (+ tests)

## Goal

The roster (造冊) Excel — the STD_UP_MIXLISTA payment-format sheet produced by
`ExcelExportService.export_roster_to_excel` — should carry **eligibility
verification information**, including **one column per scholarship rule**, and
**highlight the specific failing cells with a red background** (warning-rule
failures use amber). This turns the roster Excel into a review document that
lets an admin see, at a glance, exactly why any student is non-compliant.

## Key facts (verified)

- **No `.xlsx` template file exists in the repo.** `_load_template_structure`
  always falls back to `_set_default_columns`, and `_create_excel_file` always
  builds a fresh `Workbook` (the `use_template` branch is dead in practice).
  So extending the column set is purely a matter of extending the default list
  and the data-writing loop.
- `self.field_mapping` in the export service is **dead** (never read elsewhere).
- `item.excel_row_data` is **write-only** (no consumers) — safe to extend.
- **Per-rule results are already frozen on each item.**
  `RosterService._validate_student_eligibility()` loops
  `_evaluate_scholarship_rule()` over `_get_scholarship_rules()` and stores the
  outcome in `item.rule_validation_result["details"]`, keyed `"rule_<id>"`:

  ```python
  {"passed": bool, "rule_name": str, "rule_type": str,
   "is_hard_rule": bool, "is_warning": bool, "message": str, ...}
  ```

  This is populated in **both** `generate_roster` and
  `generate_rosters_from_distribution`. The Excel layer therefore **reads the
  frozen snapshot** — no DB access, no re-evaluation, and guaranteed consistent
  with the recorded `is_eligible` / `failed_rules`. Rule-evaluation logic stays
  in `RosterService` as the single source of truth.

## Reuse decision

Instead of re-querying or re-running rules in the Excel layer, reuse the
**already-stored** `rule_validation_result["details"]`. The only new logic is a
**pure presentation helper** that turns those per-item details into a stable,
ordered set of columns.

## Columns

### Static base (unchanged)
The existing 30 STD_UP_MIXLISTA columns (`身分證字號` … `分發獎學金`).

### Appended verification columns
| Order | 欄位 | Source | Red/Amber condition |
|------|------|--------|---------------------|
| after 30 | 學籍驗證 | `verification_status` → label | **red** if `!= VERIFIED` |
| dynamic | *(one per rule)* header = `rule_name` | `details["rule_<id>"]` | hard-rule fail → **red**; warning-rule fail → **amber** |
| end | 納入造冊 | `is_included` → 是/否 | **red** if `False` |
| end | 排除原因 | `exclusion_reason or ""` | **red** if `is_included == False` |

Additionally: the **existing 帳號 (col 3)** cell turns **red** when
`bank_account` is missing.

### Per-rule cell values
- `通過` — `passed == True` (no fill)
- `未通過` — `passed == False` and rule is hard (or severity unknown) → **red**
- `警告` — `passed == False` and rule is warning → **amber**
- `—` — that rule has no detail entry for this item (rule not applicable)

The per-rule **column set is dynamic per roster** (the union of rule ids seen
across the roster's items, ordered by rule id; on duplicate `rule_name`,
disambiguate by appending the id).

## Item scope (which students appear)

Show **included** students **plus students auto-excluded for ineligibility**
(failed 學籍 / rules / missing bank at generation). **Hide students manually
removed after locking** (`exclusion_reason` starting with `鎖定後移除` or
`比對分發移除`) — those were intentionally removed and must not reappear on a
re-download.

Implemented via a pure helper `_is_manual_removal(item)`. The default export
item set becomes: `included ∪ (excluded ∧ ¬manual_removal)`.
`include_excluded=True` still returns absolutely everything (incl. manual
removals) for callers that explicitly want it.

## Mechanics / data flow

The final column list is no longer fully static (per-rule columns depend on the
roster), so thread it through explicitly:

1. `_collect_rule_columns(items) -> List[RuleColumn]` — pure; scans
   `details`, returns ordered de-duplicated rule columns
   `(key="rule_<id>", header, ...)`.
2. Build `columns = STATIC_BASE + ["學籍驗證"] + [rc.header …] + ["納入造冊", "排除原因"]`.
3. `_prepare_excel_data(roster, items, rule_columns)` — returns
   `(rows, fill_map)` where `rows` is the list of column→value dicts and
   `fill_map` is a parallel list of `{column_name: "red" | "amber"}` per row.
4. `_create_excel_file(rows, columns, fill_map, …)` — writes using the passed
   `columns` and applies per-cell fills.
5. Column widths: per-rule and verification columns get a sensible default
   width; borders already span `len(columns)`.

Red fill: `PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")`
(Excel's standard "bad" red). Amber: `PatternFill("FFEB9C", …)` ("neutral" amber).

## Error handling

- Items with `rule_validation_result is None` or empty `details` → all per-rule
  cells `—`, no rule-based red (still red on 學籍/帳號/納入 as applicable).
- A `details` value that is not a `rule_<id>` entry (e.g. `no_rules_found`,
  `error`) is ignored by `_collect_rule_columns`.
- Per-rule error results (no `is_hard_rule`) default to **red** (treated as a
  hard fail), since an un-evaluated rule must not silently look compliant.

## Testing (TDD)

Extend `backend/app/tests/test_excel_export_service_rows.py` (or a sibling
pure-helper test) using the existing `SimpleNamespace` stub pattern:

- `_is_manual_removal` true/false matrix.
- `_collect_rule_columns`: ordering, de-dup, ignores non-rule detail keys,
  handles missing/empty details.
- `_prepare_excel_data`: per-rule cell values (通過/未通過/警告/—), verification
  column values, and the parallel `fill_map` (red vs amber vs none, incl. the
  missing-bank red on 帳號).
- A real temp-file `export_roster_to_excel` (or `_create_excel_file`) round-trip
  asserting the appended headers exist and the expected cells carry the red/amber
  `PatternFill` — and that a manually-removed item is absent while an
  ineligibility-excluded item is present (red).

## Risk (accepted)

This enriches the official STD_UP_MIXLISTA payment sheet and now includes
ineligible students (red). It functions as a **review document**; red rows are
removed before any payment-system upload.
