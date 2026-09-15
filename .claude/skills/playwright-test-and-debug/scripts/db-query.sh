#!/usr/bin/env bash
# Run a SQL query against the dev Postgres. Dev creds are public (in docker-compose.dev.yml).
# Usage:
#   db-query.sh "SELECT nycu_id, role FROM users LIMIT 5;"
#   db-query.sh "$(cat query.sql)"
set -e

# DB_NAME lets a worktree/e2e run point at an isolated clone (default: the dev DB).
DB_NAME="${DB_NAME:-scholarship_db}"

SQL="${1:-}"
if [ -z "$SQL" ]; then
  echo 'Usage: db-query.sh "<SQL>"' >&2
  echo 'Or:    db-query.sh "$(cat file.sql)"' >&2
  exit 2
fi

# Fixed container_name (docker-compose.dev.yml) — independent of which compose
# project / worktree brought the stack up.
docker exec -i scholarship_postgres_dev \
  psql -U scholarship_user -d "$DB_NAME" -c "$SQL"
