# R4 Audit: compose + contact-points + notification-policies

**Reviewer:** R4 (read-only)
**Date:** 2026-05-06
**Branch:** feat/monitoring-phase2
**Files audited:**
- `monitoring/docker-compose.monitoring.yml`
- `monitoring/config/grafana/provisioning/alerting/contact-points.yml`
- `monitoring/config/grafana/provisioning/alerting/notification-policies.yml`

---

## `monitoring/docker-compose.monitoring.yml`

### Check 1 — Service networks
- **grafana**: `networks: [monitoring_network, app_network]` ✅
- **loki**: `networks: [monitoring_network, app_network]` ✅
- **prometheus**: `networks: [monitoring_network, app_network]` ✅
- No service references `scholarship_staging_network`. ✅

### Check 2 — Bottom-level `networks:` block
```yaml
app_network:
  external: true
  name: ${APP_NETWORK_NAME}
```
Present and correct. ✅

### Check 3 — `monitoring_network` definition
```yaml
monitoring_network:
  driver: bridge
  ipam:
    driver: default
    config:
      - subnet: 172.30.0.0/16
```
Preserved intact. ✅

### Check 4 — `grafana.volumes`
All four mounts present:
1. `grafana_data:/var/lib/grafana` ✅
2. `./config/grafana/provisioning:/etc/grafana/provisioning:ro` ✅
3. `./config/grafana/grafana.ini:/etc/grafana/grafana.ini:ro` ✅
4. `/opt/scholarship/secrets/gh_pat:/etc/grafana/secrets/gh_pat:ro` ✅

### Check 5 — `GRAFANA_SECRET_KEY` env reference
`GF_SECURITY_SECRET_KEY: ${GRAFANA_SECRET_KEY}` is present (line 20). ✅
Compose validates cleanly; `docker compose config --quiet` emits only the expected warning:
```
WARN: "GRAFANA_SECRET_KEY" variable is not set. Defaulting to a blank string.
```
This is the accepted posture per spec §5.2.1 (session key regenerates on restart; trade-off acknowledged).

### Check 6 — `docker compose config --quiet` output
```
time=... level=warning msg="The \"GRAFANA_SECRET_KEY\" variable is not set. Defaulting to a blank string."
time=... level=warning msg="...docker-compose.monitoring.yml: `version` is obsolete"
```
Two warnings only; no errors. ✅
The `version: '3.8'` obsolete warning is cosmetic (Compose v2 ignores the field); no functional impact.

---

## `contact-points.yml`

### Check 1 — URL
`https://api.github.com/repos/anud18/scholarship-system/dispatches` ✅

### Check 2 — `authorization_credentials`
`$__file{/etc/grafana/secrets/gh_pat}` ✅  
Matches compose container mount path exactly.

### Check 3 — `authorization_scheme`
`token` ✅

### Check 4 — `disableResolveMessage`
`false` ✅ (resolved webhooks will be sent)

### Check 5 — `message:` envelope
Top-level keys: `event_type` + `client_payload` ✅  
Required by GitHub `repository_dispatch` API.

### Check 6 — `client_payload` fields and template syntax

| Field | Template | Status |
|---|---|---|
| `alertname` | `{{ (index .Alerts 0).Labels.alertname }}` | ✅ |
| `severity` | `{{ (index .Alerts 0).Labels.severity }}` | ✅ |
| `category` | `{{ (index .Alerts 0).Labels.category }}` | ✅ |
| `status` | `{{ .Status }}` | ✅ |
| `summary` | `{{ (index .Alerts 0).Annotations.summary }}` | ✅ |
| `description` | `{{ (index .Alerts 0).Annotations.description }}` | ✅ |
| `instance` | `{{ (index .Alerts 0).Labels.instance }}` | ✅ |
| `environment` | `{{ (index .Alerts 0).Labels.environment }}` | ✅ |
| `value` | `{{ (index .Alerts 0).ValueString }}` | ✅ |
| `fired_at` | `{{ (index .Alerts 0).StartsAt }}` | ✅ |
| `grafana_url` | `{{ .ExternalURL }}` | ✅ |

All 11 required fields present; all use correct Grafana unified alerting template syntax. ✅

---

## `notification-policies.yml`

### Check 1 — `receiver`
`github-issue` ✅ (matches contact-points `name: github-issue`)

### Check 2 — `group_by`
`[alertname, environment]` ✅

### Check 3 — Timing
- `group_wait: 30s` ✅
- `group_interval: 5m` ✅
- `repeat_interval: 4h` ✅

---

## Cross-reference consistency

| Point | Value | Consistent |
|---|---|---|
| Compose host path | `/opt/scholarship/secrets/gh_pat` | ✅ |
| Compose container path | `/etc/grafana/secrets/gh_pat` | ✅ |
| contact-points `authorization_credentials` | `$__file{/etc/grafana/secrets/gh_pat}` | ✅ |
| contact-points `name` | `github-issue` | ✅ |
| notification-policies `receiver` | `github-issue` | ✅ |

All three path segments agree; receiver name matches.

---

## Findings Summary

| # | Severity | Finding |
|---|---|---|
| 1 | INFO | `version: '3.8'` is obsolete in Compose v2; harmless but can be removed as cleanup. |
| 2 | INFO | `GRAFANA_SECRET_KEY` passes empty string when unset — accepted per spec §5.2.1; sessions don't survive Grafana restart. |

**No P0 or P1 issues found.** All spec §6.3, §6.2.3, §6.2.4 requirements are satisfied.
