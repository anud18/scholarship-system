# Phase 4 — P2 Findings Grouping + Launch Gate Runbook Outline

**Prepared:** 2026-05-06  
**Source:** `docs/superpowers/audits/2026-05-06-monitoring-stack-audit.md` (§ P2 + noted appendix + Phase 4 sketch at spec §8)  
**Branch:** `feat/monitoring-phase2`  
**Entry condition:** All 45 P0+P1 findings cleared (Phase 2 + Phase 3 merged and staging green).

---

## 1. All 9 P2 Findings

| ID | Where | Short title | Affects |
|---|---|---|---|
| F-GRAF-06 | `scholarship-system-overview.json` panel 7, line 607 | Backend Error Rate `or 0` masks No-data | staging + prod AP-VM |
| F-GRAF-07 | `scholarship-system-overview.json` panel 11, line 879 | Redis Hit Ratio `or 0` masks No-data | staging + prod AP-VM |
| F-GRAF-11 | `dashboards.yml` all 5 providers (`allowUiUpdates: true`) | All 8 dashboards report `provisioned: false` — IaC sync broken | staging + prod AP-VM |
| F-GRAF-12 | `dashboards.yml` Logs Monitoring provider + `application/application-logs.json` | "Logs" folder provider configured but empty; log dashboard lands in "Application" | staging + prod AP-VM |
| F-PROM-13 | `prometheus.yml:35-63` static_configs labels | Self-monitor targets carry no `vm` label; violates cross-VM labeling convention | staging + prod AP-VM |
| F-APP-05 | `backend/app/main.py:354-378`, `nginx/nginx.staging.conf` | `/metrics` endpoint reachable from public internet via host-exposed port 8000 | staging + prod AP-VM |
| F-APP-06 | `backend/app/core/metrics.py:74-134` | 13 metrics declared but never instrumented (dead declarations) | staging + prod |
| F-APP-07 | `dashboard-scholarship-overview.json` "Backend Error Rate (%)" panel | `or 0` duplicates F-GRAF-06 finding on a second dashboard — same panel, different JSON file | staging + prod AP-VM |
| F-DEPL-08 | `.github/workflows/deploy-monitoring-stack.yml:74-75, 250-251` | Hardcoded `sleep 60` / `sleep 30` — should be readiness polling | staging |

### Noted finding reconsidered for Phase 4

| ID | Original classification | Reconsideration |
|---|---|---|
| F-DEPL-14 | `noted` | **Pull into Phase 4.** Documentation-only fix (update `PRODUCTION_SYNC_GUIDE.md` "Automatic Sync" section to "Manual Sync"). Zero risk, one file, one PR. Audit conclusion section already tags it for Phase 4 cosmetic sweep. |
| F-ALLO-10 | `noted` | Audit conclusion section recommends doing it in Phase 4. `honor_labels = true` on backend scrape allows backend to override Alloy-injected labels — latent risk; disable or document. Pull in if Phase 3 capacity allows; otherwise defer. |

---

## 2. Grouping by Theme

### Group A — `or 0` masking removal
**Findings:** F-GRAF-06, F-GRAF-07, F-APP-07  
**Rationale:** Three panels across two dashboard JSON files share the same anti-pattern (`or 0` appended to a PromQL expression). Fixing them together avoids revisiting dashboard JSON twice. F-APP-07 and F-GRAF-06 both describe the same panel in the overview dashboard — confirm at implementation time whether they point at the same JSON file or two different copies.

**Suggested execution order:** First — no dependencies on other groups. Safe to start the moment Phase 3 is merged.  
**Estimated PRs:** 1 (one dashboard JSON commit, both overview JSONs in same PR).  
**Estimated engineering days:** 0.5 d  
**Open questions:**
- F-GRAF-06 points at `dashboards/default/scholarship-system-overview.json`; F-APP-07 points at `api-responses/grafana/dashboard-scholarship-overview.json`. Confirm these are the same canonical file — the latter is an audit capture, not a source file. Only the `default/scholarship-system-overview.json` needs changing.
- After Phase 3 instruments `http_errors_total`, re-verify the division-by-zero risk. The fix sketch (no `or 0`, use `> 0` guard) should be confirmed once real data flows.

---

