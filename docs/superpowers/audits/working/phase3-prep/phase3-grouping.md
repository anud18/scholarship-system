# Phase 3 — P1 Findings Grouping

**Prepared:** 2026-05-06  
**Source audit:** `docs/superpowers/audits/2026-05-06-monitoring-stack-audit.md`  
**Phase 2 spec non-goals:** `docs/superpowers/specs/2026-05-06-monitoring-stack-fix-phase2-design.md §3`  
**Total P1 findings:** 34  
**Phase 2 already closed:** F-DEPL-09, F-DEPL-10, F-DEPL-12 (pulled into Phase 2 as tightly-coupled)  
**Phase 3 owns:** 31 remaining P1 findings (F-PROM-11 debunked; F-PROM-12 relegated to Phase 4 cleanup per audit)

---

## Adjustments to Initial Grouping

Before the table, three corrections from the initial cut:

1. **F-ALLO-02 was omitted** from the initial grouping — it belongs in the AP-VM Alloy drift group (same slash-strip fix as F-ALLO-01, but for prod-db-vm).
2. **F-PROM-11 is debunked** — audit §F-PROM-11 concludes "not a bug"; admin API intentionally disabled. No fix needed. Remove from Phase 3.
3. **F-PROM-12 is Phase 4 cleanup** — audit assigns remediation to Phase 4 per §F-PROM-12. Remove from Phase 3.
4. **F-ALLO-06 vs F-PROM-05 vs F-APP-03** — all three describe the same root cause (DB-VM metrics not reaching Prometheus). Grouped together as one sub-phase. Phase 2 addressed the label-promise comment via F-ALLO-09 (added scrape+relabel+remote_write to db-vm alloy files), so F-ALLO-06 may be largely resolved; verify before Phase 3 opens.

---

## Grouping Table

| # | Group Name | Finding IDs | Count | Blocks | Est Days |
|---|---|---|---|---|---|
| G1 | **DB-VM metric pipeline** | F-PROM-05, F-APP-03, F-ALLO-06 (verify) | 3 | G4, G5, G6 | 1.0 |
| G2 | **Prod-AP Alloy drift** | F-ALLO-01, F-ALLO-02, F-ALLO-03, F-ALLO-04, F-ALLO-05 | 5 | — | 0.5 |
| G3 | **Alloy fragility** | F-ALLO-07, F-ALLO-08 | 2 | — | 0.5 |
| G4 | **Backend metric instrumentation** | F-APP-01, F-APP-02, F-APP-04, F-GRAF-03, F-GRAF-04, F-GRAF-10 | 6 | G5, G6 | 1.5 |
| G5 | **Deferred postgres alerts** | 3 rules deferred from Phase 2 (PostgreSQLDown, TooManyConnections, HighConnections) | 3 rules | — | 0.5 |
| G6 | **Dropped application alerts redesign** | F-PROM-07 (MinIODown), F-PROM-08 (SlowHTTPResponseTime via backend), HighHTTPErrorRate | 3 alerts | — | 0.5 |
| G7 | **Dashboard query corrections** | F-GRAF-02, F-GRAF-05, F-GRAF-08, F-GRAF-09 | 4 | — | 0.5 |
| G8 | **Prometheus alert/rule hygiene** | F-PROM-06, F-PROM-07 (overlap G6), F-PROM-08 (overlap G6), F-PROM-09 | 4 | — | 0.5 |
| G9 | **Loki retention wiring** | F-PROM-10 | 1 | — | 0.5 |
| G10 | **Deploy path fixes** | F-DEPL-05, F-DEPL-06 | 2 | — | 0.5 |
| G11 | **Prod-side blind spots** | F-DEPL-11, F-DEPL-13 | 2 | — | 0.5 |
| — | **Debunked / Phase 4** | F-PROM-11 (debunked), F-PROM-12 (Phase 4) | — | — | — |

**Total active findings in Phase 3:** 29 findings across 11 groups (~6.5 engineering days)

> Note: G5 and G6 track alert rule work rather than audit finding IDs directly, because the 3 deferred postgres alerts and 3 dropped application alerts are alert-disposition items from the Phase 2 spec (§6.2.1), not separate audit IDs.

