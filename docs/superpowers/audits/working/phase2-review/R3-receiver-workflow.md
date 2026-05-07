# R3 Audit: GitHub Issue Receiver Workflow

**File:** `.github/workflows/monitoring-alert-issue.yml`
**Branch:** `feat/monitoring-phase2`
**Spec ref:** `docs/superpowers/specs/2026-05-06-monitoring-stack-fix-phase2-design.md` §6.2.5
**Auditor:** R3 (read-only)
**Date:** 2026-05-06

---

## 1. De-dupe State Machine

| # | Condition | Expected Action | Implementation | Verdict |
|---|-----------|-----------------|----------------|---------|
| 1 | `not-found` + `status=firing` | Create new issue | Step "Create new issue": `if: steps.find.outputs.found != 'true' && ... status == 'firing'` | PASS |
| 2 | `found` + `state=CLOSED` + `status=firing` | Reopen + comment | Step "Reopen + comment": `if: found == 'true' && state == 'CLOSED' && status == 'firing'` | PASS |
| 3 | `found` + `state=OPEN` + `status=firing` | Append firing comment | Step "Append firing comment": `if: found == 'true' && state == 'OPEN' && status == 'firing'` | PASS |
| 4 | `found` + `status=resolved` | Append resolved comment; do NOT auto-close | Step "Append resolved comment": appends comment only, no `gh issue close` call | PASS |
| 5 | `not-found` + `status=resolved` | Silent no-op (race condition) | No step matches `found != 'true' && status == 'resolved'` — workflow runs zero steps after render | PASS |

All five states are correctly handled.

---

## 2. Label Scheme

**Spec requirement:** `monitoring-alert`, `alert:<alertname>`, `env:<env>`, `severity:<level>`

| Label | Applied on create | Applied on reopen | Verdict |
|-------|------------------|-------------------|---------|
| `monitoring-alert` | Yes (line 82) | No (reopen does not re-apply labels) | PASS — label persists from original issue |
| `alert:<alertname>` | Yes (line 83) | No | PASS |
| `env:<env>` | Yes (line 84) | No | PASS |
| `severity:<level>` | Yes (line 85) | No | PASS — if severity changes between firings, the label is stale. Acceptable for current scope. |

Labels are applied correctly on creation. The `gh issue list` lookup uses all three discriminating labels (`monitoring-alert`, `alert:$ALERT`, `env:$ENV`) with multiple `--label` flags, which the GitHub CLI treats as AND (all must match), not OR. This correctly separates alerts by `alertname` and `env` simultaneously.

---

## 3. Issue Lookup Correctness

```
gh issue list \
  --label "monitoring-alert" \
  --label "alert:$ALERT" \
  --label "env:$ENV" \
  --state all \
  --limit 1 \
  --json number,state \
  --jq '.[0]'
```

- **AND semantics:** Multiple `--label` flags in `gh issue list` are additive (AND). This is correct; a different `env:` label will not match.
- **`--state all`:** Catches both OPEN and CLOSED issues. Correct.
- **`--limit 1`:** Returns only the most-recently-updated matching issue. If two matching issues somehow exist, only one is acted on. This is acceptable (see Finding F-R3-03 below).
- **`.[0]` on empty array:** When no issue matches, `gh` returns `[]`; `jq '.[0]'` returns `null`. The shell check `[ "$ISSUE" != "null" ]` correctly treats this as not-found. PASS.

---

## 4. Body Construction (`/tmp/body.md`)

The heredoc at lines 30–45 expands all `client_payload` fields: `STATUS`, `ALERT`, `ENV`, `SEVERITY`, `INSTANCE`, `VALUE`, `FIRED_AT`, `GRAFANA_URL`, `SUMMARY`, `DESCRIPTION`. All fields referenced in the spec's contact-point message are covered.

**Diff between spec snippet and actual file:**

| Field | Spec (§6.2.5) | Actual workflow | Verdict |
|-------|---------------|-----------------|---------|
| `**Environment:**` | Plain `$ENV` | Backtick-wrapped `` \`$ENV\` `` | IMPROVEMENT — renders as code |
| `**Severity:**` | Plain | Backtick-wrapped | IMPROVEMENT |
| `GITHUB_OUTPUT` quoting | `>> $GITHUB_OUTPUT` | `>> "$GITHUB_OUTPUT"` | IMPROVEMENT — safer quoting |
| Heredoc body indentation | Spec uses 10-space indent | Actual uses 10-space indent | PASS |

The actual implementation is a slight improvement over the spec draft on both fronts.

---

## 5. Permissions

```yaml
permissions:
  issues: write
  contents: read