### Group B — Provisioning hygiene
**Findings:** F-GRAF-11 (`allowUiUpdates`), F-GRAF-12 (Logs folder)  
**Rationale:** Both are Grafana provisioning configuration issues. F-GRAF-11 sets `allowUiUpdates: false` in `dashboards.yml`; F-GRAF-12 either moves `application-logs.json` into `dashboards/logs/` or removes the dead Logs provider. Single PR touching `dashboards.yml` + optional file move.

**Suggested execution order:** Second — after Group A so dashboards are in final form before IaC sync is locked down.  
**Estimated PRs:** 1  
**Estimated engineering days:** 0.5 d  
**Open questions:**
- Decision needed: move log dashboard into `logs/` folder (better UX) vs. remove orphaned Logs provider (simpler). Recommend moving — the "Logs" folder is semantically correct.
- After setting `allowUiUpdates: false`, confirm that the dashboard delete+re-provision cycle in staging doesn't lose any UI-only edits that were never committed to the JSON files. Phase 3 should have finalized dashboard JSON; verify before flipping the flag.

---

### Group C — Cross-VM labeling
**Findings:** F-PROM-13  
**Rationale:** Single-file change — add `vm: 'ap-vm'` to the three self-monitoring `static_configs` in `prometheus.yml`. Isolated; no dependency on other P2 groups.

**Suggested execution order:** Second (parallel with Group B).  
**Estimated PRs:** 1  
**Estimated engineering days:** 0.25 d  
**Open questions:**
- Confirm `vm: 'ap-vm'` is consistent with the label value used by Phase 3 Alloy relabel fixes (Phase 3 may have canonicalized the value; check before committing).

---

### Group D — Workflow hygiene
**Findings:** F-DEPL-08 (sleep timing), F-DEPL-14 (mirror docs note — pulled from `noted`)  
**Rationale:** Both are deploy pipeline fixes with no runtime risk. F-DEPL-08 replaces the two `sleep` calls with readiness-poll loops; F-DEPL-14 corrects one prose paragraph in `PRODUCTION_SYNC_GUIDE.md`. Bundle them to minimize workflow churn.

**Suggested execution order:** Third — after Groups A–C are merged and the pipeline is stable. The readiness-poll loops should be validated by triggering a fresh staging deploy with the new loops; having other changes already merged simplifies attribution of any issues.  
**Estimated PRs:** 1  
**Estimated engineering days:** 0.5 d  
**Open questions:**
- Verify Phase 2 did not already replace the `sleep 60` with polling as part of the strengthened health-check work (the Phase 2 spec §6 mentions adding health-check steps but does not explicitly call out replacing the sleep). If Phase 2 already handled F-DEPL-08, this group shrinks to F-DEPL-14 alone (15 min).
- Readiness-poll timeout values: spec suggests 120 s for Grafana start, 90 s for metrics. Confirm against observed cold-start times on the self-hosted runner.

---

### Group E — Metric inventory cleanup
**Findings:** F-APP-05 (`/metrics` auth), F-APP-06 (dead metrics)  
**Rationale:** Both are backend-side fixes. F-APP-05 is a compose/nginx change (remove host port binding or add nginx deny rule). F-APP-06 requires deciding per metric: instrument it in the service layer or delete the declaration from `core/metrics.py`. Group together to keep backend changes in one PR review.

**Suggested execution order:** Fourth — depends on Phase 3 instrumentation decisions so we know which metrics were wired (reducing the F-APP-06 dead-metric count). Running last among code-change groups.  
**Estimated PRs:** 1–2 (may split compose/nginx change from backend code change for cleaner review)  
**Estimated engineering days:** 1 d (instrumentation decisions + verification)  
**Open questions:**
- F-APP-06: of the 13 dead metrics, Phase 3 is expected to instrument `scholarship_applications_total`, `email_sent_total`, `db_query_duration_seconds`. Remaining ~10 are truly dead. Decision: instrument or delete? Recommend delete unless there is a planned dashboard panel. Confirm the list after Phase 3 merge.
- F-APP-05: `expose:` vs. nginx `deny` — prefer removing the host port binding (`expose:` only) since the nginx approach only blocks HTTP on port 80/443 but not direct port 8000 access if firewall allows it.
- F-ALLO-10 (`honor_labels = true`): if the team decides to pull it into Phase 4 from `noted`, it belongs in this group (Alloy config change, same backend-interface theme).

