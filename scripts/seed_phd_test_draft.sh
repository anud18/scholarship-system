#!/bin/bash
# Seed a draft PhD scholarship application with the exact form values from
# the UI test scenario (see seed_phd_test_draft.py for the field-by-field
# breakdown).
#
# Usage:
#   ./scripts/seed_phd_test_draft.sh <nycu_id>           # seed for one student
#   ./scripts/seed_phd_test_draft.sh --clean <nycu_id>   # clear all applications first
#
# Examples:
#   ./scripts/seed_phd_test_draft.sh stuphd001
#   ./scripts/seed_phd_test_draft.sh --clean csphd0001

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTAINER="scholarship_backend_dev"

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
    echo "Example: $0 stuphd001"
    exit 1
fi

if [ "$CLEAN" = true ]; then
    "$SCRIPT_DIR/clear_applications.sh" --force
fi

echo "🌱 Seeding PhD test draft for $NYCU_ID..."
docker cp "$SCRIPT_DIR/seed_phd_test_draft.py" "$CONTAINER":/tmp/seed_phd_test_draft.py
docker exec -e PYTHONPATH=/app -u root "$CONTAINER" python /tmp/seed_phd_test_draft.py "$NYCU_ID"
