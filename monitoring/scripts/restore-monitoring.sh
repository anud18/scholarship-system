#!/bin/bash
# Restore monitoring stack from backup
# Usage: ./restore-monitoring.sh <backup_directory> [--test]

set -e

# Configuration
BACKUP_DIR="$1"
TEST_MODE=""

if [ "$2" == "--test" ]; then
    TEST_MODE="yes"
fi

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

# Validate arguments
if [ -z "$BACKUP_DIR" ]; then
    echo "Usage: $0 <backup_directory> [--test]"
    echo ""
    echo "Examples:"
    echo "  $0 /path/to/backup"
    echo "  $0 /path/to/backup --test  # Dry run mode"
    exit 1
fi

if [ ! -d "$BACKUP_DIR" ]; then
    print_error "Backup directory not found: $BACKUP_DIR"
    exit 1
fi

echo "========================================="
echo "  Monitoring Stack Restore"
echo "========================================="
echo ""
echo "Backup directory: $BACKUP_DIR"
if [ -n "$TEST_MODE" ]; then
    print_warning "TEST MODE: No changes will be made"
fi
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ] && [ -z "$TEST_MODE" ]; then
    print_error "This script must be run as root or with sudo"
    print_info "Run: sudo $0 $BACKUP_DIR"
    exit 1
fi

# Read backup metadata
if [ -f "$BACKUP_DIR/backup-metadata.json" ]; then
    print_info "Reading backup metadata..."
    BACKUP_DATE=$(jq -r '.backup_date' "$BACKUP_DIR/backup-metadata.json")
    BACKUP_HOST=$(jq -r '.hostname // "unknown"' "$BACKUP_DIR/backup-metadata.json")
    echo "  Backup date: $BACKUP_DATE"
    echo "  Source host: $BACKUP_HOST"
    echo ""
fi

# Confirm restore
if [ -z "$TEST_MODE" ]; then
    print_warning "This will STOP monitoring services and REPLACE current data!"
    print_warning "Current data will be backed up to *.old directories"
    echo ""
    read -p "Are you sure you want to continue? (yes/no): " confirm

    if [ "$confirm" != "yes" ]; then
        echo "Restore cancelled"
        exit 0
    fi
    echo ""
fi

# Step 1: Stop monitoring services
echo "========================================="
echo "  Step 1: Stop Monitoring Services"
echo "========================================="

if [ -z "$TEST_MODE" ]; then
    if [ -f "/opt/scholarship/monitoring/docker-compose.monitoring.yml" ]; then
        print_info "Stopping monitoring services..."
        cd /opt/scholarship/monitoring
        docker-compose -f docker-compose.monitoring.yml down
        print_success "Services stopped"
    else
        print_warning "docker-compose.monitoring.yml not found"
    fi
else
    print_info "[TEST] Would stop monitoring services"
fi
echo ""

# Step 2: Backup current data
echo "========================================="
echo "  Step 2: Backup Current Data"
echo "========================================="

if [ -z "$TEST_MODE" ]; then
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)

    # Backup Prometheus data
    if [ -d "/var/lib/docker/volumes/monitoring_prometheus_data" ]; then
        print_info "Backing up current Prometheus data..."
        mv /var/lib/docker/volumes/monitoring_prometheus_data \
           /var/lib/docker/volumes/monitoring_prometheus_data.old.$TIMESTAMP
        print_success "Prometheus data backed up"
    fi

    # Backup Loki data
    if [ -d "/var/lib/docker/volumes/monitoring_loki_data" ]; then
        print_info "Backing up current Loki data..."
        mv /var/lib/docker/volumes/monitoring_loki_data \
           /var/lib/docker/volumes/monitoring_loki_data.old.$TIMESTAMP
        print_success "Loki data backed up"
    fi

    # Backup config
    if [ -d "/opt/scholarship/monitoring/config" ]; then
        print_info "Backing up current configuration..."
        mv /opt/scholarship/monitoring/config \
           /opt/scholarship/monitoring/config.old.$TIMESTAMP
        print_success "Configuration backed up"
    fi
else
    print_info "[TEST] Would backup current data to *.old directories"
fi
echo ""

# Step 3: Restore Prometheus data
echo "========================================="
echo "  Step 3: Restore Prometheus Data"
echo "========================================="

