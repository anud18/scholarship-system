#!/bin/bash
# Download community dashboards from Grafana.com and convert them for provisioning
# Usage: ./download-community-dashboards.sh

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Helper functions
print_success() { echo -e "${GREEN}✓${NC} $1"; }
print_error() { echo -e "${RED}✗${NC} $1"; }
print_warning() { echo -e "${YELLOW}⚠${NC} $1"; }
print_info() { echo -e "${YELLOW}ℹ${NC} $1"; }

echo "========================================="
echo "  Grafana Community Dashboard Downloader"
echo "========================================="
echo ""

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DASHBOARD_DIR="$SCRIPT_DIR/../config/grafana/provisioning/dashboards"

# Dashboard IDs from Grafana.com
# Format: ID:REVISION:FILENAME:FOLDER
DASHBOARDS=(
    "1860:latest:node-exporter-full.json:system"
    "15172:latest:node-exporter-prometheus.json:system"
    "14282:latest:cadvisor-exporter.json:system"
    "9628:latest:postgresql-database.json:database"
    "11835:latest:redis-dashboard.json:database"
    "13659:latest:minio-dashboard.json:database"
)

# Function to download and convert dashboard
download_dashboard() {
    local dashboard_id=$1
    local revision=$2
    local filename=$3
    local folder=$4

    echo ""
    print_info "Downloading dashboard ${dashboard_id} (${filename})..."

    local output_path="$DASHBOARD_DIR/$folder/$filename"

    # Download from Grafana.com
    local url="https://grafana.com/api/dashboards/${dashboard_id}/revisions/${revision}/download"

    if curl -sf "$url" -o "/tmp/${filename}" > /dev/null 2>&1; then
        # Convert dashboard for provisioning
        # 1. Replace datasource UIDs
        # 2. Set editable=true
        # 3. Remove id field
        jq '
            walk(
                if type == "object" then
                    if .type == "prometheus" then
                        .uid = "prometheus-uid"
                    elif .type == "loki" then
                        .uid = "loki-staging-uid"
                    elif .type == "alertmanager" then
                        .uid = "alertmanager-uid"
                    else
                        .
                    end
                else
                    .
                end
            ) |
            .id = null |
            .editable = true
        ' "/tmp/${filename}" > "$output_path"

        print_success "Downloaded and converted: $filename"
        rm "/tmp/${filename}"
        return 0
    else
        print_error "Failed to download dashboard ${dashboard_id}"
        return 1
    fi
}

# Create directories if they don't exist
mkdir -p "$DASHBOARD_DIR/system"
mkdir -p "$DASHBOARD_DIR/application"
mkdir -p "$DASHBOARD_DIR/database"

# Download dashboards
DOWNLOADED=0
FAILED=0

for dashboard_spec in "${DASHBOARDS[@]}"; do
    IFS=':' read -r id revision filename folder <<< "$dashboard_spec"

    if download_dashboard "$id" "$revision" "$filename" "$folder"; then
        ((DOWNLOADED++))
    else
        ((FAILED++))
    fi
done

echo ""
echo "========================================="
echo "  Download Complete"
echo "========================================="
echo "Downloaded: $DOWNLOADED"
if [ "$FAILED" -gt 0 ]; then
    echo -e "Failed: ${RED}$FAILED${NC}"
fi
echo ""
echo "Dashboards saved to: $DASHBOARD_DIR"
echo ""
print_info "Restart Grafana or wait 30 seconds for auto-reload"
echo "Dashboards will appear in their respective folders"
echo ""

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    print_warning "jq is not installed. Install it with: sudo apt-get install jq"
fi
