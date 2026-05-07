# Branch E — Deploy & Mirror Pipeline Audit Working File

**Branch prefix**: `F-DEPL`
**Spec ref**: `docs/superpowers/specs/2026-05-06-monitoring-stack-fix-design.md` (commit `07faa57`)
**Audit date**: 2026-05-06
**Auditor**: Branch E agent

---

## Findings

### F-DEPL-01  [P0]  Health check passes while datasource is returning 500

**Where**: `.github/workflows/deploy-monitoring-stack.yml:77-110`

**Evidence**:
- Active probe: `gh workflow view deploy-monitoring-stack.yml` shows "Total runs 0" in current repo (anud18/scholarship-system). Previous runs in the original repo (jotpalch/scholarship-system) succeeded, and the old-repo-run-19155493587-log.txt fetch returned HTTP 410 (logs expired). The health check step at lines 77-110 only probes `Grafana /api/health`, `Prometheus /-/healthy`, and `Loki /ready` — HTTP-level endpoints that return 200 regardless of datasource state.
- Static read: `.github/workflows/deploy-monitoring-stack.yml:85-106`:
  ```yaml
  if docker exec monitoring_grafana wget --spider -q http://localhost:3000/api/health; then
    echo "✅ Grafana is healthy"
  ...
  if curl -f http://localhost:9090/-/healthy > /dev/null 2>&1; then
    echo "✅ Prometheus is healthy"
  ...
  if curl -f http://localhost:3100/ready > /dev/null 2>&1; then
    echo "✅ Loki is healthy"
  ```
  No step calls `GET /api/datasources/uid/{uid}/health`, no step inspects Grafana provisioning logs for errors, no step checks alert rule load status.
- Cross-reference: The Grafana alertmanager datasource returns HTTP 500 ("Plugin unavailable") as confirmed by the spec §1 context and prior-G. A deploy that checks only `Grafana /api/health` (which returns 200 `{"database":"ok"}`) would pass its health check step while the alertmanager datasource is broken. The deploy workflow has never caught this class of failure.

**Expected**: The health check step should additionally call `GET /monitoring/api/datasources/uid/{uid}/health` for each provisioned datasource, assert every response is 2xx, and verify Grafana startup logs show no provisioning errors.

**Root cause hypothesis**: The health check was written to verify container liveness only, not Grafana datasource health or provisioning correctness, so any sub-service failure is invisible to CI.

**Remediation owner**: Phase 2

**Suggested fix sketch**:
```bash
# After Grafana starts, check all datasource health
DS_FAILURES=$(docker exec monitoring_grafana \
  wget -qO- "http://localhost:3000/api/datasources" \
  --header "Authorization: Basic $(echo -n admin:$GRAFANA_ADMIN_PASSWORD | base64)" \
  | jq '[.[] | .uid][]' -r | while read uid; do
    STATUS=$(docker exec monitoring_grafana wget -qO- \
      "http://localhost:3000/api/datasources/uid/$uid/health" \
      --header "Authorization: Basic $(echo -n admin:$GRAFANA_ADMIN_PASSWORD | base64)" \
      | jq -r '.status // "error"')
    [ "$STATUS" != "OK" ] && echo "$uid: $STATUS"
  done)
[ -z "$DS_FAILURES" ] || { echo "❌ Datasource failures: $DS_FAILURES"; exit 1; }
```

---

### F-DEPL-02  [P0]  False-positive Prometheus target check silently passes when zero staging targets exist

**Where**: `.github/workflows/deploy-monitoring-stack.yml:248-261`

**Evidence**:
- Active probe: `targets.json` (captured at `api-responses/prometheus-loki/targets.json`) shows exactly 3 active targets, all with `environment="monitoring"` — zero targets have `environment="staging"`. Running the workflow's exact jq expression `[.data.activeTargets[] | select(.labels.environment=="staging") | select(.health!="up")] | length` against this data returns `0`, causing the "All staging targets are UP" message. This is confirmed by Python simulation: `staging_down = 0` even though 0 staging targets exist at all.
- Static read: `.github/workflows/deploy-monitoring-stack.yml:253-260`:
  ```bash
  TARGETS_DOWN=$(curl -s http://localhost:9090/api/v1/targets | jq '[.data.activeTargets[] | select(.labels.environment=="staging") | select(.health!="up")] | length')
  if [ "$TARGETS_DOWN" -eq "0" ]; then
    echo "✅ All staging targets are UP"
  ```
- Cross-reference: The step prints "✅ All staging targets are UP" (and does not exit non-zero — it uses `⚠️ Warning` not `exit 1`) even when Alloy on DB-VM has never registered a target with `environment=staging`. The live Prometheus has only `environment=monitoring` targets (self-monitoring of grafana, loki, prometheus), meaning every past run of this step has silently declared success with zero staging coverage.

**Expected**: The check should first assert that the count of `environment=staging` targets is at least the expected minimum (e.g., node-exporter, postgres-exporter, alloy on DB-VM), then assert none are down. If the count is 0, the step should fail.

