# R5 Audit — Alloy DB-VM Files (Phase 2 / Tasks 14–15)

**Auditor:** R5  
**Date:** 2026-05-06  
**Branch:** `feat/monitoring-phase2`  
**Files reviewed:**  
- `monitoring/config/alloy/staging-db-vm.alloy`  
- `monitoring/config/alloy/prod-db-vm.alloy`  
**Spec reference:** `docs/superpowers/specs/2026-05-06-monitoring-stack-fix-phase2-design.md` §6.5

---

## 1. Structural Verification — `staging-db-vm.alloy`

### 1.1 `prometheus.scrape "node_exporter"` (lines 87–92)

| Check | Expected | Actual | Result |
|---|---|---|---|
| target `__address__` | `node-exporter:9100` | `node-exporter:9100` | PASS |
| `job_name` | `"node"` | `"node"` | PASS |
| `scrape_interval` | `"15s"` | `"15s"` | PASS |
| `forward_to` | `[prometheus.relabel.add_labels.receiver]` | `[prometheus.relabel.add_labels.receiver]` | PASS |

### 1.2 `prometheus.scrape "postgres_exporter"` (lines 94–99)

| Check | Expected | Actual | Result |
|---|---|---|---|
| target `__address__` | `postgres-exporter:9187` | `postgres-exporter:9187` | PASS |
| `job_name` | `"postgres"` | `"postgres"` | PASS |
| `scrape_interval` | `"15s"` | `"15s"` | PASS |
| `forward_to` | `[prometheus.relabel.add_labels.receiver]` | `[prometheus.relabel.add_labels.receiver]` | PASS |

### 1.3 `prometheus.relabel "add_labels"` (lines 101–111)

| Check | Expected | Actual | Result |
|---|---|---|---|
| `forward_to` | `[prometheus.remote_write.default.receiver]` | `[prometheus.remote_write.default.receiver]` | PASS |
| rule 1 `target_label` | `"environment"` | `"environment"` | PASS |
| rule 1 `replacement` | `"staging"` | `"staging"` | PASS |
| rule 2 `target_label` | `"vm"` | `"vm"` | PASS |
| rule 2 `replacement` | `"db-vm"` | `"db-vm"` | PASS |

### 1.4 `prometheus.remote_write "default"` (lines 113–117)

| Check | Expected | Actual | Result |
|---|---|---|---|
| `url` | `env("MONITORING_SERVER_URL") + ":9090/api/v1/write"` | `env("MONITORING_SERVER_URL") + ":9090/api/v1/write"` | PASS |

### 1.5 Old "METRICS PIPELINE - PULL MODE" comment block removed

The spec called for removing a stale "PULL MODE" comment block. The file contains only the new "PUSH MODE" comment header. No "PULL MODE" text is present. **PASS** (the old block existed as a stub prior to Phase 2 and has been correctly replaced).

### 1.6 Pre-existing Logging Pipeline — preserved

| Block | Present | Correct |
|---|---|---|
| `discovery.docker "containers"` | Yes | PASS |
| `loki.relabel "container_labels"` | Yes — includes slash-strip rule (`regex = "^/(.*)"`, `replacement = "$1"`) | PASS |
| `loki.source.docker "containers"` | Yes | PASS |
| `loki.process "add_labels"` | Yes — `environment = "staging"`, `vm = "db-vm"` | PASS |
| `loki.write "default"` | Yes — `url = env("MONITORING_SERVER_URL") + ":3100/loki/api/v1/push"`, `X-Scope-OrgID = "staging"` | PASS |
| `prometheus.exporter.self "alloy"` | Yes (self-monitoring block) | PASS |

---

## 2. Structural Verification — `prod-db-vm.alloy`

All Phase 2 blocks are structurally identical to staging, with `replacement = "prod"` for environment.

| Check | Expected | Actual | Result |
|---|---|---|---|
| `node_exporter` target | `node-exporter:9100` | `node-exporter:9100` | PASS |
| `postgres_exporter` target | `postgres-exporter:9187` | `postgres-exporter:9187` | PASS |
| Both job_names | `"node"`, `"postgres"` | `"node"`, `"postgres"` | PASS |
| Both scrape_intervals | `"15s"` | `"15s"` | PASS |
| relabel `environment` replacement | `"prod"` | `"prod"` | PASS |
| relabel `vm` replacement | `"db-vm"` | `"db-vm"` | PASS |
| remote_write URL | `env("MONITORING_SERVER_URL") + ":9090/api/v1/write"` | `env("MONITORING_SERVER_URL") + ":9090/api/v1/write"` | PASS |
| `loki.write` URL | `env("MONITORING_SERVER_URL") + ":3100/loki/api/v1/push"` | `env("MONITORING_SERVER_URL") + ":3100/loki/api/v1/push"` | PASS |
| `loki.write` `X-Scope-OrgID` | `"prod"` | `"prod"` | PASS |
| `loki.process` `environment` static label | `"prod"` | `"prod"` | PASS |

