#!/usr/bin/env bash
# Verify the localhost dev stack is up: backend, frontend, postgres.
# Per-service hints so you don't bring up the whole stack when only one service is down.
set -e

REPO_ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/docker-compose.dev.yml"

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "ERR: docker-compose.dev.yml not found at $COMPOSE_FILE" >&2
  exit 2
fi

backend_ok=1
frontend_ok=1
postgres_ok=1

if curl -fsS --max-time 3 http://localhost:8000/health >/dev/null 2>&1; then
  echo "OK:   backend  http://localhost:8000/health"
else
  echo "DOWN: backend  http://localhost:8000/health" >&2
  backend_ok=0
fi

if curl -fsS --max-time 3 http://localhost:3000/ >/dev/null 2>&1; then
  echo "OK:   frontend http://localhost:3000/"
else
  echo "DOWN: frontend http://localhost:3000/" >&2
  frontend_ok=0
fi

if docker compose -f "$COMPOSE_FILE" exec -T postgres pg_isready -U scholarship_user >/dev/null 2>&1; then
  echo "OK:   postgres (via docker compose exec)"
else
  echo "DOWN: postgres" >&2
  postgres_ok=0
fi

if [ $backend_ok -eq 1 ] && [ $frontend_ok -eq 1 ] && [ $postgres_ok -eq 1 ]; then
  echo "OK:   dev stack is healthy"
  exit 0
fi

# Build per-service fix hints — only suggest what's actually needed
echo >&2
down_services=()
[ $backend_ok -eq 0 ] && down_services+=(backend)
[ $frontend_ok -eq 0 ] && down_services+=(frontend)
[ $postgres_ok -eq 0 ] && down_services+=(postgres)

if [ ${#down_services[@]} -eq 1 ]; then
  echo "FIX: docker compose -f $COMPOSE_FILE up -d ${down_services[0]}" >&2
else
  echo "FIX: docker compose -f $COMPOSE_FILE up -d ${down_services[*]}" >&2
fi
echo "     then run: $(dirname "$0")/wait-for-stack.sh   (polls until healthy)" >&2
exit 1
