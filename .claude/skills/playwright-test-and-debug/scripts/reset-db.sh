#!/usr/bin/env bash
# Reset the dev DB to the seeded baseline. DESTRUCTIVE — drops + reseeds.
# Wraps the project's canonical scripts/reset_database.sh with a 3-second abort window.
set -e

REPO_ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
RESET_SCRIPT="$REPO_ROOT/scripts/reset_database.sh"

if [ ! -x "$RESET_SCRIPT" ]; then
  echo "ERR: project reset script not found or not executable: $RESET_SCRIPT" >&2
  exit 2
fi

cat <<EOF >&2
============================================================
WARNING: about to reset the dev database to the seeded baseline.
         This DROPS and reseeds all tables — current state will be lost.
         Press Ctrl+C within 3 seconds to abort.
============================================================
EOF

sleep 3

echo "Resetting…"
exec "$RESET_SCRIPT" "$@"
