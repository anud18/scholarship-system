#!/usr/bin/env bash
# Seed N colleges x M PhD applications (submitted, pending college review 待學院審核)
# with complete inline student_data. Companion to staging_multicollege_seed.py;
# pipes it over stdin into the backend container (scripts/ is not bind-mounted).
# Idempotent — wipes its own STG-MOCK-% apps + stgmock_* users first, safe to re-run.
#
# Usage:
#   scripts/staging_multicollege_seed.sh [dev|staging]        # default: dev
#   PER_COLLEGE=20 COLLEGES=A,B,C,E YEAR=114 scripts/staging_multicollege_seed.sh dev
#   OPEN_REVIEW_WINDOW=1 scripts/staging_multicollege_seed.sh staging
#
#   dev     -> docker compose -f docker-compose.dev.yml exec -T backend
#   staging -> docker exec -i scholarship_backend_staging   (needs WireGuard/host access;
#              writes to the LIVE staging DB — target must be given explicitly)
#
# Env overrides (forwarded into the container): PER_COLLEGE, COLLEGES, YEAR,
# OPEN_REVIEW_WINDOW. See the .py header for what each does.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$DIR/.." && pwd)"
PY="$DIR/staging_multicollege_seed.py"
TARGET="${1:-dev}"

# Forward recognised overrides into the container (only those actually set).
ENVS=()
for v in PER_COLLEGE COLLEGES YEAR OPEN_REVIEW_WINDOW; do
  if [ -n "${!v:-}" ]; then ENVS+=(-e "$v=${!v}"); fi
done

case "$TARGET" in
  dev)
    docker compose -f "$REPO_ROOT/docker-compose.dev.yml" exec -T \
      ${ENVS[@]+"${ENVS[@]}"} backend python - < "$PY"
    ;;
  staging)
    echo "⚠️  Seeding the LIVE staging DB (scholarship_backend_staging)." >&2
    docker exec -i ${ENVS[@]+"${ENVS[@]}"} scholarship_backend_staging python - < "$PY"
    ;;
  *)
    echo "Usage: $(basename "$0") [dev|staging]" >&2
    exit 1
    ;;
esac
