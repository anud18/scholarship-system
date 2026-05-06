# Monitoring Stack Fix — Design Spec

**Date:** 2026-05-06
**Owner:** jotpalch (with Claude Code)
**Status:** Draft awaiting user review
**Related:**
- `https://ss.test.nycu.edu.tw/monitoring` (staging Grafana)
- `monitoring/` (in-repo config)
- `.github/workflows/deploy-monitoring-stack.yml` (staging deploy)
- `.github/workflows/mirror-to-production.yml` (one-way prod sync)
- `monitoring/GITHUB_DEPLOYMENT.md`, `monitoring/PRODUCTION_RUNBOOK.md`

---

## 1. Context

The Grafana instance at `https://ss.test.nycu.edu.tw/monitoring` is up but partially broken:

- The "Scholarship System Overview" dashboard shows **No data** on three key panels: Backend Error Rate (%), PostgreSQL Active Connections, Database Query p95 (ms).
- The `alertmanager` Grafana datasource returns `http=500 message="Plugin unavailable"` because commit `57fca5f` removed the AlertManager service from the compose stack but left the datasource and `monitoring/config/alertmanager/alertmanager.yml` in the repo.
- `monitoring/config/prometheus/alerts/basic-alerts.yml` still defines Prometheus-format alert rules. With AlertManager gone, these fire into a void — alerts trigger but no human is notified.
- Recent git log shows the stack has been through ~10 `fix(monitoring): ...` commits in a short period; the bug surface is broader than what is visible in one Grafana session.

Production deploys via the `mirror-to-production.yml` workflow, which is a manually-triggered one-way push that strips `.github/workflows/`, `*.md`, `__tests__/`, and most `docker-compose.*.yml` files before opening a PR in a private prod repo. The dev repo therefore controls `monitoring/**` content for both environments, but does not control prod's deploy workflow (which lives only in the private prod repo as `deploy-monitoring-stack-prod.yml`).

Production has not yet officially launched, so staging is available as a destructive test bed.

---

## 2. Goals

1. Make `https://ss.test.nycu.edu.tw/monitoring` (and its mirrored prod counterpart) trustworthy by the day production launches.
2. Eliminate every "monitoring is silently lying" failure mode: alerts firing into a void, dashboards staying green when they should not, datasources pointing at removed services, deploy health checks reporting OK while the stack is broken.
3. Use staging as the experimental ground; promote each verified fix to production by triggering `mirror-to-production` and merging the resulting prod-repo PR.
4. Strengthen the deploy workflow's health checks so a regression of any of these bugs would have caught itself in CI.

## 3. Non-Goals

- Not replacing the stack architecture. Grafana 12.2.1 Enterprise + Grafana Alloy + Prometheus + Loki stays.
- Not adopting Slack / PagerDuty as the alert receiver. GitHub Issues is the chosen receiver for now.
- Not authoring SLOs, log retention policy, secret rotation policy, or disk-fill alerting policy. These are noted in the audit's "noted but not fixing" section as future Phase 5+.
- Not modifying production's private deploy workflow directly. We deliver any prod-side workflow changes as written instructions for the prod-repo maintainer.
- Not writing application-layer business logic. Backend changes are limited to `/metrics` instrumentation gaps that block dashboards.

---

## 4. Phase Overview

| Phase | Goal | Output | Est. effort |
|---|---|---|---|
| **1. Audit** | Enumerate every monitoring-stack and app-metric-interface bug; classify P0/P1/P2 | `docs/superpowers/audits/2026-05-06-monitoring-stack-audit.md` | ~2 engineering days |
| **2. P0 fixes** | AlertManager teardown, alert rule migration to Grafana unified alerting, GitHub Issue receiver wiring, dishonest-deploy health-check fix | Multiple config PRs + one GitHub Actions workflow | ~3 engineering days |
| **3. P1 fixes** | "No data" panel root causes (missing scrape jobs, missing `environment`/`vm` labels, query/label drift), backend metric gaps if any | config PRs + minimal backend metric instrumentation | ~2–4 engineering days, depends on Phase 1 findings |
| **4. P2 fixes + launch gate** | Cosmetic dashboard cleanup, alert tuning, prod-launch smoke-test runbook | config PRs + runbook | ~2 engineering days |

Each phase produces its own spec (using the brainstorming → writing-plans flow) and one or more PRs. **Only Phase 1 is fully detailed in this document**; Phase 2/3/4 specs will be written after Phase 1's audit findings land, because their content depends on what the audit surfaces.

---

