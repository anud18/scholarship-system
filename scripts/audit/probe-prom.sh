#!/usr/bin/env bash
# Read-only Prometheus probe via the Grafana datasource proxy (we don't have
# direct localhost:9090 access; Grafana proxies on our behalf).
# Usage: probe-prom.sh <PromQL or special>
#   special: targets | rules | runtimeinfo | metrics
set -euo pipefail
NYCU_DIR=${NYCU_DIR:-/tmp/pw-test}
OUT=${AUDIT_OUT_DIR:-docs/superpowers/audits/working}
STATE="$NYCU_DIR/auth-grafana-admin.json"
BASE='https://ss.test.nycu.edu.tw/monitoring'

# Quick freshness probe: if the Grafana storage state is older than 8 hours,
# warn the operator (sessions typically expire around this window).
STATE_AGE_S=$(( $(date +%s) - $(stat -f %m "$STATE" 2>/dev/null || stat -c %Y "$STATE" 2>/dev/null) ))
if [ "$STATE_AGE_S" -gt 28800 ]; then
  echo "WARN: Grafana session is $((STATE_AGE_S / 3600))h old; consider refreshing via /tmp/pw-test/grafana-login.js" >&2
fi

need() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 1; }; }
need node; need jq

# Find Prometheus datasource UID
PROM_UID=$(jq -r '.[] | select(.type=="prometheus") | .uid' \
  "$OUT/api-responses/grafana/datasources-health.json" 2>/dev/null || true)
if [ -z "$PROM_UID" ]; then
  echo "Run probe-grafana.js first to populate datasources-health.json" >&2
  exit 1
fi

case "${1:-}" in
  targets|rules|runtimeinfo|metrics)
    EP="$1"
    SCRIPT=$(cat <<EOF
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const c = await b.newContext({ ignoreHTTPSErrors: true, storageState: '$STATE' });
  const p = await c.newPage();
  await p.goto('$BASE/');
  const r = await p.evaluate(async () => {
    const x = await fetch('/monitoring/api/datasources/proxy/uid/$PROM_UID/api/v1/$EP', { credentials: 'include' });
    return { http: x.status, body: await x.text() };
  });
  if (r.http === 401 || r.http === 403) {
    console.error('ERROR: Grafana session expired or unauthorized (HTTP ' + r.http + ').');
    console.error('Re-run /tmp/pw-test/grafana-login.js to refresh session.');
    process.exit(1);
  }
  console.log(r.body);
  await b.close();
})();
EOF
)
    NODE_PATH=$(npm root -g) node -e "$SCRIPT"
    ;;
  query)
    Q="$2"
    SCRIPT=$(cat <<EOF
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch();
  const c = await b.newContext({ ignoreHTTPSErrors: true, storageState: '$STATE' });
  const p = await c.newPage();
  await p.goto('$BASE/');
  const r = await p.evaluate(async (q) => {
    const u = '/monitoring/api/datasources/proxy/uid/$PROM_UID/api/v1/query?query=' + encodeURIComponent(q);
    const x = await fetch(u, { credentials: 'include' });
    return { http: x.status, body: await x.text() };
  }, '$Q');
  if (r.http === 401 || r.http === 403) {
    console.error('ERROR: Grafana session expired or unauthorized (HTTP ' + r.http + ').');
    console.error('Re-run /tmp/pw-test/grafana-login.js to refresh session.');
    process.exit(1);
  }
  console.log(r.body);
  await b.close();
})();
EOF
)
    NODE_PATH=$(npm root -g) node -e "$SCRIPT"
    ;;
  *) echo "usage: $0 {targets|rules|runtimeinfo|metrics|query <PromQL>}"; exit 2 ;;
esac