---

### Group F — Documentation completeness
**Findings:** F-DEPL-14 (already assigned to Group D above), plus any docs gaps surfaced by Phase 2/3  
**Rationale:** The Phase 2/3 implementation may have produced new runbook content (e.g., Grafana unified alerting contact point setup, DB-VM push-mode wiring) that is not yet captured in `monitoring/PRODUCTION_RUNBOOK.md`. A final docs-sweep PR closes this.

**Suggested execution order:** Fifth (last) — after all code changes merge, so the runbook reflects the final state.  
**Estimated PRs:** 1  
**Estimated engineering days:** 0.5 d  
**Open questions:**
- Enumerate what Phase 2/3 PRs added/changed in `monitoring/**` and verify each has a corresponding runbook section.
- The launch-gate runbook (§4 below) is the primary deliverable here; it can live at `monitoring/PRODUCTION_LAUNCH_RUNBOOK.md` (spec §8 explicitly calls for this file).

---

## 3. Sub-Phase Ordering Summary

| Order | Group | Findings | Dependencies | PRs | Days |
|---|---|---|---|---|---|
| 4A-1 | `or 0` masking removal | F-GRAF-06, F-GRAF-07, F-APP-07 | Phase 3 merged | 1 | 0.5 |
| 4A-2 | Provisioning hygiene | F-GRAF-11, F-GRAF-12 | 4A-1 merged | 1 | 0.5 |
| 4A-2 | Cross-VM labeling | F-PROM-13 | Phase 3 merged (for vm label canonical value) | 1 | 0.25 |
| 4A-3 | Workflow hygiene | F-DEPL-08, F-DEPL-14 | 4A-1/2 merged; verify Phase 2 sleep status | 1 | 0.5 |
| 4A-4 | Metric inventory cleanup | F-APP-05, F-APP-06 (+ optional F-ALLO-10) | Phase 3 merged (instrumentation list finalized) | 1–2 | 1.0 |
| 4A-5 | Documentation + launch runbook | Docs gaps from Phase 2/3 | All above merged | 1 | 0.5 |
| **Total** | | **9 P2 + F-DEPL-14 (noted)** | | **6–7 PRs** | **~3.25 d** |

4A-2 (Provisioning hygiene) and 4A-2 (Cross-VM labeling) can run in parallel — same order slot, different files.

---

## 4. Launch Gate Runbook Outline

**Deliverable file:** `monitoring/PRODUCTION_LAUNCH_RUNBOOK.md` (inside `monitoring/` so it survives mirror strip).  
**Operator:** AP-VM maintainer or on-call engineer.  
**When to run:** After all Phase 2/3/4 PRs are merged to `main`, mirrored to prod, and prod deploy workflow has completed.

### Gate 1 — Zero broken datasources

```bash
# From any machine with Grafana credentials:
# Replace GF_URL and GF_TOKEN with actual values.
GF_URL="https://ss.test.nycu.edu.tw/monitoring"  # or prod URL
GF_TOKEN="<service-account-token>"

curl -sf -H "Authorization: Bearer $GF_TOKEN" \
  "$GF_URL/api/datasources" | \
  jq '[.[] | {name, type, uid, url}]'

# For each datasource uid returned:
for uid in $(curl -sf -H "Authorization: Bearer $GF_TOKEN" \
  "$GF_URL/api/datasources" | jq -r '.[].uid'); do
  result=$(curl -sf -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $GF_TOKEN" \
    "$GF_URL/api/datasources/uid/$uid/health")
  echo "$uid => HTTP $result"
done
# Expected: all UIDs => HTTP 200. Any 500 = FAIL.
```

**Pass condition:** Every datasource returns HTTP 200. Zero entries showing `message: "Plugin unavailable"`.

---

### Gate 2 — All 8 dashboards zero No-data for past 1 hour

```bash
# List all dashboard UIDs:
curl -sf -H "Authorization: Bearer $GF_TOKEN" \
  "$GF_URL/api/search?type=dash-db" | \
  jq '[.[] | {uid, title, folderTitle}]'

# For each dashboard: open in browser at ?from=now-1h&to=now&kiosk
# Visual check: no panel shows the "No data" sentinel (grey dash or "No data" text).
# Automated approach (Playwright):
#   npx playwright test monitoring/tests/launch-gate-nodata.spec.ts
# (script to be authored as part of 4A-5 documentation PR)
```

