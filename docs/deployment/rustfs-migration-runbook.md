# RustFS Migration Runbook — staging / prod / staging-e2e

Status: **dev has already switched** (see `docker-compose.dev.yml`, PR `feat/dev-rustfs-swap`).
This runbook is the prepared, not-yet-executed cutover plan for the remaining
environments. The backend keeps the generic python `minio` SDK and all
`MINIO_*` env names — RustFS serves the same S3 API on the same
`MINIO_ENDPOINT`, so **no application code or GitHub secret changes** are part
of the cutover.

## Verified compatibility baseline (dev, 2026-06-11)

- Image: `rustfs/rustfs:1.0.0-beta.8`
- `app/scripts/storage_compat_check.py` → **14/14 PASS** (put/get/stat,
  copy+CopySource, remove, presigned GET/PUT, 10MB multipart checksum,
  metadata round-trip, default-private anonymous-403, dual-bucket
  auto-create, health-check cycle, seeded regulations PDF)
- Storage-touching e2e subset green (student-draft-document-preview,
  admin-preview-dialog-render, batch-import-upload, roster-admin,
  roster-generation, regulations-pdf-canvas)
- Credential envs `RUSTFS_ACCESS_KEY`/`RUSTFS_SECRET_KEY` verified honored on
  this tag (positive + negative test — upstream rustfs/rustfs#1058 regression
  guard); default `rustfsadmin` creds rejected.
- `/health` endpoint + in-image `curl` verified for compose healthchecks.

### Two real semantic differences found (already handled in code)

1. **Explicit `Deny` bucket policies bind the OWNER too.** MinIO lets root
   credentials bypass bucket policies; RustFS enforces an explicit Deny
   against everyone (AWS-faithful). The old deny-all `s3:GetObject` policy on
   the roster bucket therefore 403'd the backend's own roster downloads.
   → `MinIOService` no longer attaches any bucket policy; buckets are
   private by default (anonymous GET → 403 with no policy attached —
   verified). **Cutover step: do NOT carry old bucket policies over.**
2. **`client.presigned_url` does not exist** in the minio SDK —
   `MinIOService.get_presigned_url` was latently broken (zero callers, mocked
   in tests). Fixed to `client.get_presigned_url`.

Also note: the minio SDK rejects **non-ASCII metadata client-side**
(identical on MinIO and RustFS) — not a RustFS delta.

### Deep-scan results (2026-06-11, verified empirically against dev RustFS)

- **`mc mirror` rehearsal PASSED end-to-end**: a real MinIO
  (RELEASE.2025-09-07) was stood up next to dev RustFS and mirrored with
  `mc mirror --preserve` — all objects arrived with **custom
  `x-amz-meta-*` metadata, content-type, AND special-character keys
  (`file with space+plus.xlsx`) intact**; `mc diff` empty. The migration
  tooling path is proven, not assumed.
- **Ranged reads work**: `get_object(offset, length)` returns correct
  byte ranges on RustFS (currently unused by the app, but proxies/browsers
  may rely on Range semantics later).
- **No ETag dependency**: the app never stores or compares ETags (multipart
  ETag format differences are therefore irrelevant).
- **No URI-scheme dependency in the DB**: `payment_rosters.minio_object_name`
  stores the bare object name; the `minio://...` string in
  `upload_roster_file`'s return value is never persisted.
- **Roster hash integrity check was DEAD** (on MinIO too): it read the bare
  `file-hash` metadata key, but the SDK returns custom metadata PREFIXED
  (`x-amz-meta-file-hash`) — so `stored_hash` was always `None` and the
  SHA256 verification silently never ran. Fixed in this PR; the check is now
  live (verified against RustFS).

## Preconditions (gate — all must hold)

- [ ] Dev has baked ≥ 2 weeks with no storage incidents
- [ ] Re-pin to the latest verified RustFS tag and re-run the Step-0 spike
      (positive + negative credential test, `/health`, curl-in-image)
- [ ] `storage_compat_check.py` 14/14 PASS against a scratch RustFS of that tag
- [ ] Monitoring replacement ready (see "Monitoring gap" below) — staging
      cutover MUST NOT proceed with zero storage alerting
- [ ] Maintenance window agreed (backend writes must stop during final delta
      mirror)
