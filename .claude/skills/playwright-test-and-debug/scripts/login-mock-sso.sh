#!/usr/bin/env bash
# Log in as a seeded user via mock-SSO. Prints the JSON response (use jq to extract .data.access_token).
# Usage: login-mock-sso.sh <nycu_id>
# Examples:
#   ./login-mock-sso.sh admin
#   TOKEN=$(./login-mock-sso.sh stuphd001 | jq -r .data.access_token)
set -e

NYCU_ID="${1:-}"
if [ -z "$NYCU_ID" ]; then
  echo "Usage: login-mock-sso.sh <nycu_id>" >&2
  echo "Hint:  curl -s http://localhost:8000/api/v1/auth/mock-sso/users | jq '.data[].nycu_id'" >&2
  exit 2
fi

RESP=$(curl -sS -X POST http://localhost:8000/api/v1/auth/mock-sso/login \
  -H 'Content-Type: application/json' \
  -d "{\"nycu_id\":\"$NYCU_ID\"}")

if command -v jq >/dev/null 2>&1; then
  echo "$RESP" | jq .
else
  echo "$RESP"
fi

# Exit non-zero if login failed
if command -v jq >/dev/null 2>&1; then
  SUCCESS=$(echo "$RESP" | jq -r '.success // false')
  if [ "$SUCCESS" != "true" ]; then exit 1; fi
fi