```

- `issues: write` — required for `gh issue create`, `gh issue reopen`, `gh issue comment`. PASS.
- `contents: read` — minimal read access; not strictly needed for this workflow (no checkout step) but harmless and follows least-privilege defaults. PASS.
- `secrets.GITHUB_TOKEN` (built-in) is used for `GH_TOKEN` in all steps. No `GH_PAT` is referenced. PASS — using the built-in token is correct; a PAT would be excessive for intra-repo issue operations.

---

## 6. Edge Case Findings

### F-R3-01 — Missing fields cause silent body corruption (P1)

**Condition:** Grafana sends a partial payload (e.g., `grafana_url` is empty or omitted because `ExternalURL` is not configured).

**Effect:** The heredoc expands the empty variable to an empty string, producing malformed or confusing markdown (e.g., `**Grafana:** ` with no value). `gh issue create` will not fail — it will create an issue with incomplete body. There is no guard or default value for any field.

**Recommended fix:**
```bash
ALERT=${ALERT:-"(unknown)"}
ENV=${ENV:-"(unknown)"}
SEVERITY=${SEVERITY:-"(unknown)"}
# ... etc. for all fields
```
Add default substitutions at the top of the `render` step's `run` block before the heredoc.

---

### F-R3-02 — Shell injection via client_payload fields (P1)

**Condition:** A malicious or misconfigured Grafana instance sends a `client_payload` field containing shell metacharacters (e.g., `summary` containing a backtick or `$(cmd)`).

**Effect in the heredoc:** The heredoc `<<EOF` (unquoted delimiter) with bare variable expansion (`$SUMMARY`, `$DESCRIPTION`) is subject to word splitting and glob expansion, but NOT command substitution — command substitution only occurs if the variable value contains backticks or `$(...)` and the expansion is unquoted. In a heredoc body, variables expand but backticks inside variable values are NOT executed (they are treated as literal characters in the output stream). Standard shell here-documents do not execute backticks within `$VAR` expansions.

**However:** The `title` line uses `echo "title=Monitoring Alert: $ALERT ($ENV/$SEVERITY)" >> "$GITHUB_OUTPUT"`. If `ALERT`, `ENV`, or `SEVERITY` contain a newline, this would inject extra keys into `GITHUB_OUTPUT` (newline injection). GitHub Actions sanitizes secrets but `client_payload` values are not sanitized.

**Severity:** P1 — newline injection into `GITHUB_OUTPUT` could corrupt subsequent step outputs. The fields originate from Grafana alert labels, which are operator-controlled, so real-world risk is low but non-zero.

**Recommended fix:** Use `printf '%s' "$ALERT"` or strip newlines: `ALERT=$(echo "$ALERT" | tr -d '\n')`.

---

### F-R3-03 — `--limit 1` picks oldest or newest; ordering not guaranteed (P2)

**Condition:** Two issues with identical labels exist (e.g., a first issue was manually labelled to match, or a bug created a duplicate).

**Effect:** `--limit 1` returns whichever the API returns first (by default, most-recently-updated). The workflow will act on that one, ignoring the other. The other remains in its current state indefinitely.

**Severity:** P2 — should not occur in normal operation. The label scheme makes accidental collision unlikely. Acceptable for current scope; worth a note in the runbook.

---

### F-R3-04 — `env:` label separation works correctly (PASS note)

Two alerts with the same `alertname` but different `environment` labels (e.g., `HighCPUUsage` in `staging` and `HighCPUUsage` in `prod`) will each match only their respective `env:<env>` label. The lookup correctly isolates them. No issue found.

---

### F-R3-05 — `resolved` comment uses `fired_at` instead of `resolved_at` (P2)

Line 106:
```bash
--body "✅ Alert resolved at ${{ github.event.client_payload.fired_at }}. ..."
```

The timestamp shown is `fired_at` (when the alert originally fired), not a `resolved_at` timestamp. The spec's contact-point payload does not include a `resolved_at` field, so the workflow cannot display it — but the label "resolved at" is misleading when it actually shows the original fire time.

**Recommended fix:** Change label to "Alert originally fired at" or add `resolved_at` to the Grafana contact-point message template.

---

### F-R3-06 — `state=CLOSED` is uppercase; gh CLI output casing (PASS note)

The `gh issue list --json ... state` field returns `"OPEN"` or `"CLOSED"` in uppercase. The workflow conditions compare against `'OPEN'` and `'CLOSED'` (uppercase). This matches. PASS.

---

## 7. Summary

| Finding | Description | Severity |
|---------|-------------|----------|
| F-R3-01 | Missing payload fields produce silent body corruption; no defaults | P1 |
| F-R3-02 | Newline injection into GITHUB_OUTPUT via client_payload fields | P1 |
| F-R3-03 | `--limit 1` behavior on duplicate issues is ordering-dependent | P2 |
| F-R3-04 | `env:` label correctly separates concurrent same-alert, different-env firings | PASS |
| F-R3-05 | `resolved` comment displays `fired_at` timestamp under a misleading label | P2 |
| F-R3-06 | `state` case comparison matches `gh` CLI output | PASS |

**Overall assessment:** The 4+1 state machine is correctly implemented. Label scheme matches spec. Permissions use built-in token correctly. Two P1 findings (missing field defaults, newline injection) should be fixed before the workflow handles production alerts. Two P2 findings are cosmetic / low-probability edge cases.
