#!/usr/bin/env bash
# Run a SQL query against the dev Postgres. Dev creds are public (in docker-compose.dev.yml).
# Usage:
#   db-query.sh "SELECT nycu_id, role FROM users LIMIT 5;"
#   db-query.sh "$(cat query.sql)"
set -e

REPO_ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/docker-compose.dev.yml"

SQL="${1:-}"
if [ -z "$SQL" ]; then
  echo 'Usage: db-query.sh "<SQL>"' >&2
  echo 'Or:    db-query.sh "$(cat file.sql)"' >&2
  exit 2
fi

docker compose -f "$COMPOSE_FILE" exec -T postgres \
  psql -U scholarship_user -d scholarship_db -c "$SQL"
