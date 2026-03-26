#!/bin/bash
# Clear all application data and related records.
# Usage: ./scripts/clear_applications.sh

set -e

DB_CONTAINER="scholarship_postgres_dev"
DB_USER="scholarship_user"
DB_NAME="scholarship_db"

echo "🗑  Clearing all application data..."

docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c "
BEGIN;

-- Related data (foreign key references to applications)
TRUNCATE payment_roster_items CASCADE;
TRUNCATE college_ranking_items CASCADE;
TRUNCATE college_ranking_items_backup CASCADE;
TRUNCATE document_requests CASCADE;
TRUNCATE scheduled_emails CASCADE;
DELETE FROM email_history WHERE application_id IS NOT NULL;

-- Application direct children
TRUNCATE application_reviews CASCADE;
TRUNCATE application_review_items CASCADE;
TRUNCATE application_files CASCADE;

-- Applications
TRUNCATE applications CASCADE;

-- Sequence counters
TRUNCATE application_sequences CASCADE;

COMMIT;
"

echo "✅ All application data cleared."
