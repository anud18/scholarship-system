# Production Monitoring Runbook

Quick reference guide for production monitoring operations, troubleshooting, and incident response.

## Table of Contents

- [Quick Reference](#quick-reference)
- [Health Check Commands](#health-check-commands)
- [Common Issues & Solutions](#common-issues--solutions)
- [Incident Response](#incident-response)
- [Maintenance Procedures](#maintenance-procedures)
- [Emergency Contacts](#emergency-contacts)

## Quick Reference

### Service URLs

| Service | URL | Purpose |
|---------|-----|---------|
| Grafana | http://monitoring-server:3000 | Dashboards & visualization |
| Prometheus | http://monitoring-server:9090 | Metrics & queries |
| Loki | http://monitoring-server:3100 | Log aggregation |
| AlertManager | http://monitoring-server:9093 | Alert management |

### Key Metrics

```bash
# CPU usage across all nodes
instance:node_cpu_utilization:rate5m{environment="prod"}

# Memory usage across all nodes
instance:node_memory_utilization:ratio{environment="prod"}

# HTTP error rate
rate(nginx_http_requests_total{environment="prod",status=~"5.."}[5m])

# Database connections
postgres:connection_utilization:ratio{environment="prod"}
```

### Key Log Queries

```logql
# All production errors
{environment="prod"} |= "error" | json

# Backend application errors
{environment="prod", container="backend"} |= "ERROR"

# Nginx 5xx errors
{environment="prod", container="nginx"} | json | status >= 500

# Database errors
{environment="prod", container="postgres"} |= "ERROR"
```

## Health Check Commands

### One-Line Health Check

```bash
# Check all monitoring services
curl -f http://localhost:3000/api/health && \
curl -f http://localhost:9090/-/healthy && \
curl -f http://localhost:3100/ready && \
curl -f http://localhost:9093/-/healthy && \
echo "✓ All services healthy"
```

### Detailed Health Check

```bash
# Run comprehensive test
cd /opt/scholarship/monitoring
./tests/test-monitoring-stack.sh
```

### Check Prometheus Targets

```bash
# List all targets and their health
curl -s http://localhost:9090/api/v1/targets | \
  jq -r '.data.activeTargets[] | "\(.labels.job) - \(.health)"'

# Count DOWN targets
curl -s http://localhost:9090/api/v1/targets | \
  jq '[.data.activeTargets[] | select(.health!="up")] | length'
```

### Check Log Ingestion

```bash
# Check if production logs are flowing
curl -G -s "http://localhost:3100/loki/api/v1/query" \
  --data-urlencode 'query={environment="prod"}' \
  --data-urlencode 'limit=1' \
  -H "X-Scope-OrgID: prod" | jq '.data.result | length'
```

## Common Issues & Solutions

### Issue 1: High CPU on Monitoring Server

**Symptoms**:
- Grafana sluggish
- Prometheus queries timeout
- Server load > 80%

**Diagnosis**:
```bash
# Check service resource usage
docker stats --no-stream | grep monitoring

# Check Prometheus query load
curl -s http://localhost:9090/api/v1/status/tsdb | jq '.data.seriesCountByMetricName'
```

**Solutions**:
1. Increase scrape intervals in `prometheus.yml`
2. Reduce recording rule frequency
3. Increase server resources
4. Enable Prometheus memory limit in docker-compose

```yaml
# Add to prometheus service in docker-compose.monitoring.yml
deploy:
  resources:
    limits:
      memory: 6G  # Increase from 4G
      cpus: '2.0'
```

### Issue 2: Prometheus Targets Down

**Symptoms**:
- Targets showing as "DOWN" in Prometheus UI
- Missing metrics in dashboards
- Alerts firing for target down

**Diagnosis**:
```bash
# Check which targets are down
curl -s http://localhost:9090/api/v1/targets | \
  jq -r '.data.activeTargets[] | select(.health!="up") |
         "\(.labels.job) - \(.lastError)"'

# SSH to target and check exporter
ssh prod-ap-vm "docker ps | grep exporter"
ssh prod-ap-vm "curl http://localhost:9100/metrics | head -5"
```

**Solutions**:
1. Restart exporters on target VMs:
   ```bash
   ssh prod-ap-vm "cd /opt/scholarship && docker-compose -f docker-compose.prod.yml restart node-exporter cadvisor nginx-exporter"
   ```

2. Check network connectivity:
   ```bash
   docker exec monitoring_prometheus ping -c 3 node-exporter-prod-ap
   ```

3. Verify Prometheus scrape config:
   ```bash
   docker exec monitoring_prometheus promtool check config /etc/prometheus/prometheus.yml
   ```

### Issue 3: Loki Not Receiving Logs

**Symptoms**:
- No logs in Grafana Explore
- Empty query results
- Alloy showing connection errors

**Diagnosis**:
```bash
# Check Alloy logs on application VMs
ssh prod-ap-vm "docker logs scholarship_alloy_prod_ap --tail=50 | grep -i loki"

# Check Loki ingester ring
curl -s http://localhost:3100/ingester/ring | jq

# Check Loki storage
du -sh /var/lib/docker/volumes/monitoring_loki_data/_data
```

**Solutions**:
1. Restart Alloy on target VMs:
   ```bash
   ssh prod-ap-vm "docker restart scholarship_alloy_prod_ap"
   ```

2. Check Loki has disk space:
   ```bash
   df -h | grep docker
   ```

3. Verify Loki configuration:
   ```bash
   docker logs monitoring_loki --tail=100 | grep -i error
   ```

4. Test Loki endpoint:
   ```bash
   curl -v http://localhost:3100/ready
   ```

### Issue 4: Grafana Dashboards Not Loading

**Symptoms**:
- Dashboards show "No data"
- Datasource test fails
- Query errors in browser console

**Diagnosis**:
```bash
# Test Prometheus datasource
curl -u admin:password http://localhost:3000/api/datasources | jq

# Test Prometheus from Grafana container
docker exec monitoring_grafana curl http://prometheus:9090/api/v1/query?query=up
```

**Solutions**:
1. Restart Grafana:
   ```bash
   docker-compose -f monitoring/docker-compose.monitoring.yml restart grafana
   ```

2. Verify datasource configuration:
   ```bash
   cat monitoring/config/grafana/provisioning/datasources/datasources.yml
   ```

3. Check Grafana logs:
   ```bash
   docker logs monitoring_grafana --tail=100 | grep -i error
   ```

### Issue 5: Disk Space Running Low

**Symptoms**:
- Prometheus/Loki showing storage errors
- Docker volume nearly full
- Alert: `DiskSpaceCritical`

**Diagnosis**:
```bash
# Check Docker volumes
docker system df -v

# Check specific monitoring volumes
du -sh /var/lib/docker/volumes/monitoring_*
```

**Solutions**:
1. **Immediate**: Clean up old Docker images and containers:
   ```bash
   docker system prune -a --volumes
   ```

2. **Short-term**: Reduce retention periods:
   ```yaml
   # In prometheus.yml
   --storage.tsdb.retention.time=10d  # Reduce from 15d

   # In loki-config.yml (limits.yml)
   prod:
     retention_period: 480h  # 20 days instead of 30
   ```

3. **Long-term**: Expand disk or move to external storage

### Issue 6: Alerts Not Firing

**Symptoms**:
- Expected alerts not appearing
- AlertManager shows no alerts
- Email/Slack notifications not received

**Diagnosis**:
```bash
# Check if alert rules are loaded
curl -s http://localhost:9090/api/v1/rules | jq '.data.groups[].rules[] | select(.type=="alerting") | {name:.name, state:.state}'

# Check AlertManager configuration
docker exec monitoring_alertmanager amtool check-config /etc/alertmanager/alertmanager.yml

# Test alert route
curl -X POST http://localhost:9093/api/v2/alerts -H "Content-Type: application/json" -d '[{
  "labels": {"alertname": "TestAlert", "severity": "critical"},
  "annotations": {"summary": "Test alert"}
}]'
```

**Solutions**:
1. Reload Prometheus rules:
   ```bash
   curl -X POST http://localhost:9090/-/reload
   ```

2. Check AlertManager routing:
   ```bash
   docker logs monitoring_alertmanager --tail=50
   ```

3. Verify SMTP/Slack configuration in `alertmanager.yml`

## Incident Response

### Severity Levels

| Level | Description | Response Time | Escalation |
|-------|-------------|---------------|------------|
| **P0 - Critical** | Production down, data loss | Immediate | Escalate immediately |
| **P1 - High** | Service degraded, user impact | < 15 min | Escalate if not resolved in 30min |
| **P2 - Medium** | Monitoring issues, no user impact | < 1 hour | Escalate if not resolved in 2 hours |
| **P3 - Low** | Minor issues, warnings | < 4 hours | Escalate next business day |

### Incident Response Checklist

**1. Acknowledge**
- [ ] Alert acknowledged in AlertManager
- [ ] Incident logged in tracking system
- [ ] Team notified (if P0/P1)

**2. Assess**
- [ ] Run health check: `./tests/test-monitoring-stack.sh`
- [ ] Check Grafana dashboards for anomalies
- [ ] Review recent changes (git log, deployments)
- [ ] Identify impacted services and users

**3. Mitigate**
- [ ] Apply immediate fix if known
- [ ] Restart affected services if needed
- [ ] Enable maintenance mode if necessary
- [ ] Document actions taken

**4. Resolve**
- [ ] Root cause identified
- [ ] Permanent fix applied
- [ ] Services verified healthy
- [ ] Metrics/logs confirmed normal

**5. Review**
- [ ] Post-mortem document created
- [ ] Timeline documented
- [ ] Action items assigned
- [ ] Runbook updated

### Quick Fix Commands

```bash
# Restart all monitoring services
docker-compose -f monitoring/docker-compose.monitoring.yml restart

# Restart production monitoring agents
ssh prod-ap-vm "docker-compose -f /opt/scholarship/docker-compose.prod.yml restart alloy node-exporter cadvisor nginx-exporter"
ssh prod-db-vm "docker-compose -f /opt/scholarship/docker-compose.prod-db.yml restart alloy node-exporter postgres-exporter redis-exporter"

# Force Prometheus to reload configuration
curl -X POST http://localhost:9090/-/reload

# Clear Loki cache
docker restart monitoring_loki

# Reset Grafana admin password
docker exec -it monitoring_grafana grafana-cli admin reset-admin-password newpassword
```

## Maintenance Procedures

### Weekly Tasks

```bash
# 1. Check disk usage
df -h
docker system df

# 2. Verify all targets are UP
curl -s http://localhost:9090/api/v1/targets | jq '[.data.activeTargets[] | select(.health!="up")] | length'

# 3. Review firing alerts
curl -s http://localhost:9093/api/v2/alerts | jq '.[] | select(.status.state=="active") | {name:.labels.alertname, since:.startsAt}'

# 4. Check service logs for errors
docker-compose -f monitoring/docker-compose.monitoring.yml logs --tail=100 | grep -i error
```

### Monthly Tasks

```bash
# 1. Update monitoring stack images
cd monitoring
docker-compose -f docker-compose.monitoring.yml pull
docker-compose -f docker-compose.monitoring.yml up -d

# 2. Backup Grafana dashboards
./scripts/backup-dashboards.sh

# 3. Backup Prometheus data
./scripts/backup-metrics.sh

# 4. Review and optimize alert rules
# Check for noisy alerts, adjust thresholds

# 5. Review retention policies
# Adjust based on disk usage trends

# 6. Test disaster recovery
./scripts/restore-monitoring.sh --test
```

### Quarterly Tasks

- Review and update monitoring documentation
- Audit alert notification channels
- Review access controls and rotate secrets
- Capacity planning review
- Security updates for monitoring stack

## Emergency Contacts

| Role | Name | Contact | Escalation |
|------|------|---------|------------|
| Primary On-Call | [Name] | [Phone/Email] | 24/7 |
| Secondary On-Call | [Name] | [Phone/Email] | If primary unavailable |
| Team Lead | [Name] | [Phone/Email] | For P0 incidents |
| DevOps Manager | [Name] | [Phone/Email] | Escalation point |

### Escalation Path

1. **P0/P1 Incidents**: Notify team immediately via Slack/PagerDuty
2. **Not resolved in 30 minutes**: Escalate to secondary on-call
3. **Not resolved in 1 hour**: Escalate to team lead
4. **Critical business impact**: Escalate to management

---

**Document Version**: 1.0
**Last Updated**: 2025-01-11
**Next Review**: 2025-02-11
**Owner**: DevOps Team