---

## Recommended Sub-Phase Ordering

```
Sub-phase 3.A  ─────────────────────────────────────────────────────────
  G1  DB-VM metric pipeline    (prerequisite for G4 postgres alerts)
  G2  Prod-AP Alloy drift      (independent; ship in same PR as G1 or separate)
  G3  Alloy fragility          (independent; can ship with G2)

Sub-phase 3.B  ─────────────────────────────────────────────────────────
  G4  Backend metric instrumentation   (requires G1 to verify end-to-end)
  G8  Prometheus alert/rule hygiene    (F-PROM-06 re-enable; F-PROM-09 delete)
  G9  Loki retention wiring            (independent; low-risk one-liner)
  G10 Deploy path fixes                (independent; low-risk)

Sub-phase 3.C  ─────────────────────────────────────────────────────────
  G5  Deferred postgres alerts         (requires G1 so pg_up metric exists)
  G6  Dropped application alerts       (requires G4 so backend metrics exist)
  G7  Dashboard query corrections      (requires G1+G4 data to verify panels)

Sub-phase 3.D  ─────────────────────────────────────────────────────────
  G11 Prod-side blind spots            (documentation + example file; no metric deps)
```

**Rationale:**
- G1 (DB-VM pipeline) is the hard prerequisite: without `vm="db-vm"` data in Prometheus, you cannot verify postgres alerts, MinIO alert redesign, or PostgreSQL dashboard panels.
- G4 (backend instrumentation) must land before G5/G6 alert redesigns, because `HighHTTPErrorRate` and `SlowHTTPResponseTime` will be rewritten to use `http_requests_total{status=~"5.."}` and `http_request_duration_seconds_bucket` from the backend.
- G7 (dashboard fixes) should be validated after G1+G4 are live so panels can be confirmed non-empty.
- G11 is documentation-only and can slip to the end without blocking other groups.

---

## Estimated PR Count

| Sub-phase | Groups | Proposed PRs | Rationale |
|---|---|---|---|
| 3.A | G1, G2, G3 | 2 PRs (G1 alone; G2+G3 together) | G1 is risky (cross-VM network); keep isolated |
| 3.B | G4, G8, G9, G10 | 2 PRs (G4 backend code alone; G8+G9+G10 config) | backend code change vs pure config change |
| 3.C | G5, G6, G7 | 1–2 PRs (alerts G5+G6; dashboards G7) | alert YAML vs dashboard JSON are separate concerns |
| 3.D | G11 | 1 PR | docs-only |

**Total: 6–7 PRs** across four sub-phases.

---

## Open Questions

1. **Has Phase 2 fully resolved F-ALLO-06?** Phase 2 added scrape+relabel+remote_write to `staging-db-vm.alloy` and `prod-db-vm.alloy` (per spec §6.4.6 / F-ALLO-09). If that deploy succeeded and the runner is now online, `vm="db-vm"` metrics may already be flowing. Phase 3 must verify `up{vm="db-vm"}` before opening G1 work — if already resolved, G1 shrinks to just validating postgres-exporter labels.

2. **What is the prod network name after F-DEPL-04 fix?** Phase 2 parameterized `${APP_NETWORK_NAME}` in `docker-compose.monitoring.yml`. G3 (F-ALLO-07) standardizes `prod-ap-vm.alloy` remote_write URL. The fix assumes Alloy and Prometheus are co-located — is that still true for prod after Phase 2's network refactor?

3. **Nginx exporter replacement or log-parsing pivot?** F-GRAF-08 and F-PROM-08 both stem from the stub_status nginx exporter lacking `status` and duration labels. Phase 3 must decide: (a) enable VTS module in nginx, (b) switch to OpenTelemetry, or (c) replace the alert/dashboard queries with backend-side equivalents. This choice affects G6 and G7 scope significantly.

