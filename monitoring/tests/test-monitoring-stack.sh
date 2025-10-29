#!/bin/bash
# Test script for monitoring stack
# Verifies all services are healthy and collecting data

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
MONITORING_HOST="${MONITORING_HOST:-localhost}"
PROMETHEUS_PORT="${PROMETHEUS_PORT:-9090}"
LOKI_PORT="${LOKI_PORT:-3100}"
GRAFANA_PORT="${GRAFANA_PORT:-3000}"
ALERTMANAGER_PORT="${ALERTMANAGER_PORT:-9093}"

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0

# Helper functions
print_success() {
    echo -e "${GREEN}✓${NC} $1"
    ((TESTS_PASSED++))
}

print_error() {
    echo -e "${RED}✗${NC} $1"
    ((TESTS_FAILED++))
}

print_info() {
    echo -e "${YELLOW}ℹ${NC} $1"
}

# Test functions
test_service_health() {
    local service=$1
    local url=$2
    local expected_status=${3:-200}

    print_info "Testing $service health..."

    if curl -s -o /dev/null -w "%{http_code}" "$url" | grep -q "$expected_status"; then
        print_success "$service is healthy"
        return 0
    else
        print_error "$service health check failed"
        return 1
    fi
}

test_prometheus() {
    echo ""
    echo "=== Testing Prometheus ==="

    # Health check
    test_service_health "Prometheus" "http://$MONITORING_HOST:$PROMETHEUS_PORT/-/healthy"

    # Check if Prometheus is scraping targets
    print_info "Checking Prometheus targets..."
    TARGETS_UP=$(curl -s "http://$MONITORING_HOST:$PROMETHEUS_PORT/api/v1/targets" | \
        jq -r '[.data.activeTargets[] | select(.health=="up")] | length')
    TARGETS_DOWN=$(curl -s "http://$MONITORING_HOST:$PROMETHEUS_PORT/api/v1/targets" | \
        jq -r '[.data.activeTargets[] | select(.health!="up")] | length')

    if [ "$TARGETS_DOWN" -eq 0 ]; then
        print_success "All $TARGETS_UP Prometheus targets are UP"
    else
        print_error "$TARGETS_DOWN targets are DOWN (${TARGETS_UP} UP)"
        curl -s "http://$MONITORING_HOST:$PROMETHEUS_PORT/api/v1/targets" | \
            jq -r '.data.activeTargets[] | select(.health!="up") | "\(.labels.job) - \(.lastError)"'
    fi

    # Check if Prometheus is receiving metrics
    print_info "Checking if Prometheus has metrics..."
    METRIC_COUNT=$(curl -s "http://$MONITORING_HOST:$PROMETHEUS_PORT/api/v1/query?query=up" | \
        jq -r '.data.result | length')

    if [ "$METRIC_COUNT" -gt 0 ]; then
        print_success "Prometheus has $METRIC_COUNT 'up' metrics"
    else
        print_error "Prometheus has no metrics"
    fi

    # Check recording rules
    print_info "Checking recording rules..."
    RECORDING_RULES=$(curl -s "http://$MONITORING_HOST:$PROMETHEUS_PORT/api/v1/rules" | \
        jq -r '[.data.groups[].rules[] | select(.type=="recording")] | length')

    if [ "$RECORDING_RULES" -gt 0 ]; then
        print_success "Found $RECORDING_RULES recording rules"
    else
        print_error "No recording rules found"
    fi

    # Check alert rules
    print_info "Checking alert rules..."
    ALERT_RULES=$(curl -s "http://$MONITORING_HOST:$PROMETHEUS_PORT/api/v1/rules" | \
        jq -r '[.data.groups[].rules[] | select(.type=="alerting")] | length')

    if [ "$ALERT_RULES" -gt 0 ]; then
        print_success "Found $ALERT_RULES alert rules"
    else
        print_error "No alert rules found"
    fi
}

test_loki() {
    echo ""
    echo "=== Testing Loki ==="

    # Health check
    test_service_health "Loki" "http://$MONITORING_HOST:$LOKI_PORT/ready"

    # Check if Loki has staging logs
    print_info "Checking for staging logs in Loki..."
    STAGING_LOGS=$(curl -G -s "http://$MONITORING_HOST:$LOKI_PORT/loki/api/v1/query" \
        --data-urlencode 'query={environment="staging"}' \
        --data-urlencode 'limit=1' \
        -H "X-Scope-OrgID: staging" | jq -r '.data.result | length')

    if [ "$STAGING_LOGS" -gt 0 ]; then
        print_success "Loki has staging logs"
    else
        print_error "Loki has no staging logs"
    fi

    # Check if Loki has production logs (if production is deployed)
    print_info "Checking for production logs in Loki..."
    PROD_LOGS=$(curl -G -s "http://$MONITORING_HOST:$LOKI_PORT/loki/api/v1/query" \
        --data-urlencode 'query={environment="prod"}' \
        --data-urlencode 'limit=1' \
        -H "X-Scope-OrgID: prod" | jq -r '.data.result | length')

    if [ "$PROD_LOGS" -gt 0 ]; then
        print_success "Loki has production logs"
    else
        print_info "Loki has no production logs (may not be deployed yet)"
    fi

    # Check ingester ring
    print_info "Checking Loki ingester ring..."
    INGESTERS=$(curl -s "http://$MONITORING_HOST:$LOKI_PORT/ingester/ring" | jq -r '.shards[].ingesters | length')

    if [ "$INGESTERS" -gt 0 ]; then
        print_success "Loki has $INGESTERS active ingesters"
    else
        print_error "No Loki ingesters found"
    fi
}

