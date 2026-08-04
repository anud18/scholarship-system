#!/usr/bin/env bash
# Zero → roster for the multi-college PhD pipeline, run entirely inside the dev
# docker stack (no Playwright). Seeds reviewers + apps + approvals, creates and
# finalizes a ranking per college, runs matrix distribution, generates the roster,
# and verifies the roster spans every college. Idempotent — safe to re-run.
#
# Usage:
#   scripts/multicollege_seed_to_roster.sh
#
# Requires the dev stack up (docker compose -f docker-compose.dev.yml up).
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$DIR/.." && pwd)"
COMPOSE="$REPO_ROOT/docker-compose.dev.yml"

# The backend container has the app + DB session; pipe the orchestrator over stdin
# (scripts/ is not bind-mounted into the container, so we don't rely on a path).
docker compose -f "$COMPOSE" exec -T backend python - < "$DIR/multicollege_seed_to_roster.py"