## 5. Phase 1 — Audit Method (Detailed)

### 5.1 Scope

**Monitoring stack itself:**

- `monitoring/config/grafana/provisioning/datasources/datasources.yml` — datasource definitions (esp. the `alertmanager-uid` row).
- `monitoring/config/grafana/provisioning/dashboards/**/*.json` — all 8 dashboards. Every panel's PromQL / LogQL is extracted and verified.
- `monitoring/config/grafana/provisioning/dashboards/dashboards.yml` — provisioning loader.
- `monitoring/config/grafana/grafana.ini.example` — diff against any deployed `grafana.ini` known facts (per `9175ac0` the live file is git-ignored).
- `monitoring/config/prometheus/prometheus.yml` — scrape jobs, `external_labels`, `alerting:` block.
- `monitoring/config/prometheus/alerts/basic-alerts.yml` — full inventory of alert rules to be migrated to Grafana.
- `monitoring/config/prometheus/recording-rules/aggregations.yml` — recording rules.
- `monitoring/config/alloy/{prod,staging}-{ap,db}-vm.alloy` — four files, three-way diff for accidental drift.
- `monitoring/config/alertmanager/alertmanager.yml` — confirmed removable.
- `monitoring/config/loki/{loki-config,limits}.yml`.
- `monitoring/docker-compose.monitoring.yml`, `docker-compose.staging-db-monitoring.yml`, `docker-compose.prod-db-monitoring.yml` — service inventory.

**Application metric / log interface (the `(B)` audit-scope addition):**

- `backend/app/main.py:354` — confirm `/metrics` endpoint is reachable anonymously (no auth middleware blocks it).
- `backend/app/core/metrics.py` — list every `Counter` / `Gauge` / `Histogram` metric name and label set. Cross-reference against every PromQL expression in the dashboards.
- `backend/app/middleware/metrics_middleware.py` — verify EXCLUDED_PATHS does not strip metrics the dashboards depend on, and that label cardinality (status code, method, path) matches dashboard groupings.
- Log structure — confirm backend writes JSON logs that Loki / Alloy can parse for `level` and `request_id`.
- DB-VM exporter labels — verify Alloy `discovery.relabel` blocks add `environment` and `vm` labels to all exporter targets, including `postgres-exporter` on DB-VM.

**Deploy and release pipeline:**

- `.github/workflows/deploy-monitoring-stack.yml` — staging deploy.
- `.github/workflows/mirror-to-production.yml` — dev → prod mirror.
- `.github/PRODUCTION_SYNC_GUIDE.md` and `monitoring/GITHUB_DEPLOYMENT.md` — process documentation.
- `.github/production-workflows-examples/` — examples (note: stripped during mirror).
- **Prod-side workflow blind spot:** the actual `deploy-monitoring-stack-prod.yml` lives in the private prod repo. The owner does not have access at this time. Audit will mark this as a known gap and revisit when access is obtained.

### 5.2 Method

Each finding must clear three gates before being added to the audit report:

1. **Active probe** — query a live system. Examples:
   - Grafana API: `GET /monitoring/api/datasources/uid/{uid}/health`, `GET /monitoring/api/search?type=dash-db`, `POST /monitoring/api/ds/query` for PromQL.
   - Prometheus: `GET /api/v1/targets`, `GET /api/v1/query?query=...`.
   - Loki: `GET /loki/api/v1/query` with `X-Scope-OrgID` per environment.
   - GitHub: read deploy workflow run logs for the most recent successful run, compare to actual state.
2. **Static read** — read the relevant config file in this repo at the current `main` commit, capture exact lines.
3. **Cross-reference** — compare (1) to (2). Drift is the finding.