---

## 3. Diff Analysis

Full diff output (`diff -u staging-db-vm.alloy prod-db-vm.alloy`):

```
--- staging-db-vm.alloy
+++ prod-db-vm.alloy
@@ file header comment @@
-// Grafana Alloy Configuration for Staging Database VM
-// Environment: staging
+// Grafana Alloy Configuration for Production Database VM
+// Environment: production

@@ loki.relabel container_labels rule @@
-    regex         = "^/(.*)"
-    replacement   = "$1"

@@ loki.process static_labels @@
-      environment = "staging",
+      environment = "prod",

@@ loki.write comment + X-Scope-OrgID @@
-    // Multi-tenant identification
+    // Multi-tenant identification for production
-      "X-Scope-OrgID" = "staging",
+      "X-Scope-OrgID" = "prod",

@@ METRICS PIPELINE comment @@
-// and alerts can filter on {environment="staging", vm="db-vm"}.
+// and alerts can filter on {environment="prod", vm="db-vm"}.

@@ prometheus.relabel replacement @@
-    replacement  = "staging"
+    replacement  = "prod"
```

### 3.1 Diff classification

| Diff | Classification | Assessment |
|---|---|---|
| File header comment (`Staging` vs `Production`, `staging` vs `production`) | Expected cosmetic | PASS |
| `loki.relabel` slash-strip rule (`regex + replacement`) absent in prod | Pre-existing drift — `F-ALLO-02` (not in Phase 2 scope) | Known / PASS (not a Phase 2 regression) |
| `loki.process` `environment = "staging"` vs `"prod"` | Expected env diff | PASS |
| `loki.write` comment wording (`"for production"` suffix) | Cosmetic only | PASS |
| `loki.write` `X-Scope-OrgID = "staging"` vs `"prod"` | Expected env diff | PASS |
| METRICS PIPELINE inline comment `{environment="staging"...}` vs `{environment="prod"...}` | Expected cosmetic | PASS |
| `prometheus.relabel` `replacement = "staging"` vs `"prod"` | Expected env diff — exactly what spec requires | PASS |

**No unexpected diffs.** The only structural difference beyond expected environment values is the pre-existing `F-ALLO-02` slash-strip rule absent from prod, which is explicitly deferred to Phase 3 per §3 of the spec.

---

## 4. Label Correctness

| Label | Staging value | Prod value | Correct |
|---|---|---|---|
| Prometheus `environment` (relabel) | `staging` | `prod` | PASS |
| Prometheus `vm` (relabel) | `db-vm` | `db-vm` | PASS |
| Loki `environment` (static_labels) | `staging` | `prod` | PASS |
| Loki `vm` (static_labels) | `db-vm` | `db-vm` | PASS |
| Loki `X-Scope-OrgID` | `staging` | `prod` | PASS |

---

## 5. Findings

**No blocking findings.** All Phase 2 requirements for Tasks 14 and 15 are correctly implemented.

### Non-blocking observations

- **OBS-1 (F-ALLO-02 pre-existing):** `prod-db-vm.alloy` `loki.relabel` block is missing the slash-strip rules (`regex = "^/(.*)"` + `replacement = "$1"`). This causes container names to carry a leading `/` in Loki labels for prod. Pre-existing, tracked as `F-ALLO-02`, deferred to Phase 3. Not introduced by Phase 2.

- **OBS-2 (minor cosmetic):** `loki.write` comment in prod has the suffix `"for production"` while staging says only `"Multi-tenant identification"`. Inconsequential; does not affect runtime behavior.

---

## 6. Verdict

**APPROVED.** Both files correctly implement the `prometheus.scrape + prometheus.relabel + prometheus.remote_write` pipeline per spec §6.5 (F-ALLO-09 + F-ALLO-06). All existing logging pipeline blocks are intact. The diff is clean — only expected environment-value differences and the known pre-existing `F-ALLO-02` slash-strip drift. Tasks 14 and 15 are complete.
