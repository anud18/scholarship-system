#!/usr/bin/env bash
# Poll until the dev stack is healthy, with a hard timeout.
# Use after `docker compose up -d <services>` to avoid manual sleep + retry.
# Usage: wait-for-stack.sh [timeout_seconds]   (default 90)
set -e

TIMEOUT="${1:-90}"
DIR="$(dirname "$0")"
START=$(date +%s)

echo "Waiting for dev stack (timeout ${TIMEOUT}s)…"
until "$DIR/check-stack.sh" >/dev/null 2>&1; do
  NOW=$(date +%s)
  ELAPSED=$((NOW - START))
  if [ $ELAPSED -ge $TIMEOUT ]; then
    echo "TIMEOUT after ${TIMEOUT}s. Current state:" >&2
    "$DIR/check-stack.sh" || true
    exit 1
  fi
  printf '.'
  sleep 2
done
ELAPSED=$(($(date +%s) - START))
echo " ready (${ELAPSED}s)"
"$DIR/check-stack.sh"
