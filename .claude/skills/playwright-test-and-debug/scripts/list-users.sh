#!/usr/bin/env bash
# List all seeded users in the dev DB grouped by role.
# Useful when you can't remember which nycu_id is which role.
# Usage: list-users.sh [--api]   (default: query DB; --api uses mock-sso/users endpoint)
set -e

DIR="$(dirname "$0")"

if [ "$1" = "--api" ]; then
  echo "via /api/v1/auth/mock-sso/users:"
  if command -v jq >/dev/null 2>&1; then
    curl -sS http://localhost:8000/api/v1/auth/mock-sso/users \
      | jq -r '.data | sort_by(.role) | .[] | "\(.role | (. + "          ")[0:12])  \(.nycu_id)  \(.name)"'
  else
    curl -sS http://localhost:8000/api/v1/auth/mock-sso/users
  fi
else
  "$DIR/db-query.sh" "
    SELECT role, nycu_id, name, dept_name
      FROM users
     ORDER BY role, nycu_id;
  "
fi
