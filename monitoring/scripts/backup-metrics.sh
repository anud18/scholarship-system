#!/bin/bash
# Backup Prometheus and Loki data
# Usage: ./backup-metrics.sh [output_directory]

set -e

# Configuration
BACKUP_DIR="${1:-./backups/metrics/$(date +%Y%m%d_%H%M%S)}"
PROMETHEUS_DATA_DIR="${PROMETHEUS_DATA_DIR:-/var/lib/docker/volumes/monitoring_prometheus_data/_data}"
LOKI_DATA_DIR="${LOKI_DATA_DIR:-/var/lib/docker/volumes/monitoring_loki_data/_data}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "========================================="
echo "  Monitoring Data Backup"
echo "========================================="
echo ""
echo "Backup directory: $BACKUP_DIR"
echo ""

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then
    echo -e "${YELLOW}Warning: This script should be run as root or with sudo${NC}"
    echo "Some files may not be accessible without proper permissions"
    echo ""
fi

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup Prometheus data
echo "========================================="
echo "  Backing up Prometheus TSDB"
echo "========================================="

if [ -d "$PROMETHEUS_DATA_DIR" ]; then
    echo "Source: $PROMETHEUS_DATA_DIR"

    # Get size
    PROM_SIZE=$(du -sh "$PROMETHEUS_DATA_DIR" | cut -f1)
    echo "Size: $PROM_SIZE"

    # Create snapshot via API (recommended method)
    echo -n "Creating Prometheus snapshot... "
    SNAPSHOT_NAME=$(curl -s -XPOST http://localhost:9090/api/v1/admin/tsdb/snapshot | jq -r '.data.name')

    if [ -n "$SNAPSHOT_NAME" ] && [ "$SNAPSHOT_NAME" != "null" ]; then
        echo -e "${GREEN}✓${NC}"
        echo "Snapshot name: $SNAPSHOT_NAME"

        # Copy snapshot
        SNAPSHOT_DIR="$PROMETHEUS_DATA_DIR/snapshots/$SNAPSHOT_NAME"
        if [ -d "$SNAPSHOT_DIR" ]; then
            echo -n "Copying snapshot data... "
            cp -r "$SNAPSHOT_DIR" "$BACKUP_DIR/prometheus-snapshot"
            echo -e "${GREEN}✓${NC}"

            # Clean up snapshot
            echo -n "Cleaning up Prometheus snapshot... "
            curl -s -XPOST "http://localhost:9090/api/v1/admin/tsdb/delete_series?match[]={__name__=~\".+\"}" > /dev/null
            curl -s -XPOST http://localhost:9090/api/v1/admin/tsdb/clean_tombstones > /dev/null
            rm -rf "$SNAPSHOT_DIR"
            echo -e "${GREEN}✓${NC}"
        else
            echo -e "${RED}✗${NC}"
            echo "Snapshot directory not found: $SNAPSHOT_DIR"
        fi
    else
        echo -e "${YELLOW}!${NC}"
        echo "Could not create snapshot via API, falling back to direct copy"

        # Fallback: direct copy
        echo -n "Copying Prometheus data directly... "
        cp -r "$PROMETHEUS_DATA_DIR" "$BACKUP_DIR/prometheus"
        echo -e "${GREEN}✓${NC}"
    fi
else
    echo -e "${RED}✗${NC} Prometheus data directory not found: $PROMETHEUS_DATA_DIR"
fi

# Backup Loki data
echo ""
echo "========================================="
echo "  Backing up Loki Data"
echo "========================================="

if [ -d "$LOKI_DATA_DIR" ]; then
    echo "Source: $LOKI_DATA_DIR"

    # Get size
    LOKI_SIZE=$(du -sh "$LOKI_DATA_DIR" | cut -f1)
    echo "Size: $LOKI_SIZE"

    echo -n "Copying Loki data... "
    cp -r "$LOKI_DATA_DIR" "$BACKUP_DIR/loki"
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗${NC} Loki data directory not found: $LOKI_DATA_DIR"
fi

# Backup configurations
echo ""
echo "========================================="
echo "  Backing up Configurations"
echo "========================================="

CONFIGS=(
    "/opt/scholarship/monitoring/config"
    "/opt/scholarship/monitoring/docker-compose.monitoring.yml"
)

for config in "${CONFIGS[@]}"; do
    if [ -e "$config" ]; then
        echo -n "Backing up $(basename "$config")... "
        cp -r "$config" "$BACKUP_DIR/"
        echo -e "${GREEN}✓${NC}"
    fi
done

# Create backup metadata
echo ""
echo -n "Creating backup metadata... "
cat > "$BACKUP_DIR/backup-metadata.json" << EOF
{
  "backup_date": "$(date -Iseconds)",
  "hostname": "$(hostname)",
  "prometheus_size": "$PROM_SIZE",
  "loki_size": "$LOKI_SIZE",
  "prometheus_data_dir": "$PROMETHEUS_DATA_DIR",
  "loki_data_dir": "$LOKI_DATA_DIR"
}
EOF
echo -e "${GREEN}✓${NC}"

# Create restore instructions
cat > "$BACKUP_DIR/RESTORE_INSTRUCTIONS.md" << 'EOF'
# Monitoring Data Restore Instructions

## Before Restore
1. Stop monitoring services:
   \`\`\`bash
   docker-compose -f /opt/scholarship/monitoring/docker-compose.monitoring.yml down
   \`\`\`

2. Backup current data (just in case):
   \`\`\`bash
   mv /var/lib/docker/volumes/monitoring_prometheus_data /var/lib/docker/volumes/monitoring_prometheus_data.old
   mv /var/lib/docker/volumes/monitoring_loki_data /var/lib/docker/volumes/monitoring_loki_data.old
   \`\`\`

## Restore Prometheus
\`\`\`bash
# Copy data back
cp -r [BACKUP_DIR]/prometheus-snapshot/* /var/lib/docker/volumes/monitoring_prometheus_data/_data/

# Or for direct backup
cp -r [BACKUP_DIR]/prometheus/* /var/lib/docker/volumes/monitoring_prometheus_data/_data/

# Fix permissions
chown -R 65534:65534 /var/lib/docker/volumes/monitoring_prometheus_data/_data/
\`\`\`

## Restore Loki
\`\`\`bash
# Copy data back
cp -r [BACKUP_DIR]/loki/* /var/lib/docker/volumes/monitoring_loki_data/_data/

# Fix permissions
chown -R 10001:10001 /var/lib/docker/volumes/monitoring_loki_data/_data/
\`\`\`

## Restore Configurations
\`\`\`bash
cp -r [BACKUP_DIR]/config /opt/scholarship/monitoring/
cp [BACKUP_DIR]/docker-compose.monitoring.yml /opt/scholarship/monitoring/
\`\`\`

## Start Services
\`\`\`bash
cd /opt/scholarship/monitoring
docker-compose -f docker-compose.monitoring.yml up -d
\`\`\`

## Verify
\`\`\`bash
# Check services are running
docker-compose -f docker-compose.monitoring.yml ps

# Check Prometheus data
curl http://localhost:9090/api/v1/query?query=up | jq '.data.result | length'

# Check Loki data
curl -G "http://localhost:3100/loki/api/v1/query" \\
  --data-urlencode 'query={environment="prod"}' \\
  --data-urlencode 'limit=1' \\
  -H "X-Scope-OrgID: prod"
\`\`\`
EOF

# Create compressed archive
echo ""
echo -n "Creating compressed archive... "
ARCHIVE_NAME="monitoring-backup-$(date +%Y%m%d_%H%M%S).tar.gz"

# Use parallel compression if available
if command -v pigz &> /dev/null; then
    tar -cf - -C "$BACKUP_DIR/.." "$(basename "$BACKUP_DIR")" | pigz > "$BACKUP_DIR/../$ARCHIVE_NAME"
else
    tar -czf "$BACKUP_DIR/../$ARCHIVE_NAME" -C "$BACKUP_DIR/.." "$(basename "$BACKUP_DIR")"
fi
echo -e "${GREEN}✓${NC}"

ARCHIVE_SIZE=$(du -sh "$BACKUP_DIR/../$ARCHIVE_NAME" | cut -f1)

# Summary
echo ""
echo "========================================="
echo "  Backup Complete"
echo "========================================="
echo "Backup directory: $BACKUP_DIR"
echo "Archive: $BACKUP_DIR/../$ARCHIVE_NAME"
echo "Archive size: $ARCHIVE_SIZE"
echo ""
echo "To restore from this backup, see:"
echo "  $BACKUP_DIR/RESTORE_INSTRUCTIONS.md"
echo ""

# Optional: Upload to remote storage
if [ -n "$BACKUP_REMOTE_HOST" ]; then
    echo "Uploading to remote storage..."
    scp "$BACKUP_DIR/../$ARCHIVE_NAME" "$BACKUP_REMOTE_HOST:$BACKUP_REMOTE_PATH/"
    echo -e "${GREEN}✓${NC} Uploaded to remote storage"
fi
