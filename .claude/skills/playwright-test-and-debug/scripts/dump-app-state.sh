#!/usr/bin/env bash
# For a given app_id, print the application row + reviews + audit log.
# One screenful of relevant context for debugging an application-flow issue.
# Usage: dump-app-state.sh <app_id>
# Example: dump-app-state.sh APP-114-0-00033
set -e

APP_ID="${1:-}"
if [ -z "$APP_ID" ]; then
  echo "Usage: dump-app-state.sh <app_id>" >&2
  exit 2
fi

DIR="$(dirname "$0")"

echo "=== application: $APP_ID ==="
"$DIR/db-query.sh" "
  SELECT id, app_id, user_id, status, status_name, review_stage,
         scholarship_type_id, scholarship_name, sub_scholarship_type,
         professor_id, reviewer_id, final_approver_id,
         submitted_at, reviewed_at, approved_at, decision_date, decision_reason
  FROM applications WHERE app_id = '$APP_ID';
"

echo
echo "=== reviews for $APP_ID (table: application_reviews) ==="
"$DIR/db-query.sh" "
  SELECT r.id, u.nycu_id AS reviewer, u.role AS reviewer_role,
         r.recommendation, r.comments, r.created_at
  FROM application_reviews r
  LEFT JOIN users u ON u.id = r.reviewer_id
  WHERE r.application_id = (SELECT id FROM applications WHERE app_id = '$APP_ID')
  ORDER BY r.created_at;
" 2>&1 || echo "(no reviews or schema mismatch — try: scripts/db-query.sh \"\\d application_reviews\")"

echo
echo "=== audit trail for $APP_ID (most recent 20) ==="
# audit_logs uses resource_type + resource_id (string). The app may be referenced
# by either its app_id string or its numeric id, so we check both.
"$DIR/db-query.sh" "
  SELECT created_at, action, status, description, trace_id, user_id
  FROM audit_logs
  WHERE resource_type IN ('application','applications')
    AND resource_id IN (
      '$APP_ID',
      (SELECT id::text FROM applications WHERE app_id = '$APP_ID')
    )
  ORDER BY created_at DESC
  LIMIT 20;
" || echo "(no audit rows for $APP_ID)"
