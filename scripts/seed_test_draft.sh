#!/bin/bash
# Seed a ready-to-submit draft PhD scholarship application.
# Usage:
#   ./scripts/seed_test_draft.sh <nycu_id>           # Seed for specific student
#   ./scripts/seed_test_draft.sh --clean <nycu_id>   # Clear all applications first
#
# Examples:
#   ./scripts/seed_test_draft.sh csphd0001
#   ./scripts/seed_test_draft.sh --clean csphd0002

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTAINER="scholarship_backend_dev"

# Parse args
CLEAN=false
NYCU_ID=""

for arg in "$@"; do
    if [ "$arg" = "--clean" ]; then
        CLEAN=true
    else
        NYCU_ID="$arg"
    fi
done

if [ -z "$NYCU_ID" ]; then
    echo "Usage: $0 [--clean] <nycu_id>"
    echo "Example: $0 csphd0001"
    exit 1
fi

if [ "$CLEAN" = true ]; then
    "$SCRIPT_DIR/clear_applications.sh"
fi

echo "🌱 Seeding draft application for $NYCU_ID..."
docker cp "$SCRIPT_DIR/seed_csphd001_draft.py" "$CONTAINER":/tmp/seed_csphd001_draft.py
docker exec -e PYTHONPATH=/app -u root "$CONTAINER" python /tmp/seed_csphd001_draft.py "$NYCU_ID"
