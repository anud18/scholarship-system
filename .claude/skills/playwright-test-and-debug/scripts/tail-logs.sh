#!/usr/bin/env bash
# Tail backend logs from the dev stack with optional time window + grep filter.
# Usage:
#   tail-logs.sh                      # last 5m, all lines
#   tail-logs.sh 10m                  # last 10m
#   tail-logs.sh 10m "ERROR|trace_id"  # last 10m, filtered (regex)
#   tail-logs.sh 5m "" frontend        # tail frontend instead of backend
set -e

REPO_ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/docker-compose.dev.yml"

SINCE="${1:-5m}"
FILTER="${2:-}"
SERVICE="${3:-backend}"

if [ -n "$FILTER" ]; then
  docker compose -f "$COMPOSE_FILE" logs --since="$SINCE" --no-color "$SERVICE" 2>&1 | grep --line-buffered -E "$FILTER" | tail -200
else
  docker compose -f "$COMPOSE_FILE" logs --since="$SINCE" --no-color "$SERVICE" 2>&1 | tail -200
fi