**Pass condition:** All 8 dashboards, all panels show data (or legitimately empty series with an explicit "0 requests" annotation — not "No data"). Screenshot each dashboard and attach to the launch PR.

---

### Gate 3 — Synthetic alert end-to-end test

```bash
# 1. Push a test firing alert via Prometheus API (or use Grafana's "Test alert" button
#    on a known alert rule that fires when a synthetic threshold is breached).

# Option A: Prometheus fake alerting (if Prometheus is accessible):
curl -X POST "https://ss.test.nycu.edu.tw/monitoring/prometheus/api/v1/alerts" \
  -H "Content-Type: application/json" \
  -d '[{
    "labels": {"alertname":"SyntheticLaunchGateTest","severity":"warning","env":"staging"},
    "annotations": {"summary":"Launch gate synthetic test"},
    "startsAt": "'"$(date -u +%Y-%m-%dT%H:%M:%SZ)"'"
  }]'
# Expected: HTTP 200 from Prometheus.

# Option B: Use Grafana unified alerting "Test alert" button on the HighErrorRate rule
# (navigate to Alerting > Alert Rules > HighErrorRate > Edit > Test).

# 2. Wait up to 2 minutes for the webhook contact point to fire.
# 3. Check GitHub Issues on anud18/scholarship-system:
gh issue list --label "monitoring-alert" --label "env:staging" --limit 5
# Expected: at least one open issue created within 2 minutes of the test fire.

# 4. Close the test issue:
gh issue close <issue-number> --comment "Launch gate synthetic test — closing."
```

**Pass condition:** A GitHub issue appears with labels `monitoring-alert`, `env:staging`, `severity:warning` within 2 minutes of alert fire. If using prod environment, labels are `env:prod`.

---

### Gate 4 — Strengthened deploy health checks pass on fresh deploy

```bash
# Trigger a fresh deploy on the self-hosted runner:
gh workflow run deploy-monitoring-stack.yml --ref main \
  -f environment=staging

# Monitor the run:
gh run watch $(gh run list --workflow=deploy-monitoring-stack.yml \
  --limit 1 --json databaseId -q '.[0].databaseId')

# Expected: all steps green, including:
#   - "Verify datasource health" step: all 200s logged
#   - "Verify staging targets" step: count > 0 logged
#   - "Verify dashboard provisioning" step: no provisioning errors
#   - "Verify alert rules loaded" step: rule count > 0 logged
```

**Pass condition:** `deploy-monitoring-stack.yml` workflow run completes with exit code 0 and all strengthened health-check steps report green. No "❌" lines in step output.

---

### Launch-gate certification checklist

An operator runs through all four gates and records:

```
[ ] Gate 1 — Datasource health: all UIDs 200  (date/time: ___)
[ ] Gate 2 — No-data panels: 0/8 dashboards affected for past 1h  (screenshot: ___)
[ ] Gate 3 — Synthetic alert: GitHub issue #___ created at ___
[ ] Gate 4 — Fresh deploy: run #___ passed at ___

Operator: _______________   Date: _______________
Environment certified: [ ] staging  [ ] production
```

All four boxes checked = Phase 4 exit condition met. Production is cleared to take real traffic.

---

## 5. Relationship to audit "noted" items

| Noted ID | Title | Phase 4 decision |
|---|---|---|
| F-DEPL-14 | Mirror docs describe "Automatic Sync" but workflow is manual-only | **Pull in** to Group D. Zero risk, one paragraph edit. |
| F-ALLO-10 | `honor_labels = true` on backend scrape allows backend to override Alloy labels | **Conditional pull-in** to Group E if Phase 3 reveals it caused label bleed. Otherwise defer to Phase 5. |
| F-PROM-14 | No remote_write long-term storage (15-day TSDB only) | **Defer** — storage architecture decision, out of scope. |
| F-APP-08 | Log format conditionally JSON — Loki parsing depends on `LOG_FORMAT=json` | **Defer** — env-var documentation; no code risk if Phase 3 confirms staging has the env var set. |