**Root cause hypothesis**: The jq filter treats "no targets match" identically to "all matching targets are UP", because `length` of an empty array is 0 in both cases.

**Remediation owner**: Phase 2

**Suggested fix sketch**:
```bash
STAGING_TOTAL=$(curl -s http://localhost:9090/api/v1/targets | jq '[.data.activeTargets[] | select(.labels.environment=="staging")] | length')
STAGING_DOWN=$(curl -s http://localhost:9090/api/v1/targets | jq '[.data.activeTargets[] | select(.labels.environment=="staging") | select(.health!="up")] | length')
MIN_EXPECTED=3  # node-exporter, postgres-exporter, alloy (DB-VM)
if [ "$STAGING_TOTAL" -lt "$MIN_EXPECTED" ]; then
  echo "❌ Only $STAGING_TOTAL staging targets found; expected at least $MIN_EXPECTED"; exit 1
fi
if [ "$STAGING_DOWN" -gt "0" ]; then
  echo "❌ $STAGING_DOWN staging targets are DOWN"; exit 1
fi
echo "✅ $STAGING_TOTAL staging targets all UP"
```

---

### F-DEPL-03  [P0]  Workflow has zero runs in current repo — IaC-first principle broken for staging

**Where**: `.github/workflows/deploy-monitoring-stack.yml` (entire workflow), GitHub Actions run history

