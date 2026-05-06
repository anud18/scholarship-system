# Repo migration context (must read for synthesis pass)

## TL;DR

Deploy history is split across two GitHub repos. Treat absence of runs in
`anud18/scholarship-system` as **expected migration state**, not P0 bug.

## Facts

- **OLD repo**: `jotpalch/scholarship-system`
  - 10 successful `deploy-monitoring-stack.yml` runs between
    2025-10-12 and **2025-11-07** (~6 months ago).
  - Last successful run: `19155493587` (2025-11-07T01:43:05Z, headBranch `main`).
    Both jobs (`Deploy Monitoring Server (Staging AP-VM)` and
    `Deploy Staging DB-VM Monitoring`) reported `success`.
  - `gh run view 19155493587 --log` returns empty (logs likely expired past
    GitHub retention).

- **NEW repo (current)**: `anud18/scholarship-system`
  - **Zero** successful `deploy-monitoring-stack.yml` runs.
  - Origin pushed here at some point after 2025-11-07.
  - Per user (2026-05-06): "之前在這邊跑的 ... 但很久之前了 現在要遷移到這個 repo".
  - Migration is **in flight**; deploy workflow wiring on the new repo
    is incomplete.

## Implications for findings

1. **"No successful runs" in current repo is migration-state, NOT a P0 bug
   on its own.** It is, however, a P0 *programmatic* concern: until the deploy
   workflow runs at least once on `anud18/scholarship-system`, any monitoring
   config change committed here does not reach staging.

2. **Staging Grafana is currently running config from a 6-month-old deploy.**
   Whatever is live at `https://ss.test.nycu.edu.tw/monitoring` reflects the
   state of `monitoring/**` as of 2025-11-07 push to old repo, not whatever
   the dev repo currently shows. **All audit findings about "config in repo
   says X but stack behaves like Y"** should be re-read with this lag in
   mind: the gap may be recent commits that have not deployed yet.

3. **Phase 2 must include "wire deploy-monitoring-stack.yml on
   anud18/scholarship-system"** as the first step. Without this, Phase 2/3/4
   fixes are theoretical.

4. The prod side (separate private repo) may also have the same migration
   issue. Out of scope for this audit (blind spot).

## Recommended additional finding

### F-DEPL-MIGRATION  [P0]  Deploy workflow not yet operational on current repo

**Where**: `.github/workflows/deploy-monitoring-stack.yml` + GitHub repo
identity. Origin remote: `https://github.com/anud18/scholarship-system.git`.

**Evidence**:
- Active probe: `gh run list --workflow=deploy-monitoring-stack.yml --limit=10`
  on `anud18/scholarship-system` returns `[]`.
- Active probe: `gh -R jotpalch/scholarship-system run list ...` returns 10
  historical successful runs, last on 2025-11-07.
- Static read: workflow file at HEAD specifies `runs-on: self-hosted`,
  `environment: staging`, `branches: [main]`. None of these are wrong;
  the workflow simply hasn't been invoked on the new repo.
- Cross-reference: any monitoring config change pushed to
  `anud18/scholarship-system:main` since 2025-11-07 has not deployed.

**Expected**: After repo migration, deploy workflow should run on every push
to `main` that touches `monitoring/**`, just like it did on the old repo.

**Root cause hypothesis**: Migration completed at the source-code level (git
history transferred) but the self-hosted runner / `staging` environment
secrets / `STAGING_DB_*` SSH key secrets weren't reconfigured on the new
repo's GitHub Actions settings.

**Remediation owner**: Phase 2 (must precede all other Phase 2 fixes — they
are no-ops without working deploy).

**Suggested fix sketch**:
- Confirm the self-hosted runner is registered to `anud18/scholarship-system`.
- Reconfigure GitHub Actions secrets: `GRAFANA_ADMIN_USER`,
  `GRAFANA_ADMIN_PASSWORD`, `GRAFANA_SECRET_KEY`, `GRAFANA_ROOT_URL`,
  `STAGING_DB_SSH_KEY`, `STAGING_DB_HOST`, `STAGING_DB_USER`,
  `STAGING_MONITORING_SERVER_URL`. (Optional dead vars: `ALERT_EMAIL_*`,
  `ALERT_SLACK_WEBHOOK` — see prior-E.)
- Configure `staging` environment in repo settings.
- Trigger a `workflow_dispatch` test run; verify both jobs succeed and the
  staging Grafana picks up any pending config changes.