if [ -d "$BACKUP_DIR/prometheus-snapshot" ] || [ -d "$BACKUP_DIR/prometheus" ]; then
    if [ -z "$TEST_MODE" ]; then
        print_info "Creating Prometheus volume..."
        docker volume create monitoring_prometheus_data

        PROM_SRC="$BACKUP_DIR/prometheus-snapshot"
        if [ ! -d "$PROM_SRC" ]; then
            PROM_SRC="$BACKUP_DIR/prometheus"
        fi

        print_info "Restoring Prometheus data..."
        cp -r "$PROM_SRC"/* /var/lib/docker/volumes/monitoring_prometheus_data/_data/

        print_info "Fixing permissions..."
        chown -R 65534:65534 /var/lib/docker/volumes/monitoring_prometheus_data/_data/

        print_success "Prometheus data restored"
    else
        print_info "[TEST] Would restore Prometheus data"
    fi
else
    print_warning "No Prometheus data found in backup"
fi
echo ""

# Step 4: Restore Loki data
echo "========================================="
echo "  Step 4: Restore Loki Data"
echo "========================================="

if [ -d "$BACKUP_DIR/loki" ]; then
    if [ -z "$TEST_MODE" ]; then
        print_info "Creating Loki volume..."
        docker volume create monitoring_loki_data

        print_info "Restoring Loki data..."
        cp -r "$BACKUP_DIR/loki"/* /var/lib/docker/volumes/monitoring_loki_data/_data/

        print_info "Fixing permissions..."
        chown -R 10001:10001 /var/lib/docker/volumes/monitoring_loki_data/_data/

        print_success "Loki data restored"
    else
        print_info "[TEST] Would restore Loki data"
    fi
else
    print_warning "No Loki data found in backup"
fi
echo ""

# Step 5: Restore configurations
echo "========================================="
echo "  Step 5: Restore Configurations"
echo "========================================="

if [ -d "$BACKUP_DIR/config" ]; then
    if [ -z "$TEST_MODE" ]; then
        print_info "Restoring monitoring configuration..."
        cp -r "$BACKUP_DIR/config" /opt/scholarship/monitoring/
        print_success "Configuration restored"
    else
        print_info "[TEST] Would restore configuration"
    fi
else
    print_warning "No configuration found in backup"
fi

if [ -f "$BACKUP_DIR/docker-compose.monitoring.yml" ]; then
    if [ -z "$TEST_MODE" ]; then
        print_info "Restoring docker-compose file..."
        cp "$BACKUP_DIR/docker-compose.monitoring.yml" /opt/scholarship/monitoring/
        print_success "docker-compose file restored"
    else
        print_info "[TEST] Would restore docker-compose file"
    fi
fi
echo ""

# Step 6: Restore Grafana dashboards
echo "========================================="
echo "  Step 6: Restore Grafana Dashboards"
echo "========================================="

if [ -f "$BACKUP_DIR/datasources.json" ]; then
    if [ -z "$TEST_MODE" ]; then
        print_info "Grafana dashboards will be restored after services start"
        print_info "Run the following after services are up:"
        echo ""
        echo "  # Restore datasources"
        echo "  curl -X POST -H 'Content-Type: application/json' \\"
        echo "    -u admin:password \\"
        echo "    -d @$BACKUP_DIR/datasources.json \\"
        echo "    http://localhost:3000/api/datasources"
        echo ""
        echo "  # Restore dashboards"
        echo "  for json in $BACKUP_DIR/*/*.json; do"
        echo "    curl -X POST -H 'Content-Type: application/json' \\"
        echo "      -u admin:password \\"
        echo "      -d @\"\$json\" \\"
        echo "      http://localhost:3000/api/dashboards/db"
        echo "  done"
        echo ""
    else
        print_info "[TEST] Would provide dashboard restore commands"
    fi
else
    print_info "No dashboard backup found (will use provisioned dashboards)"
fi
echo ""

# Step 7: Start monitoring services
echo "========================================="
echo "  Step 7: Start Monitoring Services"
echo "========================================="

if [ -z "$TEST_MODE" ]; then
    if [ -f "/opt/scholarship/monitoring/docker-compose.monitoring.yml" ]; then
        print_info "Starting monitoring services..."
        cd /opt/scholarship/monitoring
        docker-compose -f docker-compose.monitoring.yml up -d

        print_info "Waiting for services to start (30 seconds)..."
        sleep 30

        print_success "Services started"
    else
        print_error "docker-compose.monitoring.yml not found"
        exit 1
    fi
else
    print_info "[TEST] Would start monitoring services"
fi
echo ""

# Step 8: Verify restoration
echo "========================================="
echo "  Step 8: Verify Restoration"
echo "========================================="

if [ -z "$TEST_MODE" ]; then
    ERRORS=0

    # Check Grafana
    print_info "Checking Grafana..."
    if curl -sf http://localhost:3000/api/health > /dev/null 2>&1; then
        print_success "Grafana is healthy"
    else
        print_error "Grafana health check failed"
        ((ERRORS++))
    fi

    # Check Prometheus
    print_info "Checking Prometheus..."
    if curl -sf http://localhost:9090/-/healthy > /dev/null 2>&1; then
        print_success "Prometheus is healthy"

        # Check if data was restored
        METRICS=$(curl -s http://localhost:9090/api/v1/query?query=up | jq -r '.data.result | length')
        if [ "$METRICS" -gt 0 ]; then
            print_success "Prometheus has $METRICS metrics (data restored)"
        else
            print_warning "Prometheus has no metrics yet"
        fi
    else
        print_error "Prometheus health check failed"
        ((ERRORS++))
    fi

    # Check Loki
    print_info "Checking Loki..."
    if curl -sf http://localhost:3100/ready > /dev/null 2>&1; then
        print_success "Loki is ready"
    else
        print_error "Loki health check failed"
        ((ERRORS++))
    fi

    # Check AlertManager
    print_info "Checking AlertManager..."
    if curl -sf http://localhost:9093/-/healthy > /dev/null 2>&1; then
        print_success "AlertManager is healthy"
    else
        print_error "AlertManager health check failed"
        ((ERRORS++))
    fi

    echo ""
    if [ "$ERRORS" -eq 0 ]; then
        print_success "All services are healthy!"
    else
        print_error "$ERRORS service(s) failed health check"
        echo ""
        echo "Check logs with:"
        echo "  docker-compose -f /opt/scholarship/monitoring/docker-compose.monitoring.yml logs"
    fi
else
    print_info "[TEST] Would verify all services are healthy"
fi

# Summary
echo ""
echo "========================================="
echo "  Restore Complete"
echo "========================================="

if [ -z "$TEST_MODE" ]; then
    echo "Monitoring stack has been restored from backup"
    echo "Backup date: $BACKUP_DATE"
    echo "Source: $BACKUP_DIR"
    echo ""
    echo "Old data backed up to:"
    echo "  /var/lib/docker/volumes/monitoring_*_data.old.$TIMESTAMP"
    echo ""
    echo "Access monitoring:"
    echo "  Grafana: http://localhost:3000"
    echo "  Prometheus: http://localhost:9090"
else
    echo "Test mode completed successfully"
    echo "No changes were made to the system"
fi
echo ""
