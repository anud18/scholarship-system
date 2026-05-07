#!/usr/bin/env bash
# Build a Playwright storageState JSON for a logged-in seeded user.
# The frontend (hooks/use-auth.tsx) requires BOTH auth_token AND a user blob
# (under "user" or "dev_user") in localStorage — injecting only the token
# fails silently and shows the dev login picker instead of the dashboard.
#
# Usage:
#   build-storage-state.sh <nycu_id> [out.json]
# Defaults: out=/tmp/auth-<nycu_id>.json
#
# Example:
#   STORAGE=$(./build-storage-state.sh admin)
#   NODE_PATH=$(npm root -g) node ./with-session.js "$STORAGE" http://localhost:3000
set -e

NYCU_ID="${1:-}"
OUT="${2:-/tmp/auth-${NYCU_ID}.json}"
if [ -z "$NYCU_ID" ]; then
  echo "Usage: build-storage-state.sh <nycu_id> [out.json]" >&2
  exit 2
fi

DIR="$(dirname "$0")"
RESP=$("$DIR/login-mock-sso.sh" "$NYCU_ID")

python3 - <<PY > "$OUT"
import json, sys
resp = json.loads('''$RESP''')
data = resp.get("data") or {}
token = data.get("access_token")
user = data.get("user") or {}
if not token:
    sys.stderr.write("ERR: no access_token in mock-sso response\n")
    sys.exit(1)
state = {
    "cookies": [],
    "origins": [{
        "origin": "http://localhost:3000",
        "localStorage": [
            {"name": "auth_token", "value": token},
            # Frontend's useAuth() reads either "user" or "dev_user"; provide both for safety
            {"name": "user", "value": json.dumps(user)},
            {"name": "dev_user", "value": json.dumps(user)},
        ],
    }],
}
print(json.dumps(state))
PY

echo "$OUT"
