#!/bin/bash
# Backup all Grafana dashboards to JSON files
# Usage: ./backup-dashboards.sh [output_directory]

set -e

# Configuration
GRAFANA_URL="${GRAFANA_URL:-http://localhost:3000}"
GRAFANA_USER="${GRAFANA_ADMIN_USER:-admin}"
GRAFANA_PASSWORD="${GRAFANA_ADMIN_PASSWORD:-admin}"
OUTPUT_DIR="${1:-./backups/dashboards/$(date +%Y%m%d_%H%M%S)}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "========================================="
echo "  Grafana Dashboard Backup"
echo "========================================="
echo ""
echo "Grafana URL: $GRAFANA_URL"
echo "Output directory: $OUTPUT_DIR"
echo ""

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Test Grafana connection
echo -n "Testing Grafana connection... "
if curl -sf -u "$GRAFANA_USER:$GRAFANA_PASSWORD" "$GRAFANA_URL/api/health" > /dev/null; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗${NC}"
    echo "Error: Cannot connect to Grafana at $GRAFANA_URL"
    exit 1
fi

# Get all dashboards
echo "Fetching dashboard list..."
DASHBOARDS=$(curl -s -u "$GRAFANA_USER:$GRAFANA_PASSWORD" "$GRAFANA_URL/api/search?type=dash-db")

DASHBOARD_COUNT=$(echo "$DASHBOARDS" | jq 'length')
echo "Found $DASHBOARD_COUNT dashboards"
echo ""

# Export each dashboard
EXPORTED=0
FAILED=0

echo "$DASHBOARDS" | jq -c '.[]' | while read -r dashboard; do
    TITLE=$(echo "$dashboard" | jq -r '.title')
    UID=$(echo "$dashboard" | jq -r '.uid')
    FOLDER=$(echo "$dashboard" | jq -r '.folderTitle // "General"')

    echo -n "Exporting: $TITLE (folder: $FOLDER)... "

    # Create folder structure
    FOLDER_PATH="$OUTPUT_DIR/$FOLDER"
    mkdir -p "$FOLDER_PATH"

    # Export dashboard
    DASHBOARD_JSON=$(curl -s -u "$GRAFANA_USER:$GRAFANA_PASSWORD" "$GRAFANA_URL/api/dashboards/uid/$UID")

    if echo "$DASHBOARD_JSON" | jq -e '.dashboard' > /dev/null 2>&1; then
        # Extract and save dashboard
        echo "$DASHBOARD_JSON" | jq '.dashboard' > "$FOLDER_PATH/${TITLE//[^a-zA-Z0-9_-]/_}.json"
        echo -e "${GREEN}✓${NC}"
        ((EXPORTED++))
    else
        echo -e "${RED}✗${NC}"
        echo "  Error: $(echo "$DASHBOARD_JSON" | jq -r '.message // "Unknown error"')"
        ((FAILED++))
    fi
done

# Export datasources
echo ""
echo "Exporting datasources..."
DATASOURCES=$(curl -s -u "$GRAFANA_USER:$GRAFANA_PASSWORD" "$GRAFANA_URL/api/datasources")
echo "$DATASOURCES" | jq '.' > "$OUTPUT_DIR/datasources.json"
echo -e "${GREEN}✓${NC} Datasources exported"

# Export alerting rules (if any)
echo "Exporting alert rules..."
ALERT_RULES=$(curl -s -u "$GRAFANA_USER:$GRAFANA_PASSWORD" "$GRAFANA_URL/api/v1/provisioning/alert-rules")
echo "$ALERT_RULES" | jq '.' > "$OUTPUT_DIR/alert-rules.json"
echo -e "${GREEN}✓${NC} Alert rules exported"

# Create backup metadata
cat > "$OUTPUT_DIR/backup-metadata.json" << EOF
{
  "backup_date": "$(date -Iseconds)",
  "grafana_url": "$GRAFANA_URL",
  "dashboard_count": $DASHBOARD_COUNT,
  "exported_count": $EXPORTED,
  "failed_count": $FAILED
}
EOF

# Create restore instructions
cat > "$OUTPUT_DIR/RESTORE_INSTRUCTIONS.md" << EOF
# Dashboard Restore Instructions

## Backup Information
- Date: $(date)
- Dashboards: $DASHBOARD_COUNT
- Location: $OUTPUT_DIR

## Manual Restore (via UI)
1. Login to Grafana
2. Go to Dashboards → Import
3. Upload each JSON file from this backup
4. Select appropriate folder and datasource

## Automated Restore (via API)
\`\`\`bash
cd $OUTPUT_DIR
for json_file in */*.json; do
    curl -X POST \\
      -H "Content-Type: application/json" \\
      -u admin:password \\
      -d @"\$json_file" \\
      http://localhost:3000/api/dashboards/db
done
\`\`\`

## Restore Datasources
\`\`\`bash
curl -X POST \\
  -H "Content-Type: application/json" \\
  -u admin:password \\
  -d @datasources.json \\
  http://localhost:3000/api/datasources
\`\`\`
EOF

# Create archive
echo ""
echo "Creating compressed archive..."
ARCHIVE_NAME="grafana-dashboards-$(date +%Y%m%d_%H%M%S).tar.gz"
tar -czf "$OUTPUT_DIR/../$ARCHIVE_NAME" -C "$OUTPUT_DIR/.." "$(basename "$OUTPUT_DIR")"
echo -e "${GREEN}✓${NC} Archive created: $OUTPUT_DIR/../$ARCHIVE_NAME"

# Summary
echo ""
echo "========================================="
echo "  Backup Complete"
echo "========================================="
echo "Total dashboards: $DASHBOARD_COUNT"
echo -e "Exported: ${GREEN}$EXPORTED${NC}"
if [ "$FAILED" -gt 0 ]; then
    echo -e "Failed: ${RED}$FAILED${NC}"
fi
echo "Output: $OUTPUT_DIR"
echo "Archive: $OUTPUT_DIR/../$ARCHIVE_NAME"
echo ""
