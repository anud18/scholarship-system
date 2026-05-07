# scripts/phase3 — Phase 3 Alert Issue Helper

## Purpose

`open-deferred-alert-issues.sh` opens the 6 GitHub tracking issues for
Phase 3 alert work defined in
`docs/superpowers/audits/working/phase3-prep/deferred-alerts-redesign.md`.

| # | Alert | Part | Labels |
|---|-------|------|--------|
| 1 | PostgreSQLDown | Deferred (DB-VM pipeline) | `database` |
| 2 | PostgreSQLTooManyConnections | Deferred (DB-VM pipeline) | `database` |
| 3 | PostgreSQLHighConnections | Deferred (DB-VM pipeline) | `database` |
| 4 | HighHTTPErrorRate | Dropped → redesigned on backend metrics | `application` |
| 5 | SlowHTTPResponseTime | Dropped → redesigned on backend histogram | `application` |
| 6 | MinIODown | Dropped → redesigned with AP-VM scrape target | `application` |

## Pre-conditions

1. `gh` CLI installed and authenticated (`gh auth status`).
2. You have write access to the target repository (default: `anud18/scholarship-system`).
3. The labels `phase3`, `monitoring-deferred-alert`, `database`, and `application`
   must already exist in the repo. Create them if missing:

   ```bash
   gh label create phase3 --color 0075ca --repo anud18/scholarship-system
   gh label create monitoring-deferred-alert --color e4e669 --repo anud18/scholarship-system
   gh label create database --color b60205 --repo anud18/scholarship-system
   gh label create application --color 0e8a16 --repo anud18/scholarship-system
   ```

## Usage

```bash
# Preview — no issues created, no gh calls made
scripts/phase3/open-deferred-alert-issues.sh --dry-run

# Interactive — prompts before each issue
scripts/phase3/open-deferred-alert-issues.sh

# Non-interactive — create all without prompts
scripts/phase3/open-deferred-alert-issues.sh --yes

# Targeting a different repo fork
scripts/phase3/open-deferred-alert-issues.sh --yes --repo yourfork/scholarship-system
```

All flags may be combined: `--dry-run --yes` is valid (dry-run wins, no
network calls).

## Output format

```
==========================================================
 Phase 3 deferred-alert issue creator
 Repo    : anud18/scholarship-system
 Dry-run : false
 Auto-yes: true
==========================================================

── Issue 1/6 ──────────────────────────────────────────────────
  Title : [Phase 3] Restore PostgreSQLDown ...
  Labels: phase3,monitoring-deferred-alert,database
  Status: created https://github.com/anud18/scholarship-system/issues/42

── Issue 2/6 ...
  Status: already exists: #38 [Phase 3] Restore PostgreSQLTooManyConnections ...

==========================================================
 Summary: created 5, skipped 1 (already exist), failed 0
==========================================================
```

Exit code is `0` if all issues were created or skipped, `1` if any `gh`
call failed.

## Idempotency

The script calls `gh issue list --label phase3 --state open --search "<title>"`
before creating each issue.  If a matching open issue already exists the step
is skipped and counted in "skipped".  Running twice is safe.
