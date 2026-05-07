# R2 Audit — deploy-monitoring-stack.yml
**Branch:** feat/monitoring-phase2
**Spec:** docs/superpowers/specs/2026-05-06-monitoring-stack-fix-phase2-design.md (§6.4 + Task 21 + Task 2)
**Reviewer:** R2 (automated read-only audit)
**Date:** 2026-05-06

---

## YAML Parse

`node -e "require('js-yaml').load(fs.readFileSync(...))"` → **YAML OK**

---

## shellcheck

`shellcheck` not installed on this machine; visual review only. Observations noted inline.

---

## Concern-by-Concern Verdict

| # | Concern | Verdict | Lines |
|---|---------|---------|-------|
| Task 2 | Pre-flight secret check in BOTH jobs, all 7 secrets, fail-fast | ⚠️ | 26–51, 202–227 |
| 1 | Dead `ALERT_*` exports removed | ✅ | — |
| 2 | `grafana.ini` always overwrite (no `if [ ! -f ]` guard) | ✅ | 58–68 |
| 3 | GH_PAT file write: mkdir, chmod 700, write, chmod 600, chown 472, fail-if-empty | ✅ | 97–107 |
| 4 | `APP_NETWORK_NAME` export + unset-guard loop + network idempotency; `GRAFANA_SECRET_KEY` absent | ⚠️ | 80–94 |
| 5 | Strengthened health check: readiness loop, datasource health, provisioning logs, alert-rules API | ⚠️ | 116–178 |
| 6 | Staging metrics: poll loop, MIN_EXPECTED=7, STAGING_DOWN fail, diagnostic curl | ✅ | 343–378 |
| 7 | Tar cleanup with `if: always()` at end of job 2 | ✅ | 394–396 |

---

## Detailed Findings

### Task 2 — Pre-flight secret check: ⚠️ PARTIAL BUG

Both jobs (job 1 lines 26–51, job 2 lines 202–227) have the step and check all 7 required secrets. Implementation is correct **in isolation**, but there is a logic defect in the `for var in $REQUIRED_SECRETS` loop.

`REQUIRED_SECRETS` is a multi-line env var:

```yaml
REQUIRED_SECRETS: |
  GRAFANA_ADMIN_USER GRAFANA_ADMIN_PASSWORD GRAFANA_ROOT_URL
  STAGING_DB_HOST STAGING_DB_USER STAGING_DB_SSH_KEY
  STAGING_MONITORING_SERVER_URL
```

The `|` block scalar preserves the trailing newline. In bash, `for var in $REQUIRED_SECRETS` word-splits on whitespace including newlines — this actually works correctly on most shells when `IFS` is default. However, the spec (§5.2.2) shows a single-line `REQUIRED_SECRETS` value whereas the implementation uses a `|` literal block. On runners where `$REQUIRED_SECRETS` expands with embedded newlines and the loop iterates correctly, this is fine; it is not a guaranteed failure but is fragile. **Low severity — works in practice, but deviates from spec pattern.**

No functional blocker for the 7-secret check itself.

### Concern 1 — Dead ALERT_* exports: ✅

`grep` for `ALERT_EMAIL_FROM`, `ALERT_SMTP_HOST`, `ALERT_SMTP_PORT`, `ALERT_SMTP_USER`, `ALERT_SMTP_PASSWORD`, `ALERT_SLACK_WEBHOOK` returns zero matches. All six dead exports are gone.

### Concern 2 — grafana.ini always overwrite: ✅

No `if [ ! -f ... ]` guard present anywhere in the file. Lines 66–67 perform unconditional `cp`:
```
cp /opt/scholarship/monitoring/config/grafana/grafana.ini.example \
   /opt/scholarship/monitoring/config/grafana/grafana.ini
```
Matches spec §6.4.2 exactly.

### Concern 3 — GH_PAT file write: ✅

Lines 97–107 implement all required elements:
- `sudo mkdir -p /opt/scholarship/secrets` (line 97)
- `sudo chmod 700 /opt/scholarship/secrets` (line 98)
- `echo "..." | sudo tee ... > /dev/null` (line 99)
- `sudo chmod 600 /opt/scholarship/secrets/gh_pat` (line 100)
- `sudo chown 472:472 /opt/scholarship/secrets/gh_pat` (line 102)
- `if [ ! -s /opt/scholarship/secrets/gh_pat ]` → fail-if-empty (lines 103–106)

The spec says "fail if file empty" — `! -s` checks for non-zero size, which is correct.