- [ ] **Versioning audit** (compliance — the SRS names "MinIO Versioning,
      7-year retention" as the backup story): on the live side run
      `mc version info live/<bucket>` for BOTH buckets. If versioning is
      enabled, `mc mirror` copies **only the latest version** — version
      history does NOT migrate. The frozen old MinIO volume then becomes the
      retention archive: keep it (and its snapshots) for the full retention
      window, and record that decision. Do not enable RustFS versioning
      ("under testing" features) as a substitute without its own validation.
- [ ] **Bucket inventory**: `mc ls live` on the live side — confirm the only
      buckets are `scholarship-files`(or the env's `MINIO_BUCKET` value) and
      `roster-files`. Any extra bucket (manual uploads, console experiments)
      must be explicitly mirrored or explicitly declared abandoned.
- [ ] **TLS gate (prod)**: prod backend connects with `MINIO_SECURE=true`
      (docker-compose.prod.yml default) and prod-db mounts
      `minio_config:/root/.minio`, whose `certs/` dir is how MinIO serves TLS.
      ALL validation so far ran secure=false. Before prod cutover: inspect the
      volume for `certs/`, determine where RustFS gets its TLS cert
      (`RUSTFS_TLS_PATH`), and rehearse a backend connection with
      `minio_secure=True` against RustFS+cert (the SDK validates against
      certifi — private CAs need the CA bundled). Do NOT drop the old
      `minio_config` mount until the cert story is replaced.
- [ ] **Version-upgrade gate**: the image is a pinned PRERELEASE; on-disk
      format stability across RustFS versions is NOT guaranteed. Before
      adopting ANY new tag (incl. beta→beta): clone the data volume, boot the
      new image against the clone, run `storage_compat_check` + a checksum
      sweep. Never in-place upgrade the only copy.
- [ ] **Key audit**: scan for problematic object keys before mirroring —
      `mc ls --recursive live/<bucket> | grep -P '[^\x20-\x7e]'` (non-ASCII)
      — rehearsal proved spaces/`+` survive, but eyeball anything exotic.

## Data migration (per environment; staging-db first)

MinIO's on-disk erasure format is NOT readable by RustFS — data moves over
the S3 API with `mc` (the MinIO client is a generic S3 client and works
against RustFS; the staging-e2e workflow already uses `mc mirror` this way).

```bash
# 1. Stand up RustFS side-by-side on alternate ports (e.g. 9100/9101),
#    same docker network as the existing MinIO. New named volume.
#    If using BIND mounts: chown -R 10001:10001 <dir> (RustFS runs uid 10001).

# 2. Mirror both buckets (run from a container on the same network):
docker run --rm --network <net> --entrypoint sh minio/mc:latest -c '
  mc alias set old http://minio:9000        "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" &&
  mc alias set new http://rustfs:9000       "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" &&
  mc mb --ignore-existing "new/${MINIO_BUCKET}" new/roster-files &&
  mc mirror --preserve "old/${MINIO_BUCKET}" "new/${MINIO_BUCKET}" &&
  mc mirror --preserve old/roster-files      new/roster-files &&
  mc diff "old/${MINIO_BUCKET}" "new/${MINIO_BUCKET}" &&
  mc diff old/roster-files      new/roster-files'
# MINIO_BUCKET differs per env: staging/staging-e2e = scholarship-documents (or
# the STAGING_MINIO_BUCKET secret), prod = "scholarship-files" (the compose
# sets only the DEAD MINIO_BUCKET_NAME env, so the config default applies —
# confirm against `mc ls old` before mirroring).

# 3. Validate: object counts match (mc du old/... vs new/...), confirm
#    anonymous GET on a roster object → 403, and stat-check EVERY DB location
#    that references storage objects (the complete inventory — missing one
#    means orphaned references that 404 at download time):
#      application_files.object_name
#      applications.application_document_url
#      applications.submitted_form_data -> documents[].object_name (JSON)
#      user_profiles.bank_document_object_name (+ derived _photo_url)
#      student_bank_accounts.passbook_cover_object_name
#      payment_rosters.minio_object_name           (ROSTER bucket)
#      batch_imports.file_path
#      supplementary_docs.object_name
#      application_documents.example_file_url
#      scholarship_types.terms_document_url
#      system_settings.value for keys regulations_url / sample_document_url
#    payment_rosters.excel_file_hash (SHA256) can byte-verify roster objects.
```

## Compose diffs per environment

Apply the same shape as the dev swap (`docker-compose.dev.yml` is the
reference diff):

| File | Changes |
|---|---|
| `docker-compose.staging-db.yml` | image → pinned `rustfs/rustfs:<tag>`; env `MINIO_ROOT_USER/PASSWORD` → `RUSTFS_ACCESS_KEY/SECRET_KEY` (same values; backend-side MINIO_* secrets unchanged); drop `command: server /data --console-address ":9001"`; add `RUSTFS_VOLUMES: /data`; healthcheck `/minio/health/live` → `/health`; **remove `MINIO_PROMETHEUS_AUTH_TYPE: public`** (no such endpoint); new volume `rustfs_staging_data` (keep `minio_staging_data` untouched = rollback) |
| `docker-compose.prod-db.yml` | same, plus: drop the `minio_config:/root/.minio` mount (RustFS doesn't use it); resource limits can carry over; **fix the dead env**: prod backend (`docker-compose.prod.yml`) sets `MINIO_BUCKET_NAME`, but config.py binds `MINIO_BUCKET` — same silently-ignored-env bug fixed in dev; align before or during cutover and confirm which bucket name prod data actually lives in (it has been the default `scholarship-files` if the env never bound) |
| `docker-compose.staging-e2e.yml` | same swap for the ephemeral replica (ports 19000/19001); the `mc mirror` seeding step in `.github/workflows/staging-e2e.yml` keeps working as-is. **Swap the replica image in the SAME change as the staging-db cutover** — a MinIO replica fronting a RustFS live store would re-introduce the semantic differences (owner-Deny policies, etc.) that e2e is supposed to catch |

GitHub secrets (`STAGING_MINIO_*`, `MINIO_*`): **no changes** — names and
values stay; they configure the backend client, not the server.

## ⚠️ CRITICAL merge-ordering hazard (staging)

`deploy-monitoring-stack.yml` auto-triggers on any push to main touching
`monitoring/**`, scp's the REPO's `docker-compose.staging-db.yml` to the VM,
`docker rm -f scholarship_minio_staging`, and `up -d minio`. **If the RustFS
staging-db compose block merges to main BEFORE the data-migration maintenance
window, the next monitoring push destroys the live staging MinIO and boots an
EMPTY RustFS — every staging file download 404s with zero data migrated.**
Sequencing rule: the staging-db compose swap must merge in the SAME change
window as the executed data migration (or the monitoring workflow's
storage-recreate step must be temporarily disabled first). The same workflow
also hardcodes the container name `scholarship_minio_staging` — keep that
container name (or update the workflow in the same PR).

## Cutover order (per environment)

1. Stop backend (maintenance window) — prevents writes during delta sync
2. Final `mc mirror` delta + `mc diff` (must be empty)
3. Switch compose to RustFS block; `docker compose up -d` storage + backend
4. `docker exec <backend> python -m app.scripts.storage_compat_check` → 14/14
5. Smoke e2e (staging: the storage-touching @nightly subset; or manual
   upload→preview→roster-download spot check)
6. Watch logs for `S3Error` for the first hour

## Rollback

Old MinIO volume is never touched. Revert the compose block to the MinIO
image + old volume, `docker compose up -d`, done. Caveat: objects written
AFTER cutover exist only in RustFS — `mc mirror new old` them back before
reverting if any writes happened.

## Monitoring gap (tracked in the GitHub issue created with this runbook)

staging-db-vm Alloy scrapes `minio:9000/minio/v2/metrics/{cluster,bucket,node}`
(3 jobs) feeding the Grafana `minio-monitoring` dashboard. RustFS serves none
of these. At cutover those scrapes will fail and any up-based alerts will
fire. **Disable the three scrape jobs in the same change that swaps the
compose**, and ship replacement observability first:
- blackbox probe of `:9000/health` (storage-down alerting), and/or
- S3 synthetic canary (timed put/get/delete via a cron job), and/or
- RustFS native observability (OTel) once its Prometheus story stabilizes.

Acceptance for staging cutover: equivalent storage-down + disk-usage
alerting exists.

## Risk register

| Risk | Mitigation |
|---|---|
| rustfs#1058 (credential envs ignored in some builds) | Step-0 spike repeats positive+negative credential test on every re-pin |
| Explicit Deny policies block owner | No bucket policies post-migration; compat check pins anonymous-403-by-default + owner-GET-ok |
| UID 10001 vs bind-mount perms | `chown -R 10001:10001` any bind mounts (prod-db uses bind mounts under `/opt/scholarship/minio/...` — new dirs needed) |
| Beta maturity / read latency | bake-in on dev + staging before prod; rollback volume preserved |
| Lifecycle rules | not used by this system (none configured) — re-check before enabling any |
| `MINIO_BUCKET_NAME` dead env in prod compose | fix to `MINIO_BUCKET` during cutover; verify actual bucket name in prod data first |
| Versioned-bucket history does not migrate (`mc mirror` copies latest only) | versioning audit precondition; frozen MinIO volume = retention archive for the compliance window |
| Prod volume snapshots/backups still target the OLD MinIO dir | update snapshot/backup config to the new RustFS data dir (`/opt/scholarship/rustfs/...`) at cutover; `scripts/backup.sh` only covers postgres — object-storage backup is volume-level |
| staging-e2e MinIO replica masking RustFS semantics | swap the replica image in the same change as staging-db |
| **RustFS beta.8 leaks prior object data on overwrite** (live-proven: each overwrite of a >inline-size key leaves the previous dataDir on disk; DELETE leaves orphans too; no background reclaim) | watch `du`-vs-`mc du` divergence during bake-in; avoid fixed-key overwrites (seed_regulations re-seeds leak ~240KB each); track upstream rustfs/rustfs for a fix before prod |
| Volume snapshot restores to an unreadable store | restore drill in the checklist: tar full `/data` INCLUDING `.rustfs.sys` (format.json/IAM/bucket metadata), untar to fresh volume, boot RustFS, pass compat check + checksum sweep |
| Pre-existing batch-import delete bug orphaned PII files in storage (fixed in this PR) | before mirroring, sweep `batch-imports/` prefix for objects with no matching batch_imports.file_path row; decide migrate-or-purge |