4. **MinIO scrape architecture** (F-PROM-07): MinIO lives on AP-VM, not DB-VM. The dropped `MinIODown` alert referenced `job="staging-db-minio"` — wrong VM, wrong job name. G6 must decide where to add the MinIO scrape block in `staging-ap-vm.alloy` and what job name to assign; this also affects `minio-monitoring.json` dashboard panel filters.

5. **`db_query_duration_seconds` instrumentation strategy** (F-APP-04): The SQLAlchemy event listener approach (per audit fix sketch) adds overhead to every query. Is there an existing SQLAlchemy middleware or OpenTelemetry integration in the backend that already captures this? Check `backend/app/db/session.py` and any existing middleware before writing a new event listener.

6. **`scholarship_applications_total` and `email_sent_total` placement** (F-GRAF-10): Which service layer increments these? Application state changes span multiple services. Confirm whether to instrument in the service layer, the router, or via a SQLAlchemy ORM event, and whether the email counter belongs in `email_service.py` or the notification task.

7. **Recording rules: re-enable or delete?** (F-PROM-06): The audit notes that no dashboard JSON references any recording-rule metric name — they are dead code even if re-enabled. Phase 3 must choose between (a) re-enabling them for future alerting use, or (b) deleting `aggregations.yml` entirely for CLAUDE.md §2 (no backward compat / clean delete). This choice affects G8 scope.

8. **F-DEPL-13 prod blind spot resolution**: The prod-side deploy workflow SCP step for `prod-db-vm.alloy` is unknown. Can the user provide prod repo read access before Phase 3 closes? If not, G11 produces a written SCP template only — actual verification cannot happen in this repo.

9. **F-DEPL-05 paths filter** — the audit assigns this to Phase 4 per the spec, but Phase 2 spec §3 Non-Goals lists it as "Phase 3". Clarify which phase owns it. Currently placed in G10 as Phase 3 to match the Phase 2 spec non-goals listing.

10. **Sub-phase 3.A ordering dependency on Phase 2 runner being live**: All of Phase 3 depends on the Phase 2 runner being registered and the workflow having at least one successful run. If the runner is still offline when Phase 3 begins, sub-phase 3.A must start with a runner check, not metric verification.

---

## Key Risks

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| **R1: DB-VM network path blocked** — even after F-ALLO-06 fix, firewall between DB-VM and AP-VM Prometheus port 9090 may block remote_write | G1 entirely blocked; postgres alerts impossible | Medium | Verify `curl http://<AP-VM>:9090/api/v1/write` from DB-VM before opening Phase 3 |
| **R2: Phase 2 runner still offline** — if the self-hosted runner was never re-registered, Phase 3 config changes cannot deploy | All of Phase 3 blocked | Medium | Phase 3 gate: confirm `gh workflow view deploy-monitoring-stack.yml` shows ≥1 successful run before brainstorming Phase 3 PRs |
| **R3: Nginx exporter architecture decision drags** — the VTS vs backend-side pivot for G6/G7 requires user decision; wrong choice = rework | G6 and G7 delayed; alert coverage gap persists | Medium | Pre-decide before Phase 3 brainstorm: ask user to confirm nginx exporter type (`docker exec monitoring_nginx nginx -V 2>&1 | grep with-http_vhost_traffic_status`) |
| **R4: Backend SQLAlchemy instrumentation regression** — adding event listeners to a production-targeted backend is non-trivial; risk of performance regression or missed transactions | G4 quality risk | Low-Medium | Add benchmark test; observe histogram in staging for 1 hour before merging |
| **R5: Prod-side blind spot (F-DEPL-13) unresolvable** — without prod repo access, G11 is documentation-only and the actual Alloy config deployment on prod DB-VM remains unverified | Prod DB-VM logs continue to be absent from Loki in prod | High | Escalate prod repo access request before Phase 3.D; document as explicit prod-launch blocker if not resolved |
| **R6: F-ALLO-06 partially resolved by Phase 2** — if Phase 2's db-vm alloy changes deployed but Prometheus still shows no `vm="db-vm"` targets, the root cause is the firewall/network (R1), not the config | Misdiagnosis wastes time in G1 | Medium | Run `up{vm="db-vm"}` probe on day 1 of Phase 3 before any code changes |
