# Grafana Dashboards Guide

Complete guide to the pre-configured Grafana dashboards for the Scholarship System monitoring infrastructure.

## Table of Contents

- [Dashboard Overview](#dashboard-overview)
- [Available Dashboards](#available-dashboards)
- [Datasource Configuration](#datasource-configuration)
- [Dashboard Variables](#dashboard-variables)
- [Downloading Community Dashboards](#downloading-community-dashboards)
- [Creating Custom Dashboards](#creating-custom-dashboards)
- [Exporting and Backup](#exporting-and-backup)

## Dashboard Overview

All dashboards are automatically provisioned when Grafana starts. They are organized into folders:

```
📁 Default
  └── Scholarship System Overview

📁 System
  └── System Monitoring (Node Exporter)

📁 Application
  └── Nginx Monitoring

📁 Database
  └── (Available for community downloads)
```

### Dashboard Features

All dashboards include:
- **Environment Selector**: Switch between staging/prod/dev
- **Auto-refresh**: 30 seconds
- **Time Range**: Last 1 hour (configurable)
- **Multi-tenancy Support**: Automatically filters by environment
- **Responsive Layout**: Works on desktop and mobile

## Available Dashboards

### 1. Scholarship System Overview

**Location**: `Default` folder
**UID**: `scholarship-overview`
**File**: `monitoring/config/grafana/provisioning/dashboards/default/scholarship-system-overview.json`

**Panels**:
- Prometheus Targets Status (all services UP/DOWN)
- CPU Usage (all VMs)
- Memory Usage (all VMs)
- Nginx HTTP Requests (by status code)
- PostgreSQL Active Connections

**Variables**:
- `$environment`: staging, prod, dev
- `$vm`: All VMs or specific VM filter

**Use Case**: Quick health check of entire system

### 2. System Monitoring (Node Exporter)

**Location**: `System` folder
**UID**: `node-exporter-system`
**File**: `monitoring/config/grafana/provisioning/dashboards/system/node-exporter-system.json`

**Panels**:
- CPU Usage (per instance)
- Memory Usage (per instance)
- Disk Usage (root filesystem)
- Network Traffic (receive/transmit)
- System Load Average (1m, 5m, 15m)

**Variables**:
- `$environment`: staging, prod, dev
- `$instance`: All instances or specific instance

**Use Case**: Detailed system resource monitoring for servers

### 3. Nginx Monitoring

**Location**: `Application` folder
**UID**: `nginx-monitoring`
**File**: `monitoring/config/grafana/provisioning/dashboards/application/nginx-monitoring.json`

**Panels**:
- HTTP Requests Rate (by status: 2xx, 3xx, 4xx, 5xx)
- Request Latency (P50, P95, P99 percentiles)
- Active Connections
- HTTP Error Rate (4xx and 5xx)

**Variables**:
- `$environment`: staging, prod

**Use Case**: Monitor web server performance and identify bottlenecks

## Datasource Configuration

### Datasource UIDs

All dashboards reference datasources by UID for consistency:

| Datasource Name | UID | Type | Use Case |
|-----------------|-----|------|----------|
| Prometheus | `prometheus-uid` | prometheus | All metrics queries |
| Loki (Staging) | `loki-staging-uid` | loki | Staging logs |
| Loki (Production) | `loki-prod-uid` | loki | Production logs |
| Loki (Dev) | `loki-dev-uid` | loki | Development logs |
| AlertManager | `alertmanager-uid` | alertmanager | Alert management |

### Datasource Features

**Prometheus**:
- Query caching enabled
- Incremental querying for better performance
- 60-second query timeout

**Loki**:
- Multi-tenant with X-Scope-OrgID header
- 1000 max lines per query
- Derived fields for trace linking (future use)

**AlertManager**:
- Handles Grafana-managed alerts
- Integration with Prometheus alert rules

## Dashboard Variables

### Environment Selector

All dashboards include an environment variable:

```json
{
  "name": "environment",
  "type": "custom",
  "options": ["staging", "prod", "dev"],
  "current": {"value": "staging"}
}
```

**Usage in Queries**:
```promql
# Filter by environment
up{environment="$environment"}

# CPU usage for selected environment
100 - (avg by (instance) (irate(node_cpu_seconds_total{mode="idle",environment="$environment"}[5m])) * 100)
```

### Instance/VM Selector

Dynamic selector based on Prometheus labels:

```json
{
  "name": "instance",
  "type": "query",
  "query": "label_values(node_uname_info{environment=\"$environment\"}, instance)",
  "includeAll": true,
  "multi": true
}
```

**Benefits**:
- Automatically discovers instances
- Refreshes on environment change
- Supports multiple selection

## Downloading Community Dashboards

### Using the Download Script

We provide a script to automatically download and convert popular community dashboards:

```bash
cd monitoring/scripts
./download-community-dashboards.sh
```

**What it does**:
1. Downloads dashboards from Grafana.com
2. Replaces datasource references with our UIDs
3. Sets `editable=true` for customization
4. Removes dashboard IDs for clean provisioning
5. Organizes into appropriate folders

### Included Community Dashboards

The script downloads these popular dashboards:

| Dashboard | ID | Description | Folder |
|-----------|-----|-------------|--------|
| Node Exporter Full | 1860 | Comprehensive system metrics | system/ |
| Node Exporter for Prometheus | 15172 | Alternative system dashboard | system/ |
| cAdvisor Exporter | 14282 | Container runtime metrics | system/ |
| PostgreSQL Database | 9628 | Database monitoring | database/ |
| Redis Dashboard | 11835 | Redis cache metrics | database/ |
| MinIO Dashboard | 13659 | Object storage metrics | database/ |

### Manual Download

To download a specific dashboard manually:

```bash
# Get dashboard JSON
DASHBOARD_ID=1860
curl -s "https://grafana.com/api/dashboards/${DASHBOARD_ID}/revisions/latest/download" -o /tmp/dashboard.json

# Convert for provisioning
jq '
  walk(if type == "object" and .type == "prometheus" then .uid = "prometheus-uid" else . end) |
  .id = null |
  .editable = true
' /tmp/dashboard.json > monitoring/config/grafana/provisioning/dashboards/system/my-dashboard.json

# Restart Grafana or wait 30 seconds for auto-reload
```

## Creating Custom Dashboards

### Method 1: Grafana UI (Recommended)

1. **Create in Grafana**:
   - Go to Dashboards → New → New Dashboard
   - Add panels with queries
   - Configure visualizations
   - Add variables
   - Save dashboard

2. **Export JSON**:
   - Click dashboard settings (gear icon)
   - JSON Model tab
   - Copy JSON
   - Save to provisioning directory

3. **Clean for Provisioning**:
   ```bash
   # Remove ID and set editable
   jq '.id = null | .editable = true' dashboard-export.json > monitoring/config/grafana/provisioning/dashboards/application/my-custom-dashboard.json
   ```

4. **Reload**:
   - Wait 30 seconds for auto-reload, OR
   - Restart Grafana: `docker-compose -f monitoring/docker-compose.monitoring.yml restart grafana`

### Method 2: Edit JSON Directly

**Example: Simple CPU Dashboard**

Create `monitoring/config/grafana/provisioning/dashboards/system/cpu-simple.json`:

```json
{
  "title": "Simple CPU Monitor",
  "uid": "cpu-simple",
  "tags": ["system", "cpu"],
  "timezone": "browser",
  "time": {"from": "now-1h", "to": "now"},
  "refresh": "30s",
  "editable": true,
  "panels": [
    {
      "id": 1,
      "title": "CPU Usage",
      "type": "timeseries",
      "gridPos": {"h": 8, "w": 24, "x": 0, "y": 0},
      "datasource": {"type": "prometheus", "uid": "prometheus-uid"},
      "targets": [
        {
          "expr": "100 - (avg by (instance) (irate(node_cpu_seconds_total{mode=\"idle\",environment=\"$environment\"}[5m])) * 100)",
          "legendFormat": "{{instance}}"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "percent",
          "max": 100,
          "min": 0
        }
      }
    }
  ],
  "templating": {
    "list": [
      {
        "name": "environment",
        "type": "custom",
        "options": [
          {"text": "staging", "value": "staging"},
          {"text": "prod", "value": "prod"}
        ],
        "current": {"value": "staging"}
      }
    ]
  }
}
```

### Best Practices for Custom Dashboards

1. **Always Use UIDs**:
   - Datasource: `prometheus-uid`, `loki-staging-uid`
   - Dashboard: Unique UID like `my-dashboard-name`

2. **Include Environment Variable**:
   ```json
   "templating": {
     "list": [{
       "name": "environment",
       "type": "custom",
       "options": ["staging", "prod", "dev"]
     }]
   }
   ```

3. **Filter Queries by Environment**:
   ```promql
   metric_name{environment="$environment"}
   ```

4. **Set Appropriate Refresh**:
   - Real-time monitoring: 10s-30s
   - Historical analysis: 1m-5m
   - Overview dashboards: 30s

5. **Use Meaningful Legend Formats**:
   ```promql
   # Good
   legendFormat: "{{instance}} - {{job}}"

   # Bad
   legendFormat: "{{__name__}}"
   ```

## Exporting and Backup

### Export Single Dashboard

```bash
# Via API
DASHBOARD_UID="scholarship-overview"
curl -X GET "http://admin:admin@localhost:3000/api/dashboards/uid/$DASHBOARD_UID" | \
  jq '.dashboard' > backup-$DASHBOARD_UID.json
```

### Export All Dashboards

```bash
# Use the backup script
cd monitoring/scripts
./backup-dashboards.sh
```

**Output**:
- All dashboards exported to `backups/dashboards/YYYYMMDD_HHMMSS/`
- Organized by folder
- Includes datasources configuration
- Creates restore instructions

### Restore from Backup

```bash
# Via API
curl -X POST "http://admin:admin@localhost:3000/api/dashboards/db" \
  -H "Content-Type: application/json" \
  -d @backup-scholarship-overview.json
```

### Version Control

**Recommended**: Keep provisioned dashboards in Git:

```bash
cd /path/to/scholarship-system
git add monitoring/config/grafana/provisioning/dashboards/
git commit -m "feat(monitoring): add PostgreSQL monitoring dashboard"
git push
```

**Benefits**:
- Track dashboard changes over time
- Collaborate on dashboard improvements
- Easy rollback if dashboard breaks
- Automatic deployment via CI/CD

## Troubleshooting Dashboards

### Dashboard Not Appearing

**Check provisioning logs**:
```bash
docker logs monitoring_grafana | grep -i provision
```

**Verify file exists**:
```bash
ls -la monitoring/config/grafana/provisioning/dashboards/*/your-dashboard.json
```

**Check JSON validity**:
```bash
jq empty monitoring/config/grafana/provisioning/dashboards/system/your-dashboard.json
```

### "Datasource not found" Error

**Fix datasource UID**:
```bash
# Update all datasource UIDs in dashboard
jq 'walk(if type == "object" and .type == "prometheus" then .uid = "prometheus-uid" else . end)' \
  dashboard.json > dashboard-fixed.json
```

### Panels Show "No Data"

**Check Prometheus targets**:
```bash
curl -s http://localhost:9090/api/v1/targets | \
  jq '.data.activeTargets[] | select(.health != "up") | {job: .labels.job, health: .health}'
```

**Test query directly**:
```bash
# Test in Prometheus
curl -s 'http://localhost:9090/api/v1/query?query=up{environment="staging"}' | jq
```

### Variables Not Populating

**Check query syntax**:
```json
{
  "query": "label_values(up{environment=\"$environment\"}, instance)",
  "refresh": 1  // 1 = on dashboard load, 2 = on time range change
}
```

**Verify Prometheus has labels**:
```bash
curl -s 'http://localhost:9090/api/v1/label/instance/values' | jq
```

## Dashboard Customization Examples

### Adding a New Panel

1. Open dashboard in Grafana
2. Click "Add" → "Visualization"
3. Select datasource: Prometheus
4. Enter query:
   ```promql
   rate(nginx_http_requests_total{environment="$environment"}[5m])
   ```
5. Configure visualization type (Time series, Gauge, Stat, etc.)
6. Set panel title and description
7. Save dashboard
8. Export JSON and save to provisioning directory

### Adding Alert to Panel

1. Edit panel
2. Go to "Alert" tab
3. Create alert rule:
   ```
   WHEN last() OF query(A, 5m, now)
   IS ABOVE 80
   ```
4. Configure notification channel
5. Save

### Creating a Row

```json
{
  "type": "row",
  "collapsed": false,
  "title": "Database Metrics",
  "gridPos": {"h": 1, "w": 24, "x": 0, "y": 0},
  "panels": []
}
```

### Adding Links Between Dashboards

```json
{
  "links": [
    {
      "title": "System Dashboards",
      "type": "dashboards",
      "tags": ["system"],
      "includeVars": true,
      "keepTime": true
    }
  ]
}
```

---

## Additional Resources

### Grafana Dashboard Gallery
- Browse: https://grafana.com/grafana/dashboards/
- Filter by datasource (Prometheus, Loki)
- Check ratings and downloads
- Read comments for issues/tips

### Dashboard Best Practices
- [Official Grafana Best Practices](https://grafana.com/docs/grafana/latest/dashboards/build-dashboards/best-practices/)
- Use consistent naming conventions
- Group related panels into rows
- Add descriptions to panels
- Use appropriate visualization types

### PromQL Resources
- [Prometheus Query Basics](https://prometheus.io/docs/prometheus/latest/querying/basics/)
- [PromQL Examples](https://prometheus.io/docs/prometheus/latest/querying/examples/)
- [Recording Rules](https://prometheus.io/docs/prometheus/latest/configuration/recording_rules/)

---

**Last Updated**: 2025-01-11
**Maintained By**: Scholarship System Development Team
