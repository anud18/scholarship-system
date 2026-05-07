# Audit Probe Scripts

Read-only probes for the monitoring stack audit (Phase 1 of
`docs/superpowers/specs/2026-05-06-monitoring-stack-fix-design.md`).

## Prerequisites
- VPN tunnel `peer2` up (`wg-quick up peer2`)
- `/tmp/pw-test/auth-grafana-admin.json` Grafana session valid
- `gh` CLI authenticated to this repo

## Run order
1. `node scripts/audit/probe-grafana.js` — populates datasource health,
   dashboard JSON, screenshots.
2. `scripts/audit/probe-prom.sh targets|rules|query <expr>` — Prometheus probes
   via Grafana proxy.
3. `scripts/audit/probe-alloy-diff.sh` — Alloy file pairwise diffs.
4. `scripts/audit/probe-deploy-honesty.sh` — deploy-vs-reality.

## Output
All scripts write under `docs/superpowers/audits/working/`. JSON dumps under
`api-responses/`, screenshots under `screenshots/`. Working files
(`<branch>.md`) are written by the per-branch agents.