The auditor uses the existing Grafana session at `/tmp/pw-test/auth-grafana-admin.json` for browser-driven probes (the `nycu-sso-login` skill's pattern, extended for Grafana credentials). Browser-side audit uses Playwright:

- For each of the 8 dashboards: open in `?kiosk` mode, full-page screenshot, panel-by-panel inspection. Captures cases where the PromQL returns data but the panel JSON is misconfigured (visual gap that pure API audit misses).
- For each panel: detect `or 0` style "fake-zero" patterns that mask No-data as 0 — flagged as P2.
- For datasource list and alert rule list: screenshot to provide reproduction artifact.
- For deploy honesty audit: screenshot the GitHub Actions run page after a successful deploy alongside the actual Grafana datasource health to demonstrate when "deploy ✅" lies.

### 5.3 Severity Rubric

| Severity | Definition | Example |
|---|---|---|
| **P0** | Monitoring is lying about its own state. Alert fires to nowhere; datasource points at removed service; deploy reports green while stack is broken. | AlertManager dangling datasource; alert rules with no receiver; health check that tolerates "0 targets" as "all UP". |
| **P1** | Monitoring is configured but not delivering data. No-data panels; missing scrape targets; label drift between collector and query. | The three No-data panels on the overview dashboard. |
| **P2** | Monitoring works but has cosmetic, hygiene, or quality-of-life issues. | `or 0` patterns hiding No-data; dashboard folder naming inconsistencies; hardcoded `sleep` in deploy workflow. |
| **noted** | Out of scope this round. Recorded so it isn't lost. | SLO definition; log retention policy; secret rotation; disk-fill alerts. |

Phase 2 fixes P0; Phase 3 fixes P1; Phase 4 fixes P2; `noted` items roll into a future Phase 5 if they ever happen.

### 5.4 Finding Template

Every finding in the audit report uses this exact block:

````markdown
### F-NNN  [Severity]  Short title

**Where**: `path/to/file.yml:start-end` (and any related deploy step / API endpoint)

**Evidence**:
- Active probe: ... (curl/jq/Playwright command and the actual response)
- Static read: ... (file path and line numbers)
- Cross-reference: ... (the contradiction)

**Expected**: What the system should be doing.

**Root cause hypothesis**: One sentence on why this is broken.

**Remediation owner**: Phase 2 / 3 / 4.

**Suggested fix sketch**: A few lines. Not a final design.
````

### 5.5 Audit Report Structure

The Phase 1 deliverable is a single Markdown file at `docs/superpowers/audits/2026-05-06-monitoring-stack-audit.md` with this structure:

1. Executive summary (≤ 1 page): counts by severity, top 3 risks, ready-to-launch verdict.
2. Findings, grouped by severity then by subsystem (`grafana/`, `prometheus/`, `alloy/`, `backend/`, `deploy/`).
3. "Noted but not fixing" appendix.
4. Cross-VM and cross-environment matrix: a table showing which AP-VM / DB-VM / staging / prod stages each finding affects.
5. Reproduction-artifact appendix: Playwright screenshots, API responses, file excerpts.

---

## 6. Phase 2 — P0 Fixes (Sketch)

Detailed spec to be written after Phase 1 lands. Confirmed direction:

- Remove the `alertmanager` datasource from `monitoring/config/grafana/provisioning/datasources/datasources.yml`.
- Delete `monitoring/config/alertmanager/` entirely.
- Migrate all rules in `monitoring/config/prometheus/alerts/basic-alerts.yml` to Grafana unified alerting via `monitoring/config/grafana/provisioning/alerting/*.yml`. Remove the `alerting:` block from `prometheus.yml`.
- Add a Grafana contact point (type: webhook) targeting a new GitHub Actions workflow `.github/workflows/monitoring-alert-issue.yml` triggered by `repository_dispatch`. The workflow:
  - de-duplicates by alert name (one open issue per alert; subsequent fires reopen + comment with the new fire timestamp).
  - tags issues with labels `monitoring-alert`, `env:staging` or `env:prod`, `severity:warning` or `severity:critical`.
  - Uses a fine-grained PAT scoped to `issues:write` on this single dev repo (stored in GitHub Actions secrets).
- Strengthen `.github/workflows/deploy-monitoring-stack.yml`:
  - Add a step that asserts every Grafana datasource returns 2xx from its `/health` endpoint.
  - Add a step that asserts the count of UP targets matches the count of expected targets (not just `select(.health!="up") | length == 0`, which silently passes when there are zero targets at all).
  - Add a step that asserts dashboard provisioning logs contain no errors.
  - Add a step that asserts no alert rules failed to load.
- Remove dead `ALERT_EMAIL_*` and `ALERT_SLACK_WEBHOOK` env exports from the workflow once they are confirmed unused.

Both staging Grafana and prod Grafana point their webhook contact point at the same dev repo. Issues are filtered by `env:` label.

## 7. Phase 3 — P1 Fixes (Sketch)

Detailed spec to be written after Phase 1 lands. Confirmed direction:

- For each No-data panel:
  - If the metric is missing from Prometheus, fix the scrape pipeline (Alloy or Prometheus scrape_configs).
  - If the metric exists but lacks `environment` / `vm` labels, fix Alloy `discovery.relabel`.
  - If the dashboard query is wrong, fix the panel JSON.
- Reconcile any backend metric instrumentation gaps surfaced by the audit's app-metric cross-reference.
- Verify cross-VM scrape (AP-VM Prometheus reaching DB-VM `postgres-exporter`) actually works; if firewall or compose network limits it, fix the network or move the scrape to Alloy on DB-VM with `prometheus.remote_write` to AP-VM Prometheus.

## 8. Phase 4 — P2 Fixes and Launch Gate (Sketch)

- Cosmetic dashboard cleanup (axes, units, naming).
- Replace `or 0` PromQL patterns where they obscure No-data.
- Replace hardcoded `sleep 60` / `sleep 30` in the deploy workflow with readiness-poll loops.
- Improve `paths:` filter in `deploy-monitoring-stack.yml` to also trigger on `docker-compose.staging-db-monitoring.yml` changes.
- Author a launch-gate runbook at `monitoring/PRODUCTION_LAUNCH_RUNBOOK.md` listing exact commands and expected outputs for each pre-launch verification.

**Launch gate criteria** (Phase 4 exit, before prod is allowed to take real traffic):

- All 8 dashboards have zero No-data panels for the past 1 hour.
- Zero broken datasources (every datasource returns 2xx from `/health`).
- At least one synthetic alert successfully creates a GitHub issue end-to-end.
- Deploy workflow's strengthened health checks pass on a fresh deploy.

---

## 9. Cross-Phase Engineering Principles

1. **IaC-first.** Every fix is committed to `monitoring/**` or `.github/workflows/**`. UI-only changes that don't survive container restart are forbidden.
2. **Staging first, prod follows.** Each PR description carries staging evidence (Playwright screenshot, API response, Loki query result) before merge. Prod promotion happens only after staging green.
3. **No fallback data** (CLAUDE.md §1). Dashboards must not append `or 0` to disguise No-data as zero. Existing instances are P2 audit findings.
4. **No backward compat** (CLAUDE.md §2). When removing AlertManager-related code, delete cleanly. No `# deprecated` placeholders or commented-out blocks.
5. **Cross-VM topology is explicit.** Every scrape target carries a `vm=ap` or `vm=db` label, and every metric stream carries an `environment` label. Implicit topology assumptions are forbidden because they break silently when networks change.
6. **Verification harness is part of the deliverable.** Every Phase 2/3/4 PR includes a one-shot command (curl + jq, or a small Playwright script) that proves the fix works. The command runs against staging.
7. **Reproducible bugs become GitHub issues** (per user memory). If the audit surfaces a bug that has a clean reproduction, file a separate issue rather than burying it in the report.
8. **Documentation lives under `monitoring/**.md`.** Repo-root `*.md` files are stripped by `mirror-to-production.yml`, so prod-side maintainers cannot see them. Anything prod-relevant goes inside `monitoring/`.

---

## 10. Production Sync & Deploy Reality

1. Config changes under `monitoring/**` propagate to prod via `mirror-to-production.yml`.
2. Mirror is **manually triggered** (`workflow_dispatch`), not automatic on push.
3. Mirror strips `.github/workflows/`, `.github/production-workflows-examples/`, all repo-root `docker-compose.staging*.yml`, all `__tests__/` and test files, and **all `*.md` files**, then restores prod's own `.github/workflows/` from `prod-repo/main`.
4. Mirror creates a temp branch in the prod repo, opens a PR, and waits for human review. The prod repo's workflow runs deploy after the PR is squash-merged.
5. **Prod-side `deploy-monitoring-stack-prod.yml` is not visible from this repo.** No example exists in `.github/production-workflows-examples/`. Audit treats this as a blind spot.

**Promotion workflow for every Phase 2/3/4 PR:**

1. Merge the PR to `main` in this dev repo (after staging green).
2. (User or maintainer) trigger `mirror-to-production` workflow with appropriate `version_bump`.
3. Review and merge the auto-generated PR in the prod repo.
4. Confirm prod's deploy workflow ran successfully.
5. Verify the fix is live in prod Grafana using the same verification harness from step 1.

---

## 11. Pre-Discovered Findings (Audit Priors)

These findings were discovered during brainstorming for this spec. They are listed here so the user can verify the framing early. Phase 1 will re-validate each one with a formal Active Probe + Static Read + Cross-Reference, and only then will they appear in the audit report.

| # | Sev | Where | What |
|---|---|---|---|
| **prior-A** | P0 | `deploy-monitoring-stack.yml:77-110` | Health check pings Grafana, Prometheus, Loki only. Does NOT verify datasource health, dashboard provisioning errors, or alert rule load errors. Today's `alertmanager-uid` 500 would silently pass. |
| **prior-B** | P0 | `deploy-monitoring-stack.yml:254` | `select(.health!="up") \| length == 0` returns 0 for both "all UP" and "0 targets matched". If relabel breaks, this passes. |
| **prior-C** | P1 | `deploy-monitoring-stack.yml:7-9` | `paths:` filter does not include `docker-compose.staging-db-monitoring.yml`. Edits at repo root won't trigger redeploy. |
| **prior-D** | P1 | `deploy-monitoring-stack.yml:38-45` | `grafana.ini.example` → `grafana.ini` copy is one-shot. Changes to example don't propagate to deployed Grafana on subsequent deploys. |
| **prior-E** | P0 | `deploy-monitoring-stack.yml:62-68` | Workflow exports `ALERT_EMAIL_*` and `ALERT_SLACK_WEBHOOK` secrets to env, but Phase 2 chose GitHub Issues. These are dead variables; if `grafana.ini.example` references them, Grafana misconfigured. |
| **prior-F** | P2 | `deploy-monitoring-stack.yml:74-75, 250-251` | Hardcoded `sleep 60` / `sleep 30`. Should be readiness polling. |
| **prior-G** | P0 | `monitoring/config/{grafana,prometheus,alertmanager}/**` | AlertManager removed from compose at commit `57fca5f` but datasource (`datasources.yml:111-115`), Prometheus alert rules (`prometheus/alerts/basic-alerts.yml`), and `alertmanager.yml` directory all still in place. Alerts fire to nowhere. |
| **prior-H** | P1 | `mirror-to-production.yml` | Whether monitoring config drift can sneak through the mirror's strip rules unintentionally. Audit will diff repo-root post-mirror payload against `monitoring/**` to confirm full propagation. |
| **prior-I** | P1 | `.github/production-workflows-examples/` and `monitoring/GITHUB_DEPLOYMENT.md:546` | No `deploy-monitoring-stack-prod.yml.example` exists. Instructions to create it live in an MD file that gets stripped during mirror. **Prod-side workflow is an audit blind spot at this time** (no read access). |

---

## 12. Risks

- **R1**: Alloy config drift across the four `*-vm.alloy` files. Three-way diff is part of the audit but small differences may still escape if the diff is not exhaustive.
- **R2**: Migrating Prometheus alert rules to Grafana unified alerting may break any external tool that reads `prometheus/api/v1/rules`. Audit will list any such consumer; if none, migration is clean.
- **R3**: GitHub Actions `repository_dispatch` rate limits and webhook reliability. The receiver workflow must be idempotent and tolerant of duplicate deliveries.
- **R4**: Prod-side workflow blind spot may hide bugs that only surface in prod. Mitigation: launch-gate runbook (Phase 4) defines a manual smoke-test against prod immediately after launch.

---

## 13. Open Questions

- **OQ-1** (resolved): Issue receiver lives in this dev `scholarship-system` repo; both staging and prod Grafanas point webhook here; label-distinguished by `env:`.
- **OQ-2** (resolved partially): Launch-gate criteria defined in §8. May need refinement after Phase 1 surfaces additional categories.
- **OQ-3** (open, deferred): Prod-side `deploy-monitoring-stack-prod.yml` content. User to obtain access later. Until then, audit treats prod-side workflow as a blind spot.

---

## 14. Acceptance Criteria

### Phase 1 (this spec's primary deliverable)

- A Markdown file at `docs/superpowers/audits/2026-05-06-monitoring-stack-audit.md` exists and is committed.
- Every finding follows the §5.4 template with all three gates (Active Probe, Static Read, Cross-Reference).
- Every priors A–I (§11) is either confirmed (becomes a numbered finding) or explicitly debunked (with evidence).
- Severity counts visible in the executive summary.
- Reproduction-artifact appendix contains at least one screenshot per dashboard.
- Cross-VM / cross-environment matrix complete (or marks prod-side cells as blind spot).

### Phase 2/3/4 (later)

Defined in their own specs, with the launch-gate criteria in §8 as the final exit condition for Phase 4.

---

## 15. Next Steps

1. User reviews this spec.
2. Spec changes (if any) are made in this file.
3. Once approved, the brainstorming flow transitions to `superpowers:writing-plans` to produce the Phase 1 audit implementation plan.
4. Phase 1 plan is executed, producing the audit report.
5. Phase 2 brainstorming begins, informed by audit findings.
