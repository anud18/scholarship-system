# R6 Documentation Cleanup Audit
**Branch**: `feat/monitoring-phase2`
**Date**: 2026-05-06
**Auditor**: R6
**Spec reference**: `docs/superpowers/specs/2026-05-06-monitoring-stack-fix-phase2-design.md` §6.7; Tasks 17, 18, 19, 20

---

## Summary

| File | AlertManager grep | Task-specific pass | Severity |
|---|---|---|---|
| `monitoring/PRODUCTION_RUNBOOK.md` | **0** | Partial — 2 stale items | MEDIUM |
| `monitoring/README.md` | **6** | Fail — ALERT_* vars still present | HIGH |
| `monitoring/GITHUB_DEPLOYMENT.md` | **0** | Pass | PASS |
| `.github/PRODUCTION_SYNC_GUIDE.md` | n/a | Pass (GH_PAT: 3, OLD: 0) | PASS |

---

## File 1 — `monitoring/PRODUCTION_RUNBOOK.md` (Task 18)

### A. AlertManager grep
```
grep -ciE "alertmanager|alert-manager|alert manager|ALERT_EMAIL|ALERT_SMTP|ALERT_SLACK" → 0
```
PASS.

### B. Task 18 requirements

**New "Alerting" section** — PRESENT (lines 433–449). Contains GitHub Issues label filter table and Grafana → Alerting navigation. PASS.

**Pre-launch smoke test reference** — PRESENT (line 449): "To verify the alert pipeline end-to-end, see Phase 2 spec §7.2." PASS.

**Stale AlertManager port 9093 references** — FAIL (2 occurrences):

| Line | Content |
|---|---|
| 66 | `curl -f http://localhost:9093/-/healthy &&` — in "One-Line Health Check" |
| 379 | `curl -s http://localhost:9093/api/v2/alerts …` — in "Weekly Tasks" |

Both curl commands reach the AlertManager HTTP API which is removed in Phase 2. They will silently fail (connection refused) because the AlertManager container no longer exists. The health check one-liner at line 66 includes this call in an `&&` chain, meaning the entire check will fail even when all remaining services are healthy.

**Severity**: MEDIUM — operational scripts produce false failures post-AlertManager removal.

### F. Markdown integrity
- Code fences: 58 (balanced). PASS.
- Internal links: 6/6 valid. PASS.

---

## File 2 — `monitoring/README.md` (Task 19)

### A. AlertManager grep
```
grep -ciE "alertmanager|alert-manager|alert manager|ALERT_EMAIL|ALERT_SMTP|ALERT_SLACK" → 6
```
FAIL. All 6 occurrences listed:

| Line | Pattern | Context |
|---|---|---|
| 90 | `email, Slack` | Features > Alerting bullet: "Multi-channel notifications (email, Slack)" |
| 159 | `ALERT_EMAIL_FROM` | Quick Start Step 1 `.env.monitoring` example block |
| 160 | `ALERT_SMTP_HOST` | same block |
| 161 | `ALERT_SMTP_PORT` | same block |
| 162 | `ALERT_SMTP_USER` | same block |
| 163 | `ALERT_SMTP_PASSWORD` | same block |
| 166 | `ALERT_SLACK_WEBHOOK` | same block |

(The grep matched 6 lines; the tool returned 6 because line 163 and 166 were counted but `grep -c` reports line count. ALERT_SLACK appears at line 166 as the 6th match.)

### C. Task 19 requirements

**Architecture diagram updated** — PASS. The ASCII diagram (lines 23–51) shows `Grafana Alerting → GitHub Issues` in place of an AlertManager box. No AlertManager box is present.

**"Grafana unified alerting" replacement language** — PARTIAL.

- `### Grafana Alerting` section (line 286) correctly states: "Alerts are managed via Grafana unified alerting and delivered to GitHub Issues." PASS.
- However, `### Alerting` feature list (lines 88–94) still contains the OLD Phase 1 bullets:
  - "Multi-channel notifications (email, Slack)" — **should be removed or replaced** with "Alert delivery via GitHub Issues"
  - "Alert inhibition rules" — AlertManager-specific concept, no longer applicable

**Quick Start Step 1 env block** (lines 155–167) — FAIL. Still instructs operators to configure `ALERT_EMAIL_*` and `ALERT_SLACK_WEBHOOK` in `.env.monitoring`. These variables are not consumed by Grafana unified alerting (which uses `GH_PAT`). Leaving them in misleads operators and creates the impression the old notification channels still function.

**Production Deployment Preparation Checklist** (line 655) — FAIL. Still contains:
```
- [ ] Configure production alert channels (email, Slack)
```
Should reference GH_PAT secret and GitHub Issues contact point instead.

