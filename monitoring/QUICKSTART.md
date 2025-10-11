# Monitoring Stack - Quick Start Guide

5-minute guide to get monitoring running for Staging environment.

## Prerequisites

```bash
# Ensure Docker and Docker Compose are installed
docker --version  # Should be 24.0+
docker-compose --version  # Should be 2.20+

# Create network
docker network create scholarship_staging_network
```

## Step 1: Configure Environment (2 minutes)

```bash
cd /path/to/scholarship-system/monitoring

# Copy example config
cp .env.monitoring.example .env.monitoring

# Edit with your credentials (optional for testing)
nano .env.monitoring
```

**Minimal config for testing**:
```bash
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=admin123
```

## Step 2: Start Monitoring Server (1 minute)

```bash
# From monitoring/ directory
docker-compose -f docker-compose.monitoring.yml --env-file .env.monitoring up -d

# Wait 30 seconds for services to initialize
sleep 30

# Verify all 4 services are running
docker-compose -f docker-compose.monitoring.yml ps
```

Expected output: ✅ grafana, loki, prometheus, alertmanager all "Up"

## Step 3: Start Staging Services (2 minutes)

```bash
# Go back to project root
cd ..

# Start staging application VM with monitoring
docker-compose -f docker-compose.staging.yml up -d

# Start staging database VM with monitoring
docker-compose -f docker-compose.staging-db.yml up -d

# Verify monitoring agents are running
docker ps | grep -E "(alloy|exporter|cadvisor)"
```

Expected: 8+ containers with "alloy", "exporter", or "cadvisor" in their names

## Step 4: Verify Setup (30 seconds)

### Quick Health Check

```bash
# Check all services are healthy
curl -s http://localhost:3000/api/health && echo " ✅ Grafana OK"
curl -s http://localhost:9090/-/healthy && echo " ✅ Prometheus OK"
curl -s http://localhost:3100/ready && echo " ✅ Loki OK"
curl -s http://localhost:9093/-/healthy && echo " ✅ AlertManager OK"
```

### Check Prometheus Targets

```bash
# Should show ~8 targets, all "up"
curl -s http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health: .health}'
```

### Check Loki Logs

```bash
# Should return staging logs (may take 1-2 minutes for first logs)
curl -G -s "http://localhost:3100/loki/api/v1/query" \
  --data-urlencode 'query={environment="staging"}' \
  --data-urlencode 'limit=5' \
  -H "X-Scope-OrgID: staging" | jq '.data.result | length'
```

## Access Dashboards

### Grafana
- **URL**: http://localhost:3000
- **User**: admin
- **Pass**: (from .env.monitoring)

**What to do**:
1. Login to Grafana
2. Go to "Explore" in left menu
3. Select "Prometheus" datasource → Enter query: `up`
4. Select "Loki (Staging)" datasource → Enter query: `{environment="staging"}`

### Prometheus
- **URL**: http://localhost:9090
- **Check targets**: http://localhost:9090/targets
- **Check alerts**: http://localhost:9090/alerts

### Loki
- **URL**: http://localhost:3100
- **Test query**:
  ```bash
  curl -G "http://localhost:3100/loki/api/v1/query" \
    --data-urlencode 'query={environment="staging"}' \
    -H "X-Scope-OrgID: staging"
  ```

## Troubleshooting

### Issue: Targets showing as "DOWN"

```bash
# Check exporter containers are running
docker ps | grep exporter

# Check network connectivity
docker network inspect scholarship_staging_network

# Restart monitoring services
docker-compose -f docker-compose.staging.yml restart
```

### Issue: No logs in Loki

```bash
# Check Alloy logs
docker logs scholarship_alloy_staging_ap --tail=50

# Check Loki logs
docker logs monitoring_loki --tail=50

# Verify Loki is ready
curl http://localhost:3100/ready
```

### Issue: Can't access Grafana

```bash
# Check Grafana logs
docker logs monitoring_grafana --tail=50

# Verify port is not in use
netstat -tuln | grep 3000

# Restart Grafana
docker-compose -f monitoring/docker-compose.monitoring.yml restart grafana
```

## Next Steps

1. **Create Dashboards**: Import pre-built dashboards or create custom ones
2. **Configure Alerts**: Edit `monitoring/config/alertmanager/alertmanager.yml`
3. **Test Alerts**: Trigger a test alert to verify notification channels
4. **Production Setup**: Follow full README.md for production deployment

## Useful Commands

```bash
# View all monitoring logs
docker-compose -f monitoring/docker-compose.monitoring.yml logs -f

# Restart monitoring stack
docker-compose -f monitoring/docker-compose.monitoring.yml restart

# Stop monitoring stack
docker-compose -f monitoring/docker-compose.monitoring.yml down

# Clean up (WARNING: deletes all data)
docker-compose -f monitoring/docker-compose.monitoring.yml down -v
```

## Full Documentation

For detailed information, see [README.md](./README.md).

---

**Setup Time**: ~5 minutes
**First Metrics**: 30-60 seconds after startup
**First Logs**: 1-2 minutes after startup