**Evidence**:
- Active probe: `gh workflow view deploy-monitoring-stack.yml` output: "Total runs 0". `gh run list --workflow=deploy-monitoring-stack.yml --limit=30` returns `[]`. The workflow file has `workflow_id: 209788291` and is enabled, but has never been triggered in this repository (anud18/scholarship-system).
- Static read: `api-responses/deploy-pipeline/old-repo-deploy-runs.json` shows 10 successful runs in the previous repository (jotpalch/scholarship-system), the most recent at `2025-11-07T01:43:05Z` (commit `d14318a` = "Refactor database configuration"). All subsequent monitoring commits (e.g., the Phase 1 audit branch) have never triggered the workflow in this repo.
- Cross-reference: The workflow triggers on `push` to `main` in `monitoring/**` and on `workflow_dispatch`. The repo was migrated from jotpalch to anud18 — the self-hosted runner is presumably still registered to the old repo or not re-registered. Staging Grafana (`https://ss.test.nycu.edu.tw/monitoring`) is live (per other branches' probes), meaning it was deployed outside the IaC workflow after the repo migration.

**Expected**: Every deploy to staging should be traceable to a CI run. Zero runs means staging config could diverge from this repo at any time with no detection.

**Root cause hypothesis**: The GitHub Actions self-hosted runner was not re-registered to the new repository (anud18/scholarship-system) after repo migration, so no pushes trigger the workflow.

**Remediation owner**: Phase 2 (re-register runner) — also needs a pre-flight check that runner is online before the next fix PR merges.

**Suggested fix sketch**: Re-register the self-hosted runner token under Settings → Actions → Runners in anud18/scholarship-system. Verify with a `workflow_dispatch` trigger. Document in `monitoring/GITHUB_DEPLOYMENT.md` that runner must be re-registered on repo migration.

---

### F-DEPL-04  [P0]  Prod monitoring compose references `scholarship_staging_network` — likely broken on prod AP-VM

**Where**: `monitoring/docker-compose.monitoring.yml:46,75,118,160-162` (dev repo) and `api-responses/deploy-pipeline/prod-monitoring-compose.yml` (user-supplied prod snapshot)

**Evidence**:
- Active probe: User-supplied snapshot `prod-monitoring-compose.yml` (captured from `root@jotp:~/naass/monitoring/docker-compose.monitoring.yml` on prod AP-VM). The file is byte-identical to the dev repo's `monitoring/docker-compose.monitoring.yml`. Both declare:
  ```yaml
  networks:
    scholarship_staging_network:
      external: true
      name: scholarship_staging_network
  ```
  and attach grafana, loki, and prometheus to `scholarship_staging_network`. The network `scholarship_staging_network` is defined as `external: true`, meaning Docker Compose expects this network to already exist on the host.
- Static read: `monitoring/docker-compose.monitoring.yml:160-162`:
  ```yaml
  scholarship_staging_network:
    external: true
    name: scholarship_staging_network
  ```
  The network is created by `docker-compose.staging.yml` in the dev/staging environment. On prod AP-VM, no staging application stack runs, so `scholarship_staging_network` almost certainly does not exist.
- Cross-reference: The prod AP-VM is described as running the production application stack (`docker-compose.prod.yml`), which uses `scholarship_prod_network` (not `scholarship_staging_network`). If monitoring were restarted on prod AP-VM with this compose file, all three monitoring services would fail to start with `network scholarship_staging_network declared as external, but could not be found`.

**Expected**: The prod monitoring compose should reference `scholarship_prod_network` (or no external network, if cross-service DNS is not needed). A separate `docker-compose.prod-monitoring.yml` distinct from the staging version should exist.

**Root cause hypothesis**: The monitoring compose file was written for staging and then deployed to prod without renaming the external network reference, because the prod monitoring stack was set up via manual copy rather than a prod-specific file.

**Remediation owner**: Phase 2

**Suggested fix sketch**: Create `monitoring/docker-compose.prod-monitoring.yml` with `scholarship_prod_network` as the external network, or remove the external network reference from the prod compose if monitoring containers communicate only over `monitoring_network`. Update the mirror and prod-side deploy workflow to use the prod-specific compose file.

---

### F-DEPL-05  [P1]  `paths:` filter omits `docker-compose.staging-db-monitoring.yml`

**Where**: `.github/workflows/deploy-monitoring-stack.yml:7-9`

**Evidence**:
- Active probe: File exists at repo root: `ls docker-compose.staging-db-monitoring.yml → FILE_EXISTS`. It is used in job 2 (deploy-staging-db-monitoring) at line 219: `scp ... ./docker-compose.staging-db-monitoring.yml ...`. Changes to this file would affect DB-VM monitoring deployment but would not trigger the workflow.
- Static read: `.github/workflows/deploy-monitoring-stack.yml:6-9`:
  ```yaml
  paths:
    - 'monitoring/**'
    - '.github/workflows/deploy-monitoring-stack.yml'
  ```
  `docker-compose.staging-db-monitoring.yml` is at the repo root (not under `monitoring/`), so it is not covered by the `monitoring/**` glob.
- Cross-reference: If a developer changes only `docker-compose.staging-db-monitoring.yml` (e.g., to fix a DB-VM exporter port), the workflow does not auto-trigger. The change sits in main without being deployed to staging until someone manually triggers `workflow_dispatch` or pushes another `monitoring/**` change.

**Expected**: `paths:` should include `'docker-compose.staging-db-monitoring.yml'` so that changes to the DB-VM compose file trigger a redeploy.

**Root cause hypothesis**: The file was added at the repo root after the `paths:` filter was written, and the filter was not updated.

**Remediation owner**: Phase 4 (spec §8 lists this fix explicitly)

**Suggested fix sketch**:
```yaml
paths:
  - 'monitoring/**'
  - 'docker-compose.staging-db-monitoring.yml'
  - '.github/workflows/deploy-monitoring-stack.yml'
```

---

### F-DEPL-06  [P1]  `grafana.ini.example` → `grafana.ini` copy is one-shot; subsequent changes silently ignored

**Where**: `.github/workflows/deploy-monitoring-stack.yml:38-45`

**Evidence**:
- Active probe: Commit `9175ac0` ("Security: Remove grafana.ini from version control while maintaining deployment functionality") introduced the `if [ ! -f ... ]` guard. After that commit, `grafana.ini` on the runner was never updated by subsequent runs.
- Static read: `.github/workflows/deploy-monitoring-stack.yml:38-45`:
  ```yaml
  if [ ! -f /opt/scholarship/monitoring/config/grafana/grafana.ini ]; then
    echo "Creating Grafana configuration from example..."
    cp /opt/scholarship/monitoring/config/grafana/grafana.ini.example \
       /opt/scholarship/monitoring/config/grafana/grafana.ini
    echo "✅ Grafana configuration initialized"
  else
    echo "✅ Grafana configuration already exists"
  fi
  ```
  Once `grafana.ini` exists, the copy is skipped forever. Any change to `grafana.ini.example` (e.g., adding a new section, fixing a parameter) is silently ignored on redeploy.
- Cross-reference: `monitoring/config/grafana/grafana.ini.example` has 264 lines of configuration (verified by Read). A fix to any of those lines — for example, correcting `root_url`, adjusting session parameters, or enabling a feature toggle — would not take effect on the running Grafana instance until someone manually deletes the live `grafana.ini` on the runner and re-runs the workflow.

**Expected**: The deploy step should compare the example's content hash to the deployed file and replace if changed, or always overwrite with the example (with a note that operator-local overrides must be re-applied). Alternatively, use environment variables exclusively (as Grafana supports) and remove the `grafana.ini` file requirement.

**Root cause hypothesis**: The one-shot copy was designed to prevent overwriting operator secrets embedded in `grafana.ini`, but the result is that the example and the deployed file can drift indefinitely.

**Remediation owner**: Phase 2 (config drift is P1 but the root cause — secrets in ini file — is a P1 architectural issue that blocks any clean fix)

**Suggested fix sketch**:
```bash
# Always propagate the example, overwriting the deployed copy.
# Secrets (admin_user, admin_password, secret_key) are read from env vars
# by Grafana anyway (GF_SECURITY_* env vars set in compose), so the
# grafana.ini does not need to contain secrets.
cp /opt/scholarship/monitoring/config/grafana/grafana.ini.example \
   /opt/scholarship/monitoring/config/grafana/grafana.ini
echo "✅ Grafana configuration updated from example"
```

---

### F-DEPL-07  [P0]  Dead `ALERT_EMAIL_*` and `ALERT_SLACK_WEBHOOK` env exports — potential Grafana misconfiguration

**Where**: `.github/workflows/deploy-monitoring-stack.yml:62-68`

**Evidence**:
- Active probe: `grep -rn "ALERT_EMAIL\|ALERT_SMTP\|ALERT_SLACK" monitoring/config/grafana/grafana.ini.example` returns 0 matches. The `grafana.ini.example` does not reference these env vars. However, `monitoring/config/alertmanager/alertmanager.yml` (lines 7-10) references `${ALERT_SMTP_SMARTHOST}`, `${ALERT_EMAIL_FROM}`, `${ALERT_SMTP_USER}`, `${ALERT_SMTP_PASSWORD}`, and `monitoring/README.md:158-165` and `monitoring/GITHUB_DEPLOYMENT.md:97-102` document these secrets as valid alert configuration.
- Static read: `.github/workflows/deploy-monitoring-stack.yml:62-68`:
  ```yaml
  export ALERT_EMAIL_FROM="${{ secrets.ALERT_EMAIL_FROM }}"
  export ALERT_SMTP_HOST="${{ secrets.ALERT_SMTP_HOST }}"
  export ALERT_SMTP_PORT="${{ secrets.ALERT_SMTP_PORT }}"
  export ALERT_SMTP_USER="${{ secrets.ALERT_SMTP_USER }}"
  export ALERT_SMTP_PASSWORD="${{ secrets.ALERT_SMTP_PASSWORD }}"
  export ALERT_SLACK_WEBHOOK="${{ secrets.ALERT_SLACK_WEBHOOK }}"
  ```
  AlertManager was removed from the compose stack (commit `57fca5f` / noted in workflow line 108: "Note: AlertManager has been removed from the monitoring stack"). These secrets are exported but never consumed by any running container.
- Cross-reference: Phase 2 decided to use GitHub Issues as the alert receiver (spec §6). These 6 env exports are dead. If the GitHub repository has secrets with these names configured, they expand to real values in the workflow logs (masked, but still processed), creating unnecessary secret surface. If the secrets are not configured, the exports produce empty strings — harmless but confusing to operators reading the workflow.

**Expected**: Remove all 6 dead `ALERT_*` exports once the Phase 2 GitHub Issues receiver is wired. Document in a comment that `ALERT_*` secrets are deprecated.

**Root cause hypothesis**: AlertManager was removed from the compose stack but the workflow's environment setup step was not updated to remove the corresponding secret exports.

**Remediation owner**: Phase 2

**Suggested fix sketch**: Delete lines 62-68 from the workflow (the `export ALERT_EMAIL_FROM` through `export ALERT_SLACK_WEBHOOK` block) after Phase 2 wires the GitHub Issues contact point.

---

### F-DEPL-08  [P2]  Hardcoded `sleep 60` and `sleep 30` — should use readiness polling

**Where**: `.github/workflows/deploy-monitoring-stack.yml:74-75` and `250-251`

**Evidence**:
- Active probe: Not applicable (static analysis finding). Both sleeps are unconditional fixed waits.
- Static read:
  - Line 74-75: `echo "Waiting for services to start..."; sleep 60`
  - Line 250-251: `echo "Waiting for metrics to be collected..."; sleep 30`
  Both are inside `run:` blocks with no retry logic.
- Cross-reference: The `sleep 60` is followed by health checks that could succeed in 10s on a warm host or fail even after 60s if the host is slow. The `sleep 30` before `Verify staging metrics` is arbitrary — metrics collection latency depends on Alloy scrape interval and Prometheus scrape interval, both of which are configurable. The spec (§8) explicitly calls these out as P2 to replace with readiness polling.

**Expected**: Replace `sleep 60` with a poll loop that checks `Grafana /api/health` every 5 seconds until it returns 200 (max 120s timeout). Replace `sleep 30` with a poll loop that checks Prometheus target count until `environment=staging` count > 0 (max 90s).

**Root cause hypothesis**: Hardcoded sleeps are simpler to write and work "most of the time" on consistent hardware; readiness polling was deferred.

**Remediation owner**: Phase 4 (spec §8 explicitly lists this)

**Suggested fix sketch**:
```bash
# Replace sleep 60 with:
for i in $(seq 1 24); do
  docker exec monitoring_grafana wget --spider -q http://localhost:3000/api/health && break
  echo "Waiting for Grafana... ($i/24)"
  sleep 5
done || { echo "❌ Grafana did not start in 120s"; exit 1; }
```

---

### F-DEPL-09  [P1]  Mirror strips all `*.md` including `monitoring/GITHUB_DEPLOYMENT.md` and `monitoring/PRODUCTION_RUNBOOK.md`

**Where**: `.github/workflows/mirror-to-production.yml:341-344` and spec §9 principle

**Evidence**:
- Active probe: `grep -n '\.md' mirror-to-production.yml:341` shows:
  ```bash
  find . -type f -name "*.md" 2>/dev/null | xargs -r git rm -f 2>/dev/null || true
  ```
  This `find` starts at `.` (repo root) and matches ALL `.md` files, including files under `monitoring/`.
- Static read: Files confirmed to exist and be stripped:
  - `monitoring/GITHUB_DEPLOYMENT.md` (deployment guide including self-hosted runner setup, secrets reference)
  - `monitoring/PRODUCTION_RUNBOOK.md` (health check commands, incident response)
  - `monitoring/README.md` (architecture overview)
  These three files contain operational knowledge that prod-side maintainers need.
- Cross-reference: Spec §9 cross-phase engineering principle states: "Documentation lives under `monitoring/**/*.md`. Repo-root `*.md` files are stripped by `mirror-to-production.yml`, so prod-side maintainers cannot see them. Anything prod-relevant goes inside `monitoring/`." The spec correctly anticipates that docs should survive in `monitoring/` — but the actual mirror strips them too. The spec's principle is violated by the mirror implementation.

**Expected**: Documentation under `monitoring/` should survive the mirror. The strip rule should exclude `./monitoring/**/*.md` (or include `monitoring/` docs in a preservation list).

**Root cause hypothesis**: The `find . -type f -name "*.md"` strip rule was written to remove all repo-root documentation (`README.md`, `CONTRIBUTING.md`, etc.) without considering that `monitoring/*.md` files are operationally necessary in prod.

**Remediation owner**: Phase 2 (the missing docs prevent prod operators from following deployment and runbook procedures)

**Suggested fix sketch**: Change the strip rule to exclude `monitoring/`:
```bash
find . -type f -name "*.md" -not -path "./monitoring/*" 2>/dev/null | xargs -r git rm -f 2>/dev/null || true
```

---

### F-DEPL-10  [P1]  `PRODUCTION_SYNC_GUIDE.md` documents wrong secret name (`PRODUCTION_SYNC_PAT` vs actual `GH_PAT`)

**Where**: `.github/PRODUCTION_SYNC_GUIDE.md:68,389,394` vs `.github/workflows/mirror-to-production.yml:37,47,91`

**Evidence**:
- Active probe: `grep -n "GH_PAT\|PRODUCTION_SYNC_PAT"` on both files confirms: the workflow uses `secrets.GH_PAT` in 4 places (lines 37, 47, 48, 91, 765); the PRODUCTION_SYNC_GUIDE.md instructs operators to create a secret named `PRODUCTION_SYNC_PAT` (lines 68, 389, 394).
- Static read:
  - `PRODUCTION_SYNC_GUIDE.md:68`: `| PRODUCTION_SYNC_PAT | ghp_xxxxxxxxxxxx | Personal Access Token from Step 2 |`
  - `PRODUCTION_SYNC_GUIDE.md:389`: `### Issue: "PRODUCTION_SYNC_PAT not configured"`
  - `mirror-to-production.yml:47-48`: `if [ -z "${{ secrets.GH_PAT }}" ]; then echo "::error::GH_PAT secret not configured"`
- Cross-reference: An operator following the guide would create a secret named `PRODUCTION_SYNC_PAT`. The workflow checks for `GH_PAT`. The workflow would immediately fail at step "Check for required secrets" with "GH_PAT secret not configured", even though the secret exists under the wrong name. The guide's troubleshooting section would also not help (it says check for `PRODUCTION_SYNC_PAT`, not `GH_PAT`).

**Expected**: The guide and the workflow must use the same secret name. Preferred: rename the guide to match the workflow (`GH_PAT`), or rename the workflow to match the guide (`PRODUCTION_SYNC_PAT`) — consistency either way.

**Root cause hypothesis**: The secret was renamed from `PRODUCTION_SYNC_PAT` to `GH_PAT` in the workflow at some point but the documentation was not updated, or vice versa.

**Remediation owner**: Phase 2

**Suggested fix sketch**: Update `PRODUCTION_SYNC_GUIDE.md` to replace all occurrences of `PRODUCTION_SYNC_PAT` with `GH_PAT` (3 locations).

---

### F-DEPL-11  [P1]  No `deploy-monitoring-stack-prod.yml.example` in `.github/production-workflows-examples/` — prod deploy is a blind spot

**Where**: `.github/production-workflows-examples/` (directory listing) and `monitoring/GITHUB_DEPLOYMENT.md`

**Evidence**:
- Active probe: `ls .github/production-workflows-examples/` output:
  ```
  auto-tag-on-merge.yml
  backup.yml
  deploy.yml
  health-check.yml
  IT-BACKUP-TRANSFER-GUIDE.md
  README.md
  SECRETS-SETUP-GUIDE.md
  setting-env.yml
  ```
  No `deploy-monitoring-stack-prod.yml.example` or any monitoring-specific workflow example exists. `grep -rn "deploy-monitoring\|monitoring-stack" .github/production-workflows-examples/` returns 0 matches.
- Static read: `monitoring/GITHUB_DEPLOYMENT.md` describes the staging deploy workflow in detail. It does not provide a corresponding template for the prod-side deploy workflow. The spec (§10) states: "Prod-side `deploy-monitoring-stack-prod.yml` is not visible from this repo. Audit treats this as a known gap." The directory that exists to house prod-side examples (`production-workflows-examples/`) contains no monitoring workflow.
- Cross-reference: The spec §10 states the prod-side deploy workflow "lives only in the private prod repo as `deploy-monitoring-stack-prod.yml`". With no example in this repo and no documentation for how the prod workflow should differ from staging, prod-side maintainers have no guidance. Additionally, `.github/production-workflows-examples/` is itself stripped by the mirror (line 255: `git rm -rf .github/production-workflows-examples/`), so even if an example were added here, prod maintainers in the prod repo would not see it.

**Expected**: A `deploy-monitoring-stack-prod.yml.example` should exist in `.github/production-workflows-examples/` documenting the prod-equivalent deploy workflow. The example should note prod-specific differences (e.g., `scholarship_prod_network` instead of `scholarship_staging_network`, prod secrets names, prod runner label). Additionally, the `monitoring/GITHUB_DEPLOYMENT.md` should include a section on prod-specific deployment.

**Root cause hypothesis**: The prod deploy workflow was created directly in the private prod repo without a corresponding example or documentation being added to the dev repo.

**Remediation owner**: Phase 2 (this is marked as a "blind spot" per spec §5.1 — no access to prod workflow content; owner must provide the prod workflow content for review)

**Suggested fix sketch**: Create `.github/production-workflows-examples/deploy-monitoring-stack-prod.yml.example` based on the staging workflow with prod-specific parameter differences documented inline. Note: this directory is stripped by mirror, so also add a summary in `monitoring/GITHUB_DEPLOYMENT.md` (which should survive mirror per F-DEPL-09 fix).

---

### F-DEPL-12  [P1]  AP-VM `/tmp/monitoring-images/` tar files accumulate across runs — no local cleanup

**Where**: `.github/workflows/deploy-monitoring-stack.yml:143-170`

**Evidence**:
- Active probe: Not directly observable from the local audit, but static analysis is conclusive: the "Export monitoring images for DB-VM" step at lines 143-157 creates `/tmp/monitoring-images/` with three `.tar` files (alloy.tar ~600MB, node-exporter.tar ~25MB, postgres-exporter.tar ~60MB — typical sizes). The "Import monitoring images on DB-VM" step at lines 178-194 runs `rm -rf /tmp/monitoring-images` inside the SSH heredoc (remote side, DB-VM). No `rm -rf /tmp/monitoring-images` command exists on the AP-VM (runner) side.
- Static read: Lines 143-170 of the workflow show three steps: "Export monitoring images for DB-VM" (creates /tmp/monitoring-images on AP-VM), "Transfer monitoring images to DB-VM" (scp to remote), "Import monitoring images on DB-VM" (loads + rm -rf on DB-VM only). The AP-VM cleanup is absent.
- Cross-reference: Each workflow run deposits approximately 700MB of tar files in AP-VM's `/tmp/`. Over 10 runs (historical count from old-repo-deploy-runs.json), this would accumulate ~7GB. If AP-VM `/tmp/` fills, future runs fail at the `docker save` step with "no space left on device".

**Expected**: Add a cleanup step after the transfer that runs `rm -rf /tmp/monitoring-images` on the AP-VM (runner) side. Alternatively, add `if: always()` cleanup at the job level.

**Root cause hypothesis**: The remote cleanup was added but the local (runner-side) cleanup was forgotten, likely because the author focused on the remote side.

**Remediation owner**: Phase 2 (risk of disk exhaustion is operational)

**Suggested fix sketch**:
```yaml
- name: Cleanup monitoring image tar files (AP-VM)
  if: always()
  run: rm -rf /tmp/monitoring-images
```

---

### F-DEPL-13  [P1]  `docker-compose.prod-db-monitoring.yml` preserved by mirror but prod-side deploy workflow is unknown — chain integrity unverifiable

**Where**: `.github/workflows/mirror-to-production.yml:280-282` and `docker-compose.prod-db-monitoring.yml`

**Evidence**:
- Active probe: `ls docker-compose.prod-db-monitoring.yml → IN_DEV_REPO` (file exists). Mirror workflow at line 280-282 explicitly preserves it:
  ```bash
  if [[ "$file" == "docker-compose.prod-db-monitoring.yml" ]]; then
    echo "::notice::Preserving $file (production file)"
  ```
  User-supplied prod snapshot `api-responses/deploy-pipeline/prod-db-monitoring-compose.yml` is byte-identical to the dev repo's copy (source annotation confirms: "Captured: 2026-05-06 during Phase 1 audit Stage 0.4"). The prod DB-VM's Alloy reads `./monitoring/config/alloy/prod-db-vm.alloy` — that path works only if the prod-side deploy workflow ships the `monitoring/config/alloy/` tree to the DB-VM, which is not visible.
- Static read: `docker-compose.prod-db-monitoring.yml:19` mounts `./monitoring/config/alloy/prod-db-vm.alloy:/etc/alloy/config.alloy:ro`. This mount works only if the file exists at `./monitoring/config/alloy/prod-db-vm.alloy` relative to where the compose file is run from. On the prod DB-VM, the alloy config must have been deployed separately (since the DB-VM receives the compose file but not the monitoring config tree via the staging workflow — the staging workflow ships `staging-db-vm.alloy` via SCP at line 229).
- Cross-reference: No prod-side equivalent of lines 226-231 (SCP of `staging-db-vm.alloy` to DB-VM) is visible. If the prod deploy workflow omits this SCP step, the Alloy container on prod DB-VM starts with no config file, silently logs errors, and collects no metrics.

**Expected**: The prod-side deploy workflow should SCP `monitoring/config/alloy/prod-db-vm.alloy` to the prod DB-VM before starting the compose stack. This should be documented in `monitoring/GITHUB_DEPLOYMENT.md`.

**Root cause hypothesis**: The prod-side workflow is a blind spot — its content is unknown from this repo. The chain of `docker-compose.prod-db-monitoring.yml` → alloy config file → prod deploy workflow cannot be fully verified.

**Remediation owner**: Phase 2 (requires prod repo access; mark as prod-side blind spot pending access)

**Suggested fix sketch**: Pending prod repo access. Document the required alloy config SCP step in `monitoring/GITHUB_DEPLOYMENT.md` so it is visible to prod-side maintainers.

---

### F-DEPL-14  [noted]  `mirror-to-production.yml` describes "Automatic Sync" in `PRODUCTION_SYNC_GUIDE.md` but workflow is manual-only

**Where**: `.github/PRODUCTION_SYNC_GUIDE.md:125-130` vs `.github/workflows/mirror-to-production.yml:3-4`

**Evidence**:
- Active probe: `gh run list --workflow=mirror-to-production.yml --limit=10` shows 5 runs total, all `event: workflow_dispatch` (manual). No `push`-triggered runs exist.
- Static read: `mirror-to-production.yml:3-4`: `on: workflow_dispatch:` — the only trigger. `PRODUCTION_SYNC_GUIDE.md:125-130`: "### Automatic Sync (Recommended) — Every time you push to the `main` branch in the development repo: ✅ Workflow detects the push..."
- Cross-reference: The guide describes automatic push-triggered sync, but the workflow only has `workflow_dispatch`. The guide's "Automatic Sync" section is misleading. This is a documentation inaccuracy, not a functional bug (the manual-only design is intentional per spec §10), so it is `noted` rather than P1.

**Expected**: The guide should describe the workflow as manual-only (consistent with spec §10 which says "Mirror is manually triggered").

**Root cause hypothesis**: The guide was written before the decision to require human review of each prod sync (and was not updated after that decision).

**Remediation owner**: Phase 4 (documentation only; no operational impact since all runs are already manual)

**Suggested fix sketch**: Update `PRODUCTION_SYNC_GUIDE.md` section "Automatic Sync (Recommended)" to "Manual Sync (Required)" and remove the statement about automatic detection on push.

---

## Prior Disposition Table

| Prior | Status | Finding(s) | Notes |
|-------|--------|-----------|-------|
| prior-A | **Confirmed** | F-DEPL-01 | Health check only pings Grafana/Prometheus/Loki HTTP endpoints; does not check datasource health, provisioning errors, or alert rule load |
| prior-B | **Confirmed** | F-DEPL-02 | Verified with live `targets.json`: all 3 active targets have `environment="monitoring"`, zero have `environment="staging"`. The jq expression returns 0 in both "all UP" and "0 targets" cases |
| prior-C | **Confirmed** | F-DEPL-05 | `paths:` filter covers `monitoring/**` and the workflow file itself; `docker-compose.staging-db-monitoring.yml` (repo root) is not listed |
| prior-D | **Confirmed** | F-DEPL-06 | `if [ ! -f ... ]` guard prevents `grafana.ini` updates after first deploy; grafana.ini.example changes are silently ignored |
| prior-E | **Partially confirmed** | F-DEPL-07 | Dead `ALERT_*` exports confirmed. Cross-reference: `grafana.ini.example` does NOT reference these env vars (so Grafana config itself is not broken), but the workflow exports them to a void and `alertmanager.yml` still references them |
| prior-F | **Confirmed** | F-DEPL-08 | `sleep 60` at line 74-75, `sleep 30` at line 250-251 — both hardcoded, no readiness polling |
| prior-H | **Confirmed** | F-DEPL-09 | Mirror strips ALL `*.md` including `monitoring/GITHUB_DEPLOYMENT.md` and `monitoring/PRODUCTION_RUNBOOK.md`, contradicting spec §9's principle |
| prior-I | **Confirmed (blind spot)** | F-DEPL-11 | No `deploy-monitoring-stack-prod.yml.example` in `production-workflows-examples/`; prod workflow not visible; marked as blind spot |

### Stage 0.4 Supplemental Findings

| Supplemental | Status | Finding(s) |
|---|---|---|
| No successful deploy runs | **Confirmed — new P0** | F-DEPL-03: Zero runs in current repo (anud18); old-repo shows 10 successful runs on jotpalch (last: 2025-11-07). Self-hosted runner not re-registered post repo migration. |
| Prod compose `scholarship_staging_network` | **Confirmed — new P0** | F-DEPL-04: Prod monitoring compose (byte-identical to dev) declares `scholarship_staging_network: external: true`. This network does not exist on prod AP-VM. Stack likely fails to restart on prod. |
| `prod-db-monitoring.yml` mirror chain | **Partially confirmed** | F-DEPL-13: File is in dev repo and preserved by mirror. Prod DB-VM has it (byte-identical per snapshot). But the alloy config SCP step in the prod workflow is a blind spot — cannot verify from this repo. |

---

## Coverage

### Files inspected

| File | Lines read | Verdict |
|------|-----------|---------|
| `.github/workflows/deploy-monitoring-stack.yml` | All 292 lines | Primary target; all priors addressed |
| `.github/workflows/mirror-to-production.yml` | All 834 lines | Primary target; strip rules, preserve logic |
| `.github/PRODUCTION_SYNC_GUIDE.md` | All 867 lines | Documentation; secret name mismatch found |
| `monitoring/GITHUB_DEPLOYMENT.md` | Lines 1-200 | Process docs; AlertManager references still present |
| `monitoring/PRODUCTION_RUNBOOK.md` | Lines 1-80 | AlertManager URL still referenced |
| `monitoring/README.md` | Lines 1-60 | Architecture diagram still shows AlertManager |
| `monitoring/docker-compose.monitoring.yml` | All 163 lines | Network reference finding |
| `monitoring/config/grafana/grafana.ini.example` | All 264 lines | No ALERT_* env vars (prior-E cross-ref) |
| `.github/production-workflows-examples/` | Directory listing | No monitoring workflow example found |
| `api-responses/deploy-pipeline/last-success-meta.json` | All | Empty `[]` — confirmed zero runs |
| `api-responses/deploy-pipeline/all-runs.json` | All | Zero runs in current repo |
| `api-responses/deploy-pipeline/mirror-runs.json` | All | 5 manual runs, all successful |
| `api-responses/deploy-pipeline/old-repo-deploy-runs.json` | All | 10 successful runs on jotpalch/scholarship-system |
| `api-responses/deploy-pipeline/prod-monitoring-compose.yml` | All | Byte-identical to dev; scholarship_staging_network confirmed |
| `api-responses/deploy-pipeline/prod-db-monitoring-compose.yml` | All | Byte-identical to dev; prod-db network correct |
| `api-responses/prometheus-loki/targets.json` | All | 0 staging targets confirmed for prior-B |

### API calls made

| Command | Result |
|---------|--------|
| `gh workflow view deploy-monitoring-stack.yml` | Total runs: 0 in current repo |
| `gh run list --workflow=deploy-monitoring-stack.yml --limit=30 --json ...` | `[]` |
| `gh run list --workflow=mirror-to-production.yml --limit=10 --json ...` | 5 manual runs, all success |

### Priors addressed

- prior-A: Confirmed → F-DEPL-01
- prior-B: Confirmed → F-DEPL-02 (cross-validated with live targets.json)
- prior-C: Confirmed → F-DEPL-05
- prior-D: Confirmed → F-DEPL-06
- prior-E: Confirmed → F-DEPL-07 (with nuance: grafana.ini.example does NOT reference ALERT_*)
- prior-F: Confirmed → F-DEPL-08
- prior-H: Confirmed → F-DEPL-09 (monitoring/*.md stripped despite spec §9)
- prior-I: Confirmed as blind spot → F-DEPL-11

---

## Cross-branch observations

These observations touch other branches' territory and are noted here only; not logged as F-DEPL findings.

1. **Branch B (Prometheus+Loki) / prior-G**: `monitoring/PRODUCTION_RUNBOOK.md` line 23 still lists AlertManager at `http://monitoring-server:9093`. This is stale documentation that should be removed as part of the AlertManager teardown in Phase 2.

2. **Branch B (Prometheus+Loki)**: `monitoring/README.md` architecture diagram (lines 27-57) still shows "AlertManager :9093" in the Monitoring Server box. Needs cleanup in Phase 2.

3. **Branch A (Grafana)**: `monitoring/GITHUB_DEPLOYMENT.md:97-102` still lists `ALERT_EMAIL_FROM`, `ALERT_SMTP_*`, and `ALERT_SLACK_WEBHOOK` as "Alert Configuration Secrets (Optional)" — these should be removed when Phase 2 wires the GitHub Issues receiver.

4. **Branch C (Alloy+CrossVM)**: `prod-db-monitoring-compose.yml` (byte-identical to dev `docker-compose.prod-db-monitoring.yml`) mounts `./monitoring/config/alloy/prod-db-vm.alloy`. If the prod DB-VM does not have the alloy config tree, Alloy starts without config. This is the mirror chain completeness issue (F-DEPL-13) but the Alloy config content itself is Branch C territory.

5. **Branch D (App Metrics)**: The `STAGING_MONITORING_SERVER_URL` secret (line 209 of deploy workflow) sets the `MONITORING_SERVER_URL` env var in the DB-VM `.env.staging-db-monitoring` file. This is the URL the Alloy agent uses to send metrics to the AP-VM Prometheus remote_write endpoint. If this secret is misconfigured, all DB-VM metrics are silently dropped — this is a Branch C/D concern.