**Severity**: HIGH — operators following the Quick Start guide will add non-functional env vars and believe email/Slack alerting is active when it is not.

### F. Markdown integrity
- Code fences: 72 (balanced). PASS.
- Internal links: 11/11 valid. PASS.

---

## File 3 — `monitoring/GITHUB_DEPLOYMENT.md` (Tasks 1, 20)

### A. AlertManager grep
```
grep -ciE "alertmanager|alert-manager|alert manager|ALERT_EMAIL|ALERT_SMTP|ALERT_SLACK" → 0
```
PASS.

### D. Task 1 + 20 requirements

**"Repo Migration Checklist" section** — PRESENT (lines 558–593). Contains:
- 7-row secrets table with correct names (`GRAFANA_ADMIN_USER`, `GRAFANA_ADMIN_PASSWORD`, `GRAFANA_ROOT_URL`, `STAGING_DB_HOST`, `STAGING_DB_USER`, `STAGING_DB_SSH_KEY`, `STAGING_MONITORING_SERVER_URL`). Note: `GRAFANA_SECRET_KEY` explicitly documented as intentionally absent. Table is valid. PASS.
- Runner registration instructions (lines 579–580). PASS.
- Verification commands (`gh workflow run` + `gh run watch`, lines 587–588). PASS.

**Old "Alert Configuration Secrets (Optional)" section** — GONE. PASS.

**GH_PAT replacement section** — PRESENT. Lines 93–97 contain a brief paragraph explaining that alerting-related secrets are now handled solely by `GH_PAT`, mounted at `/etc/grafana/secrets/gh_pat`. PASS.

**Stale AlertManager 9093 reference in Manual Deployment block** (line 252):
```bash
curl http://localhost:9093/-/healthy
```
This is in the "Manual Deployment → Step 1" section and probes AlertManager. Should be removed or replaced.

**Severity**: LOW — only appears in a manual-deployment reference block, less critical than the operational runbook commands; operator is less likely to run this verbatim.

### F. Markdown integrity
- Code fences: 38 (balanced). PASS.
- Internal links: 7/7 valid. PASS.

---

## File 4 — `.github/PRODUCTION_SYNC_GUIDE.md` (Task 17)

### E. Token rename verification
```
grep -c "PRODUCTION_SYNC_PAT" → 0   PASS
grep -c "GH_PAT"              → 3   PASS (requirement: at least 3)
```
All three occurrences confirmed at lines 68, 389, 393 — matching the three expected rename locations (secrets table row, troubleshooting heading, troubleshooting body).

### F. Markdown integrity
- Code fences: 60 (balanced). PASS.
- Internal links: 0 (no internal anchor links present — correct for this document). PASS.

---

## Issues Requiring Action

| ID | Severity | File | Description |
|---|---|---|---|
| R6-01 | HIGH | `monitoring/README.md:159-166` | `ALERT_EMAIL_*` and `ALERT_SLACK_WEBHOOK` env vars in Quick Start env block must be removed |
| R6-02 | HIGH | `monitoring/README.md:90` | Feature bullet "Multi-channel notifications (email, Slack)" must be updated to GitHub Issues delivery |
| R6-03 | HIGH | `monitoring/README.md:655` | Checklist item "Configure production alert channels (email, Slack)" must be updated |
| R6-04 | MEDIUM | `monitoring/PRODUCTION_RUNBOOK.md:66` | Stale `curl http://localhost:9093/-/healthy` in one-line health check — breaks `&&` chain |
| R6-05 | MEDIUM | `monitoring/PRODUCTION_RUNBOOK.md:379` | Stale `curl -s http://localhost:9093/api/v2/alerts` in Weekly Tasks |
| R6-06 | LOW | `monitoring/GITHUB_DEPLOYMENT.md:252` | Stale `curl http://localhost:9093/-/healthy` in manual deployment step |

---

## Passing Items

- `monitoring/PRODUCTION_RUNBOOK.md`: AlertManager keyword grep = 0; new Alerting section with GitHub Issues table and smoke-test spec reference present; all code fences balanced; all internal links valid.
- `monitoring/GITHUB_DEPLOYMENT.md`: AlertManager keyword grep = 0; Repo Migration Checklist present with 7-secret table, runner instructions, verification commands; old Alert Configuration Secrets section absent; GH_PAT mount path documented; code fences balanced; internal links valid.
- `.github/PRODUCTION_SYNC_GUIDE.md`: `PRODUCTION_SYNC_PAT` count = 0; `GH_PAT` count = 3; code fences balanced; no broken links.
