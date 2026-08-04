#!/bin/bash
# Clear batch import data, rankings, and related records
# Usage: ./scripts/clear_import_data.sh [--dry-run]

set -euo pipefail

CONTAINER="scholarship_postgres_dev"
DB_USER="scholarship_user"
DB_NAME="scholarship_db"

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
fi

run_sql() {
    docker exec "$CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c "$1"
}

echo "=== Checking current data ==="
run_sql "
SELECT 'college_ranking_items' as table_name, count(*) as count FROM college_ranking_items
UNION ALL
SELECT 'college_rankings', count(*) FROM college_rankings
UNION ALL
SELECT 'application_reviews', count(*) FROM application_reviews
UNION ALL
SELECT 'applications (batch_import)', count(*) FROM applications WHERE import_source = 'batch_import'
UNION ALL
SELECT 'batch_imports', count(*) FROM batch_imports
ORDER BY table_name;
"

if $DRY_RUN; then
    echo "[dry-run] No data deleted."
    exit 0
fi

read -p "Delete all the above data? (y/N) " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "Aborted."
    exit 0
fi

echo "=== Deleting data ==="
run_sql "
DELETE FROM college_ranking_items;
DELETE FROM college_rankings;
DELETE FROM application_reviews;
DELETE FROM applications WHERE import_source = 'batch_import';
DELETE FROM batch_imports;
"

echo "=== Done ==="
