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
  console.log(r.body);
  await b.close();
})();
EOF
)
    NODE_PATH=$(npm root -g) node -e "$SCRIPT"
    ;;
  *) echo "usage: $0 {targets|rules|runtimeinfo|metrics|query <PromQL>}"; exit 2 ;;
esac
