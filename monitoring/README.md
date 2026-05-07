# Monitoring Infrastructure Documentation

Comprehensive monitoring system for the Scholarship System using Grafana Stack (Alloy, Loki, Prometheus, Grafana).

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Quick Start - Staging Environment](#quick-start---staging-environment)
- [Accessing Services](#accessing-services)
- [Multi-Tenancy Configuration](#multi-tenancy-configuration)
- [Alert Configuration](#alert-configuration)
- [Testing and Verification](#testing-and-verification)
- [Troubleshooting](#troubleshooting)
- [Production Deployment](#production-deployment)
- [Maintenance](#maintenance)

## Architecture Overview

### Three-Tier Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    MONITORING SERVER                         │
│  ┌────────────┐  ┌────────────┐  ┌──────────┐              │
│  │  Grafana   │  │    Loki    │  │Prometheus│              │
│  │   :3000    │  │   :3100    │  │  :9090   │              │
│  └────┬───────┘  └────────────┘  └──────────┘              │
│       │ Alerting → GitHub Issues                            │
└───────┼──────────────────────────────────────────────────────┘
                           ▲
                           │ Logs & Metrics
                           │
        ┌──────────────────┴──────────────────┐
        │                                     │
┌───────▼──────────┐              ┌───────────▼──────────┐
│ APPLICATION VM   │              │   DATABASE VM        │
│ (staging-ap-vm)  │              │  (staging-db-vm)     │
├──────────────────┤              ├──────────────────────┤
│ • Backend        │              │ • PostgreSQL         │
│ • Frontend       │              │ • Redis              │
│ • Nginx          │              │ • MinIO              │
├──────────────────┤              ├──────────────────────┤
│ MONITORING:      │              │ MONITORING:          │
│ • Grafana Alloy  │              │ • Grafana Alloy      │
│ • Node Exporter  │              │ • Node Exporter      │
│ • cAdvisor       │              │ • Postgres Exporter  │
│ • Nginx Exporter │              │ • Redis Exporter     │
└──────────────────┘              └──────────────────────┘
```

### Components

#### Monitoring Server
- **Grafana**: Visualization and dashboards (port 3000)
- **Loki**: Log aggregation with multi-tenancy (port 3100)
- **Prometheus**: Metrics storage and querying (port 9090)
- **Grafana Alerting**: Unified alert management → GitHub Issues

#### Application VM (staging-ap-vm)
- **Grafana Alloy**: Unified telemetry collector (logs + metrics)
- **Node Exporter**: System-level metrics (CPU, memory, disk, network)
- **cAdvisor**: Container runtime metrics
- **Nginx Exporter**: Web server metrics

#### Database VM (staging-db-vm)
- **Grafana Alloy**: Unified telemetry collector
- **Node Exporter**: System-level metrics
- **PostgreSQL Exporter**: Database metrics
- **Redis Exporter**: Cache metrics

## Features

### Multi-Tenancy Support
- **Staging Tenant**: 14-day log retention, 10MB ingestion rate
- **Production Tenant**: 30-day log retention, 20MB ingestion rate
- **Dev Tenant**: 7-day log retention, 5MB ingestion rate (future use)

### Comprehensive Monitoring
- ✅ System metrics (CPU, memory, disk, network)
- ✅ Container metrics (Docker runtime)
- ✅ Application logs (structured JSON logs)
- ✅ Database metrics (PostgreSQL, Redis)
- ✅ Web server metrics (Nginx)
- ✅ Object storage metrics (MinIO)

### Alerting
- ✅ 30+ pre-configured alert rules
- ✅ GitHub Issue notifications for alerts (one issue per alertname; auto-reopen on re-fire; resolved comments)
- ✅ Severity-based routing (critical, warning)
- ✅ Environment-based routing (prod, staging)
- ✅ Alert inhibition rules

### Data Retention
- **Prometheus**: 15 days (configurable)
- **Loki Staging**: 14 days
- **Loki Production**: 30 days

## Prerequisites

### System Requirements

**Monitoring Server**:
- 4 CPU cores minimum
- 8GB RAM minimum (16GB recommended)
- 100GB disk space for time-series data
- Docker and Docker Compose

**Application/Database VMs**:
- Additional 1GB RAM for monitoring services
- Additional 2GB disk space for logs and metrics cache

### Network Requirements

**Docker Networks**:
- `scholarship_staging_network` (external) - for Staging environment
- `monitoring_network` (172.30.0.0/16) - for monitoring stack

**Required Connectivity**:
- Monitoring Server → Application VM (Prometheus scraping)
- Monitoring Server → Database VM (Prometheus scraping)
- Application VM → Monitoring Server (Loki push, Prometheus remote-write)
- Database VM → Monitoring Server (Loki push, Prometheus remote-write)

### Software Versions
- Docker: 24.0+
- Docker Compose: 2.20+
- Grafana: latest
- Loki: latest
- Prometheus: latest
- Grafana Alloy: latest

## Quick Start - Staging Environment

### Step 1: Prepare Environment

```bash
# Navigate to project root
cd /path/to/scholarship-system

# Create staging network (if not exists)
docker network create scholarship_staging_network

# Copy monitoring environment file
cp monitoring/.env.monitoring.example monitoring/.env.monitoring

# Edit monitoring configuration
nano monitoring/.env.monitoring
```

**Configure `.env.monitoring`**:
```bash
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=<strong-password>
GRAFANA_ROOT_URL=http://monitoring-server:3000

# Alerting is via Grafana → GitHub Issues; no SMTP/Slack env required.
# See monitoring/PRODUCTION_RUNBOOK.md "Alerting" section.
```

### Step 2: Deploy Monitoring Server

```bash
# Start monitoring stack
cd monitoring
docker-compose -f docker-compose.monitoring.yml --env-file .env.monitoring up -d

# Verify all services are running
docker-compose -f docker-compose.monitoring.yml ps

# Check logs
docker-compose -f docker-compose.monitoring.yml logs -f
```

**Expected Output**:
```
NAME                    STATUS    PORTS
monitoring_grafana      Up        0.0.0.0:3000->3000/tcp
monitoring_loki         Up        0.0.0.0:3100->3100/tcp
monitoring_prometheus   Up        0.0.0.0:9090->9090/tcp
```

### Step 3: Deploy Staging Application VM Monitoring

```bash
# Navigate to project root
cd /path/to/scholarship-system

# Start staging application services with monitoring
docker-compose -f docker-compose.staging.yml up -d

# Verify monitoring services are running
docker-compose -f docker-compose.staging.yml ps | grep -E "(alloy|exporter|cadvisor)"
```

**Expected Services**:
- `scholarship_alloy_staging_ap`
- `node_exporter_staging_ap`
- `cadvisor_staging_ap`
- `nginx_exporter_staging_ap`

### Step 4: Deploy Staging Database VM Monitoring

```bash
# Start staging database services with monitoring
docker-compose -f docker-compose.staging-db.yml up -d

# Verify monitoring services
docker-compose -f docker-compose.staging-db.yml ps | grep -E "(alloy|exporter)"
```

**Expected Services**:
- `scholarship_alloy_staging_db`
- `node_exporter_staging_db`
- `postgres_exporter_staging`
- `redis_exporter_staging`

### Step 5: Verify Connectivity

```bash
# Check Prometheus targets
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health: .health}'

# Check Loki is receiving logs
curl -G -s "http://localhost:3100/loki/api/v1/query" \
  --data-urlencode 'query={environment="staging"}' \
  -H "X-Scope-OrgID: staging" | jq '.data.result'

```

## Accessing Services

### Grafana Dashboard

**URL**: http://localhost:3000

**Default Credentials**:
- Username: `admin`
- Password: (set in `.env.monitoring`)

**Initial Setup**:
1. Login to Grafana
2. Navigate to Configuration → Data Sources
3. Verify Prometheus and Loki datasources are connected
4. Go to Dashboards → Browse
5. Import pre-built dashboards or create custom ones

### Prometheus

**URL**: http://localhost:9090

**Usage**:
- Query metrics directly
- View active targets: http://localhost:9090/targets
- View alert rules: http://localhost:9090/alerts
- View configuration: http://localhost:9090/config

### Loki

**URL**: http://localhost:3100

**API Endpoints**:
```bash
# Query staging logs
curl -G -s "http://localhost:3100/loki/api/v1/query" \
  --data-urlencode 'query={environment="staging"}' \
  -H "X-Scope-OrgID: staging"

# Query production logs (when deployed)
curl -G -s "http://localhost:3100/loki/api/v1/query" \
  --data-urlencode 'query={environment="prod"}' \
  -H "X-Scope-OrgID: prod"

# Check Loki health
curl http://localhost:3100/ready
```

### Grafana Alerting

Alerts are managed via Grafana unified alerting and delivered to GitHub Issues.

**Where to look**:
- Firing alerts: Grafana → Alerting → Alert rules (filter by State: Firing)
- Alert history: GitHub Issues with label `monitoring-alert`
- Silence alerts: Grafana → Alerting → Silences

## Multi-Tenancy Configuration

### Tenant Structure

| Tenant | Environment | Retention | Ingestion Rate | Use Case |
|--------|-------------|-----------|----------------|----------|
| `staging` | Staging | 14 days | 10 MB/s | Development testing |
| `prod` | Production | 30 days | 20 MB/s | Production workloads |
| `dev` | Development | 7 days | 5 MB/s | Local development |

### Sending Logs with Tenant ID

**Via Grafana Alloy** (automatically configured):
```hcl
loki.write "default" {
  endpoint {
    url = "http://loki:3100/loki/api/v1/push"
    headers = {
      "X-Scope-OrgID" = "staging",  # or "prod", "dev"
    }
  }
}
```

**Via Direct API Call**:
```bash
curl -X POST "http://localhost:3100/loki/api/v1/push" \
  -H "Content-Type: application/json" \
  -H "X-Scope-OrgID: staging" \
  -d '{
    "streams": [
      {
        "stream": {"job": "test", "environment": "staging"},
        "values": [["'"$(date +%s)000000000"'", "Test log message"]]
      }
    ]
  }'
```

### Querying Logs by Tenant

**In Grafana**:
- Use "Loki (Staging)" datasource for staging logs
- Use "Loki (Production)" datasource for production logs
- Use "Loki (Dev)" datasource for dev logs

**Via API**:
```bash
# Staging logs
curl -G "http://localhost:3100/loki/api/v1/query" \
  --data-urlencode 'query={environment="staging"}' \
  -H "X-Scope-OrgID: staging"

# Production logs
curl -G "http://localhost:3100/loki/api/v1/query" \
  --data-urlencode 'query={environment="prod"}' \
  -H "X-Scope-OrgID: prod"
```

## Alert Configuration

### Alert Rules Location

```
monitoring/config/grafana/provisioning/alerting/
├── rules-system.yml      (5 rules: CPU, memory, disk, load)
├── rules-container.yml   (4 rules: container down, CPU, memory, restarts)
├── rules-database.yml    (2 rules: Redis down, Redis memory)
├── rules-monitoring.yml  (3 rules: Prometheus target down, Loki, storage)
├── contact-points.yml    (GitHub Issue webhook)
└── notification-policies.yml
```

### Alert Categories

1. **System Health**: CPU, memory, disk, load
2. **Container Health**: Container status, resource usage, restarts
3. **Database Health**: Redis connectivity and performance (PostgreSQL deferred to Phase 3)
4. **Monitoring Stack**: Prometheus targets, Loki ingestion, storage

### Alert Delivery

All alerts fire to GitHub Issues via `repository_dispatch`. The receiver workflow
`.github/workflows/monitoring-alert-issue.yml` handles:
- Creating new issues (label: `monitoring-alert`, `alert:<name>`, `env:<env>`)
- Reopening closed issues if the same alert re-fires
- Appending resolved comments

### Testing Alerts

**Test contact point via Grafana UI**:
1. Navigate to Grafana → Alerting → Contact points
2. Click `github-issue` → Test
3. Verify a GitHub Issue is created at `anud18/scholarship-system`

## Testing and Verification

### 1. Verify Prometheus Targets

```bash
# Check all targets are UP
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.health != "up") | {job: .labels.job, instance: .labels.instance, health: .health, error: .lastError}'

# Should return empty if all targets are healthy
```

### 2. Verify Loki is Receiving Logs

```bash
# Check staging logs exist
curl -G -s "http://localhost:3100/loki/api/v1/query" \
  --data-urlencode 'query={environment="staging"}' \
  --data-urlencode 'limit=5' \
  -H "X-Scope-OrgID: staging" | jq '.data.result | length'

# Should return > 0 if logs are flowing
```

### 3. Verify Grafana Datasources

```bash
# Login to Grafana
curl -X GET http://admin:admin@localhost:3000/api/datasources

# Should show Prometheus, Loki (Staging), Loki (Production), Loki (Dev)
```

### 4. Test Metrics Collection

```bash
# Query CPU usage
curl -s 'http://localhost:9090/api/v1/query?query=instance:node_cpu_utilization:rate5m' | jq '.data.result'

# Query HTTP requests
curl -s 'http://localhost:9090/api/v1/query?query=nginx:http_requests_total:rate5m' | jq '.data.result'

# Query database connections
curl -s 'http://localhost:9090/api/v1/query?query=postgres:connection_utilization:ratio' | jq '.data.result'
```

### 5. Test Log Queries

**Via LogCLI** (install first: `go install github.com/grafana/loki/cmd/logcli@latest`):

```bash
# Query staging logs
logcli query '{environment="staging"}' --addr=http://localhost:3100 --org-id=staging --limit=20

# Query with filters
logcli query '{environment="staging", job="backend"}' --addr=http://localhost:3100 --org-id=staging --limit=20

# Query for errors
logcli query '{environment="staging"} |= "error"' --addr=http://localhost:3100 --org-id=staging --limit=20
```

### 6. Health Check Commands

```bash
# All services health check script
cat > /tmp/monitoring-health-check.sh << 'EOF'
#!/bin/bash

echo "=== Monitoring Stack Health Check ==="
echo ""

echo "1. Grafana Health:"
curl -s http://localhost:3000/api/health | jq
echo ""

echo "2. Prometheus Health:"
curl -s http://localhost:9090/-/healthy
echo ""

echo "3. Loki Health:"
curl -s http://localhost:3100/ready
echo ""

echo "4. Prometheus Targets (should all be UP):"
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, instance: .labels.instance, health: .health}'
echo ""

echo "5. Grafana Alert Rules:"
curl -s -u admin:admin http://localhost:3000/api/v1/provisioning/alert-rules | jq '.[].title'
echo ""
EOF

chmod +x /tmp/monitoring-health-check.sh
/tmp/monitoring-health-check.sh
```

## Troubleshooting

### Common Issues

#### 1. Prometheus Targets Down

**Symptom**: Targets show as "DOWN" in Prometheus UI

**Diagnosis**:
```bash
# Check if exporter containers are running
docker ps | grep exporter

# Check exporter logs
docker logs node-exporter-staging-ap
docker logs nginx-exporter-staging-ap

# Test exporter endpoint directly
curl http://localhost:9100/metrics  # Node Exporter
curl http://localhost:9113/metrics  # Nginx Exporter
```

**Solution**:
- Verify Docker network connectivity
- Check if exporters are in the same network as Prometheus
- Verify firewall rules if on different hosts

#### 2. Loki Not Receiving Logs

**Symptom**: No logs visible in Grafana or API queries return empty

**Diagnosis**:
```bash
# Check Alloy logs
docker logs scholarship_alloy_staging_ap

# Check Loki logs
docker logs monitoring_loki

# Verify Loki endpoint is accessible
curl http://localhost:3100/ready

# Check ingester status
curl http://localhost:3100/ingester/ring | jq
```

**Solution**:
- Verify `X-Scope-OrgID` header is set correctly
- Check Alloy configuration syntax
- Ensure Loki has disk space: `df -h`
- Check Loki permissions: `ls -la monitoring/loki_data/`

#### 3. Grafana Datasources Not Auto-Provisioned

**Symptom**: Datasources not appearing in Grafana

**Diagnosis**:
```bash
# Check Grafana logs for provisioning errors
docker logs monitoring_grafana | grep -i provision

# Verify provisioning files exist
ls -la monitoring/config/grafana/provisioning/datasources/

# Check file permissions
stat monitoring/config/grafana/provisioning/datasources/datasources.yml
```

**Solution**:
```bash
# Restart Grafana to re-run provisioning
docker-compose -f monitoring/docker-compose.monitoring.yml restart grafana

# If still not working, manually check datasources
curl -X GET http://admin:admin@localhost:3000/api/datasources
```

#### 4. High Memory Usage

**Symptom**: Monitoring services consuming excessive memory

**Diagnosis**:
```bash
# Check memory usage
docker stats --no-stream | grep -E "(prometheus|loki|grafana)"

# Check Prometheus TSDB size
du -sh monitoring/prometheus_data/

# Check Loki index size
du -sh monitoring/loki_data/
```

**Solution**:
- Reduce retention periods in configuration
- Increase scrape intervals (reduce frequency)
- Add resource limits in docker-compose:
  ```yaml
  deploy:
    resources:
      limits:
        memory: 2G
        cpus: '1.0'
  ```

#### 5. cAdvisor Permission Denied

**Symptom**: cAdvisor fails to start or can't read metrics

**Solution**:
```bash
# Ensure cAdvisor has privileged access
# Already configured in docker-compose.staging.yml:
privileged: true
devices:
  - /dev/kmsg
```

#### 6. Network Connectivity Issues

**Symptom**: Services can't communicate across Docker networks

**Diagnosis**:
```bash
# Check network exists
docker network ls | grep scholarship_staging_network

# Inspect network
docker network inspect scholarship_staging_network

# Test connectivity from one container to another
docker exec -it monitoring_prometheus ping -c 3 node-exporter-staging-ap
```

**Solution**:
```bash
# Recreate network if needed
docker network rm scholarship_staging_network
docker network create scholarship_staging_network

# Restart all services
docker-compose -f docker-compose.staging.yml down
docker-compose -f docker-compose.staging.yml up -d
```

### Debug Commands

```bash
# View all monitoring container logs
docker-compose -f monitoring/docker-compose.monitoring.yml logs --tail=100 -f

# Check specific service logs
docker logs monitoring_prometheus --tail=100 -f
docker logs monitoring_loki --tail=100 -f

# Exec into container for debugging
docker exec -it monitoring_prometheus sh

# Check Prometheus configuration
docker exec monitoring_prometheus promtool check config /etc/prometheus/prometheus.yml

# Reload Prometheus configuration (without restart)
curl -X POST http://localhost:9090/-/reload
```

## Production Deployment

### Preparation Checklist

- [ ] Update `.env.monitoring` with production credentials
- [ ] Verify GitHub Issue webhook contact point delivers alerts (smoke test in PRODUCTION_RUNBOOK.md)
- [ ] Review and adjust resource limits for production load
- [ ] Set up backup strategy for Prometheus and Loki data
- [ ] Configure external storage (if needed)
- [ ] Update retention policies for production requirements
- [ ] Test alert routing and notifications
- [ ] Document production access credentials securely
- [ ] Set up SSL/TLS for Grafana (if exposing externally)

### Production Configuration Changes

**1. Update Grafana Alloy configs for production**:

Create new files:
- `monitoring/config/alloy/prod-ap-vm.alloy`
- `monitoring/config/alloy/prod-db-vm.alloy`

Change tenant ID from `staging` to `prod`:
```hcl
loki.write "default" {
  endpoint {
    url = "http://monitoring-server:3100/loki/api/v1/push"
    headers = {
      "X-Scope-OrgID" = "prod",  # Changed from "staging"
    }
  }
}
```

**2. Create production docker-compose files**:
- `docker-compose.prod.yml` (similar to staging)
- `docker-compose.prod-db.yml` (similar to staging-db)

Update service names and container names to use `prod` instead of `staging`.

**3. Update Prometheus scrape configs**:

Add production jobs in `monitoring/config/prometheus/prometheus.yml`:
```yaml
scrape_configs:
  - job_name: 'prod-ap-node-exporter'
    static_configs:
      - targets: ['node-exporter-prod-ap:9100']
        labels:
          environment: 'prod'
          vm: 'ap-vm'
  # ... add all other production targets
```

**4. Deploy production stack**:
```bash
# Start production application VM
docker-compose -f docker-compose.prod.yml up -d

# Start production database VM
docker-compose -f docker-compose.prod-db.yml up -d

# Verify targets in Prometheus
curl -s http://localhost:9090/api/v1/targets | grep prod
```

## Maintenance

### Regular Tasks

**Daily**:
- Monitor alert notifications
- Check Grafana dashboards for anomalies
- Review critical alerts

**Weekly**:
- Review disk space usage
- Check for missed alerts
- Verify backup integrity
- Update dashboards based on new requirements

**Monthly**:
- Review retention policies
- Clean up old data if needed
- Update monitoring stack versions
- Review and optimize alert rules

### Backup Strategy

**Grafana Dashboards**:
```bash
# Export all dashboards
curl -X GET http://admin:admin@localhost:3000/api/search | \
  jq -r '.[] | select(.type == "dash-db") | .uid' | \
  while read uid; do
    curl -X GET http://admin:admin@localhost:3000/api/dashboards/uid/$uid | \
      jq '.dashboard' > "dashboard-$uid.json"
  done
```

**Prometheus Data**:
```bash
# Backup Prometheus data directory
tar -czf prometheus-backup-$(date +%Y%m%d).tar.gz monitoring/prometheus_data/

# Restore
tar -xzf prometheus-backup-YYYYMMDD.tar.gz -C monitoring/
```

**Loki Data**:
```bash
# Backup Loki data directory
tar -czf loki-backup-$(date +%Y%m%d).tar.gz monitoring/loki_data/

# Restore
tar -xzf loki-backup-YYYYMMDD.tar.gz -C monitoring/
```

### Upgrading Components

```bash
# Pull latest images
docker-compose -f monitoring/docker-compose.monitoring.yml pull

# Restart with new images (zero-downtime not guaranteed)
docker-compose -f monitoring/docker-compose.monitoring.yml up -d

# Check logs for errors
docker-compose -f monitoring/docker-compose.monitoring.yml logs -f
```

### Scaling Considerations

**Horizontal Scaling** (future):
- Deploy multiple Prometheus instances with federation
- Deploy Loki in microservices mode
- Use external storage (S3, GCS) for Loki chunks

**Vertical Scaling** (current):
- Increase memory limits in docker-compose
- Increase disk space for time-series data
- Adjust retention periods based on disk availability

---

## Support and Resources

### Official Documentation
- [Grafana Documentation](https://grafana.com/docs/)
- [Loki Documentation](https://grafana.com/docs/loki/latest/)
- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Alloy Documentation](https://grafana.com/docs/alloy/latest/)

### Community Resources
- [Grafana Community Forums](https://community.grafana.com/)
- [Prometheus Community](https://prometheus.io/community/)

### Project-Specific Help
- GitHub Issue: #94 - Monitoring Infrastructure Implementation
- Internal Documentation: `NGINX_MONITORING_TEST.md`

---

**Last Updated**: 2025-01-11
**Maintained By**: Scholarship System Development Team
