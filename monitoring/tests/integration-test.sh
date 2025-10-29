#!/bin/bash
# Integration test for monitoring stack
# Tests end-to-end log and metric collection

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuration
MONITORING_HOST="${MONITORING_HOST:-localhost}"
ENVIRONMENT="${TEST_ENVIRONMENT:-staging}"

print_success() { echo -e "${GREEN}✓${NC} $1"; }
print_error() { echo -e "${RED}✗${NC} $1"; }
print_info() { echo -e "${YELLOW}ℹ${NC} $1"; }

echo "========================================="
echo "  Monitoring Integration Test"
echo "========================================="
echo "Environment: $ENVIRONMENT"
echo "Monitoring Host: $MONITORING_HOST"
echo ""

# Test 1: Metrics Flow (Application -> Exporter -> Prometheus)
echo "=== Test 1: Metrics Collection Flow ==="
print_info "Checking if metrics are flowing from exporters to Prometheus..."

# Query for node_exporter metrics
NODE_METRICS=$(curl -s "http://$MONITORING_HOST:9090/api/v1/query?query=node_cpu_seconds_total{environment=\"$ENVIRONMENT\"}" | \
    jq -r '.data.result | length')

if [ "$NODE_METRICS" -gt 0 ]; then
    print_success "Node Exporter metrics are being collected ($NODE_METRICS series)"
else
    print_error "No Node Exporter metrics found for $ENVIRONMENT"
fi

# Query for cAdvisor metrics
CADVISOR_METRICS=$(curl -s "http://$MONITORING_HOST:9090/api/v1/query?query=container_cpu_usage_seconds_total{environment=\"$ENVIRONMENT\"}" | \
    jq -r '.data.result | length')

if [ "$CADVISOR_METRICS" -gt 0 ]; then
    print_success "cAdvisor container metrics are being collected ($CADVISOR_METRICS series)"
else
    print_error "No cAdvisor metrics found for $ENVIRONMENT"
fi

# Test 2: Logs Flow (Application -> Alloy -> Loki)
echo ""
echo "=== Test 2: Log Collection Flow ==="
print_info "Checking if logs are flowing from applications to Loki..."

# Query Loki for recent logs
RECENT_LOGS=$(curl -G -s "http://$MONITORING_HOST:3100/loki/api/v1/query" \
    --data-urlencode "query={environment=\"$ENVIRONMENT\"}" \
    --data-urlencode "limit=10" \
    --data-urlencode "time=$(date +%s)000000000" \
    -H "X-Scope-OrgID: $ENVIRONMENT" | jq -r '.data.result | length')

if [ "$RECENT_LOGS" -gt 0 ]; then
    print_success "Logs are being collected from $ENVIRONMENT ($RECENT_LOGS log streams)"
else
    print_error "No logs found in Loki for $ENVIRONMENT"
fi

# Check log diversity (different containers)
LOG_CONTAINERS=$(curl -G -s "http://$MONITORING_HOST:3100/loki/api/v1/label/container/values" \
    -H "X-Scope-OrgID: $ENVIRONMENT" | jq -r '.data | length')

if [ "$LOG_CONTAINERS" -ge 3 ]; then
    print_success "Logs from $LOG_CONTAINERS different containers"
else
    print_info "Only $LOG_CONTAINERS containers are sending logs"
fi

# Test 3: Recording Rules
echo ""
echo "=== Test 3: Recording Rules Evaluation ==="
print_info "Checking if recording rules are being evaluated..."

# Query a recording rule
RECORDING_RULE_RESULT=$(curl -s "http://$MONITORING_HOST:9090/api/v1/query?query=instance:node_cpu_utilization:rate5m{environment=\"$ENVIRONMENT\"}" | \
    jq -r '.data.result | length')

if [ "$RECORDING_RULE_RESULT" -gt 0 ]; then
    print_success "Recording rules are being evaluated ($RECORDING_RULE_RESULT series)"
else
    print_error "Recording rules are not producing results"
fi

# Test 4: Alert Rules
echo ""
echo "=== Test 4: Alert Rules Evaluation ==="
print_info "Checking if alert rules are configured and evaluating..."

ALERT_RULES=$(curl -s "http://$MONITORING_HOST:9090/api/v1/rules" | \
    jq -r "[.data.groups[].rules[] | select(.type==\"alerting\")] | length")

if [ "$ALERT_RULES" -gt 0 ]; then
    print_success "$ALERT_RULES alert rules are configured"
else
    print_error "No alert rules found"
fi

# Check for any firing alerts
FIRING_ALERTS=$(curl -s "http://$MONITORING_HOST:9090/api/v1/alerts" | \
    jq -r '[.data.alerts[] | select(.state=="firing")] | length')

if [ "$FIRING_ALERTS" -eq 0 ]; then
    print_success "No alerts are currently firing"
else
    print_info "$FIRING_ALERTS alerts are currently firing"
    curl -s "http://$MONITORING_HOST:9090/api/v1/alerts" | \
        jq -r '.data.alerts[] | select(.state=="firing") | "  - \(.labels.alertname): \(.annotations.summary)"'
fi

# Test 5: Data Retention
echo ""
echo "=== Test 5: Data Retention ==="
print_info "Checking if old data is being retained..."

# Check if we have data from 1 hour ago
ONE_HOUR_AGO=$(($(date +%s) - 3600))
OLD_DATA=$(curl -s "http://$MONITORING_HOST:9090/api/v1/query?query=up{environment=\"$ENVIRONMENT\"}&time=${ONE_HOUR_AGO}" | \
    jq -r '.data.result | length')

if [ "$OLD_DATA" -gt 0 ]; then
    print_success "Historical data is being retained (found data from 1 hour ago)"
else
    print_info "No historical data found (monitoring may have just started)"
fi

# Test 6: Multi-tenancy
echo ""
echo "=== Test 6: Multi-Tenancy Isolation ==="
print_info "Checking if tenant isolation is working..."

# Query with wrong tenant ID should return no results
WRONG_TENANT="dev"
if [ "$ENVIRONMENT" != "dev" ]; then
    ISOLATED_LOGS=$(curl -G -s "http://$MONITORING_HOST:3100/loki/api/v1/query" \
        --data-urlencode "query={environment=\"$ENVIRONMENT\"}" \
        --data-urlencode "limit=1" \
        -H "X-Scope-OrgID: $WRONG_TENANT" | jq -r '.data.result | length')

    if [ "$ISOLATED_LOGS" -eq 0 ]; then
        print_success "Tenant isolation is working correctly"
    else
        print_error "Tenant isolation is not working (cross-tenant data leak)"
    fi
fi

# Summary
echo ""
echo "========================================="
echo "  Integration Test Complete"
echo "========================================="
echo ""

# Check critical failures
if [ "$NODE_METRICS" -eq 0 ] || [ "$RECENT_LOGS" -eq 0 ]; then
    echo -e "${RED}Critical tests failed! Please check monitoring configuration.${NC}"
    exit 1
fi

echo -e "${GREEN}Integration tests passed!${NC}"
exit 0
