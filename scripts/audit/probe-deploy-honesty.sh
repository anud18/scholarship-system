#!/usr/bin/env bash
# Compare what the deploy workflow's health-check step claims (last successful
# run) against the actual stack state right now. Surfaces dishonest health checks.
set -euo pipefail
OUT=${AUDIT_OUT_DIR:-docs/superpowers/audits/working}
mkdir -p "$OUT/api-responses/deploy-pipeline"

echo "--- last successful deploy-monitoring-stack run ---"
gh run list --workflow=deploy-monitoring-stack.yml --status=success --limit=1 \
  --json databaseId,headSha,createdAt,conclusion \
  | tee "$OUT/api-responses/deploy-pipeline/last-success-meta.json"

RUN_ID=$(jq -r '.[0].databaseId' "$OUT/api-responses/deploy-pipeline/last-success-meta.json")
gh run view "$RUN_ID" --log \
  > "$OUT/api-responses/deploy-pipeline/last-success-log.txt"

echo "--- live datasource health (now) ---"
cat "$OUT/api-responses/grafana/datasources-health.json"

echo
echo "Diff this against the workflow log to find dishonest health checks."