test_grafana() {
    echo ""
    echo "=== Testing Grafana ==="

    # Health check
    test_service_health "Grafana" "http://$MONITORING_HOST:$GRAFANA_PORT/api/health"

    # Check datasources (requires auth, skip if not available)
    if [ -n "$GRAFANA_ADMIN_USER" ] && [ -n "$GRAFANA_ADMIN_PASSWORD" ]; then
        print_info "Checking Grafana datasources..."
        DATASOURCES=$(curl -s -u "$GRAFANA_ADMIN_USER:$GRAFANA_ADMIN_PASSWORD" \
            "http://$MONITORING_HOST:$GRAFANA_PORT/api/datasources" | jq -r 'length')

        if [ "$DATASOURCES" -ge 3 ]; then
            print_success "Grafana has $DATASOURCES datasources configured"
        else
            print_error "Grafana has only $DATASOURCES datasources (expected at least 3)"
        fi
    else
        print_info "Skipping Grafana datasource check (no credentials provided)"
    fi
}

test_alertmanager() {
    echo ""
    echo "=== Testing AlertManager ==="

    # Health check
    test_service_health "AlertManager" "http://$MONITORING_HOST:$ALERTMANAGER_PORT/-/healthy"

    # Check status
    print_info "Checking AlertManager status..."
    STATUS=$(curl -s "http://$MONITORING_HOST:$ALERTMANAGER_PORT/api/v2/status" | jq -r '.uptime')

    if [ -n "$STATUS" ]; then
        print_success "AlertManager uptime: $STATUS"
    else
        print_error "Unable to get AlertManager status"
    fi

    # Check active alerts
    print_info "Checking for active alerts..."
    ACTIVE_ALERTS=$(curl -s "http://$MONITORING_HOST:$ALERTMANAGER_PORT/api/v2/alerts" | jq -r 'length')

    print_info "AlertManager has $ACTIVE_ALERTS active alerts"
}

test_docker_containers() {
    echo ""
    echo "=== Testing Docker Containers ==="

    # Check if Docker is available
    if ! command -v docker &> /dev/null; then
        print_info "Docker not available (remote testing mode)"
        return
    fi

    # Check monitoring containers
    print_info "Checking monitoring containers..."
    CONTAINERS=("monitoring_grafana" "monitoring_loki" "monitoring_prometheus" "monitoring_alertmanager")

    for container in "${CONTAINERS[@]}"; do
        if docker ps --format '{{.Names}}' | grep -q "^$container$"; then
            STATUS=$(docker inspect --format='{{.State.Status}}' "$container")
            if [ "$STATUS" == "running" ]; then
                print_success "Container $container is running"
            else
                print_error "Container $container is $STATUS"
            fi
        else
            print_error "Container $container not found"
        fi
    done
}

test_network_connectivity() {
    echo ""
    echo "=== Testing Network Connectivity ==="

    # Test if monitoring services are reachable
    SERVICES=(
        "Prometheus:$MONITORING_HOST:$PROMETHEUS_PORT"
        "Loki:$MONITORING_HOST:$LOKI_PORT"
        "Grafana:$MONITORING_HOST:$GRAFANA_PORT"
        "AlertManager:$MONITORING_HOST:$ALERTMANAGER_PORT"
    )

    for service_info in "${SERVICES[@]}"; do
        IFS=':' read -r name host port <<< "$service_info"
        print_info "Testing connectivity to $name..."

        if timeout 5 bash -c "cat < /dev/null > /dev/tcp/$host/$port" 2>/dev/null; then
            print_success "$name is reachable at $host:$port"
        else
            print_error "Cannot reach $name at $host:$port"
        fi
    done
}

# Main execution
main() {
    echo "========================================="
    echo "  Monitoring Stack Test Suite"
    echo "========================================="
    echo ""
    echo "Testing monitoring stack at: $MONITORING_HOST"
    echo ""

    # Run all tests
    test_network_connectivity
    test_docker_containers
    test_prometheus
    test_loki
    test_grafana
    test_alertmanager

    # Print summary
    echo ""
    echo "========================================="
    echo "  Test Summary"
    echo "========================================="
    echo -e "Tests Passed: ${GREEN}$TESTS_PASSED${NC}"
    echo -e "Tests Failed: ${RED}$TESTS_FAILED${NC}"
    echo ""

    if [ "$TESTS_FAILED" -eq 0 ]; then
        echo -e "${GREEN}All tests passed!${NC}"
        exit 0
    else
        echo -e "${RED}Some tests failed. Please check the logs above.${NC}"
        exit 1
    fi
}

# Run main function
main
