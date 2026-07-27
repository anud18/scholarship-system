# 已領月份數 = 匯入 + 系統 (additive, not override)

已領月份數 has two sources: a lifetime baseline imported from 國科會's
「獲獎生已領月份統計表」, and a value computed live from this system's own
payment rosters. We **add** them rather than letting the imported value override
the computed one, as the retired `college_ranking_items.received_months_source`
mechanism did.

This is only correct under a stated assumption: **the imported file records
months paid before this system took over roster generation, so the two halves
never cover the same month.** If 國科會 ever sends a file whose
`領獎起始月份`→`目前領獎月份` range overlaps months this system also paid, the
total will double-count and can falsely trip the 36-month PhD cap. The covered
range is stored on every ledger row (`award_start_month` / `award_current_month`)
specifically so that overlap can be detected and excluded later without a
migration.

## Considered options

- **Imported overrides system** — the previous behaviour. Rejected: the imported
  number freezes on import and stops reflecting rosters generated afterwards.
- **max(imported, system)** — never double-counts, never under-counts. Rejected:
  neither number is authoritative, so the result cannot be explained to an admin.
- **Baseline + only rosters after the file's as-of month** — the accurate
  general solution. Deferred: it needs `period_label`→month comparison, and the
  no-overlap assumption above makes it unnecessary today.

## Consequences

- The imported half is keyed by `(學號, scholarship_type)` and is **lifetime**;
  the system half stays scoped to a single `scholarship_configuration` (one
  academic year). The 36-month cap therefore still under-counts a multi-year
  student who has no imported record — a pre-existing gap this ADR does not close.
- 學生領獎紀錄查詢 has no academic-year context, so it sums the system half over
  the student's whole payment history. The same student can legitimately show a
  larger 系統 number there than on the 手動分發 panel.