### Concern 4 — APP_NETWORK_NAME + unset-guard + GRAFANA_SECRET_KEY: ⚠️ PARTIAL

**Correct:**
- `APP_NETWORK_NAME="scholarship_staging_network"` exported at line 80.
- Unset-guard loop at lines 85–90: `for var in APP_NETWORK_NAME GRAFANA_ADMIN_USER GRAFANA_ADMIN_PASSWORD GRAFANA_ROOT_URL`.
- Network idempotency at lines 93–94: `docker network inspect ... || docker network create ...`.
- `GRAFANA_SECRET_KEY` is entirely absent from the workflow (confirmed by grep).

**Gap:** The spec (§6.3.2) specifies the unset-guard loop should include `APP_NETWORK_NAME` and others. It does include `APP_NETWORK_NAME`. However, the spec also mentions `MONITORING_SERVER_URL` should be guarded in the DB job. In job 2, there is no explicit `MONITORING_SERVER_URL` unset-guard outside the SSH heredoc — the value is passed inline via `MONITORING_URL="${{ secrets.STAGING_MONITORING_SERVER_URL }}"` at line 304, but there is no `if [ -z "$MONITORING_URL" ]` check before SSH. The pre-flight step catches `STAGING_MONITORING_SERVER_URL` being unset at the secret level, which is functionally equivalent, so this is a **minor deviation** rather than a hard bug.

### Concern 5 — Strengthened health check: ⚠️ BUG

The health check step at lines 116–178 correctly implements:
- Readiness poll loop (lines 121–127, `seq 1 24`, 5s interval = 120s max)
- Fallback liveness assertion (line 128–129)
- Container liveness check (lines 132–138)
- Datasource health via API + auth header (lines 142–156)
- Provisioning error grep (lines 160–164)
- Alert rule load check (lines 168–175)

**Bug: stale `sleep 60` remains in the "Deploy monitoring stack" step (line 114).**

```yaml
# line 109-114
          # Start/restart monitoring stack
          docker compose -f docker-compose.monitoring.yml up -d

          # Wait for services to be healthy
          echo "Waiting for services to start..."
          sleep 60
```

The spec §6.4.3 says "replace sleep 60 with readiness polling" — the poll loop was added to the *health check* step, but the `sleep 60` in the *deploy* step was not removed. This means the workflow still unconditionally waits 60 seconds before the health check step even starts its own readiness poll. The two waits are additive (up to 60 + 120 = 180s), making deploys slower than necessary. More importantly, it contradicts the spec intent.

**This is a spec-compliance failure for Concern 5.**

### Concern 6 — Verify staging metrics rewrite: ✅

Lines 343–378 correctly implement:
- Poll loop replacing `sleep 30` (`seq 1 18`, 10s interval = 180s max)
- `MIN_EXPECTED=7` (line 367)
- `STAGING_TOTAL < MIN_EXPECTED` → error + diagnostic curl (lines 368–371) + `exit 1`
- `STAGING_DOWN > 0` → error + diagnostic curl of down targets (lines 373–376) + `exit 1`

Both diagnostic curls present. Full compliance with spec §6.4.4.

### Concern 7 — Tar cleanup: ✅

Lines 394–396:
```yaml
      - name: Cleanup monitoring image tar files (AP-VM)
        if: always()
        run: rm -rf /tmp/monitoring-images
```

Correctly at the end of job 2 (`deploy-staging-db-monitoring`), with `if: always()`. Note: `/tmp/monitoring-images` is also cleaned on the DB-VM side inside the SSH heredoc (line 286), which is correct and separate.

---

## Summary of Bugs

| Severity | Finding | Location |
|----------|---------|----------|
| Medium | `sleep 60` not removed from "Deploy monitoring stack" step — spec says replace it, health check poll was added to the wrong step only | Line 114 |
| Low | `REQUIRED_SECRETS` uses `|` block scalar vs. spec's inline value — fragile in exotic shell configs, works in practice | Lines 28–31, 204–207 |
| Low | `STAGING_MONITORING_SERVER_URL` unset-guard in job 2 relies on pre-flight step only; no explicit shell guard before SSH use | Line 304 |

---

## Recommended Fix

Remove lines 113–115 from the "Deploy monitoring stack" step:

```yaml
          # Wait for services to be healthy        <- delete
          echo "Waiting for services to start..."  <- delete
          sleep 60                                 <- delete
```

The health check step's own poll loop is the correct replacement, and it already exists.
