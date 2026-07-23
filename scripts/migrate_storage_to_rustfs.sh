#!/usr/bin/env bash
# =============================================================================
# MinIO → RustFS data migration (staging / prod DB host)
#
# Implements the "Data migration" section of
# docs/deployment/rustfs-migration-runbook.md: stands a RustFS container up
# SIDE-BY-SIDE with the live MinIO (same docker network, no published ports),
# mirrors both buckets over the S3 API with `mc`, then verifies with
# `mc diff` + `mc du`. The live MinIO and its volume are never touched.
#
# Run this ON THE DB HOST. Safe to run repeatedly — `mc mirror` is
# incremental, so the pattern is: run once ahead of the maintenance window
# (bulk copy), then stop the backend and run again (final delta), then switch
# the compose file to the RustFS block and `docker compose up -d`.
#
# Required environment:
#   MINIO_ROOT_USER / MINIO_ROOT_PASSWORD
#       Live MinIO root credentials (the same .env the DB compose stack uses).
#       RustFS is started with the SAME credentials, so the backend's
#       MINIO_ACCESS_KEY/SECRET_KEY secrets stay valid after cutover.
#   MINIO_BUCKET
#       Main documents bucket. staging: scholarship-documents.
#       prod: scholarship-files (the old compose env was dead, so prod runs on
#       the config default) — CONFIRM with the bucket listing this script
#       prints before trusting it.
#
# Optional environment:
#   NETWORK          docker network of the live minio container
#                    (default: scholarship_staging_db_network; prod:
#                    scholarship_prod_db_network)
#   OLD_ENDPOINT     live MinIO endpoint inside that network (default: minio:9000)
#   RUSTFS_DATA_DIR  host dir for the new RustFS data
#                    (default: /opt/scholarship/rustfs/data — must match the
#                    rustfs_*_data volume device in the env's DB compose file)
#   RUSTFS_IMAGE     default: rustfs/rustfs:1.0.0-beta.8 (keep pinned to the
#                    tag in the compose files; re-run the runbook's Step-0
#                    spike before changing it)
#   ROSTER_BUCKET    default: roster-files
#   ALLOW_EXTRA_BUCKETS=1   proceed even if the live side has buckets beyond
#                    MINIO_BUCKET/ROSTER_BUCKET (they will NOT be mirrored —
#                    the runbook's bucket-inventory precondition)
# =============================================================================
set -euo pipefail

NETWORK="${NETWORK:-scholarship_staging_db_network}"
OLD_ENDPOINT="${OLD_ENDPOINT:-minio:9000}"
RUSTFS_DATA_DIR="${RUSTFS_DATA_DIR:-/opt/scholarship/rustfs/data}"
RUSTFS_IMAGE="${RUSTFS_IMAGE:-rustfs/rustfs:1.0.0-beta.8}"
ROSTER_BUCKET="${ROSTER_BUCKET:-roster-files}"
MIGRATION_CONTAINER="rustfs_migration"
MC_IMAGE="minio/mc:latest"

: "${MINIO_ROOT_USER:?MINIO_ROOT_USER must be set}"
: "${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD must be set}"
: "${MINIO_BUCKET:?MINIO_BUCKET must be set (staging: scholarship-documents, prod: scholarship-files)}"

log() { echo "[migrate-rustfs] $*"; }
die() { echo "[migrate-rustfs] ERROR: $*" >&2; exit 1; }

docker network inspect "$NETWORK" > /dev/null 2>&1 \
  || die "docker network '$NETWORK' not found (prod: set NETWORK=scholarship_prod_db_network)"

# --- 1. Prepare the RustFS data directory (RustFS runs as uid 10001) --------
# Recursive chown only on first creation: on delta re-runs the tree already
# holds the mirrored dataset (written by RustFS itself as uid 10001) and a
# recursive traversal would be O(objects) for nothing.
if [ ! -d "$RUSTFS_DATA_DIR" ]; then
  log "Creating $RUSTFS_DATA_DIR (owner uid 10001)"
  sudo mkdir -p "$RUSTFS_DATA_DIR"
  sudo chown -R 10001:10001 "$RUSTFS_DATA_DIR"
else
  log "Reusing existing $RUSTFS_DATA_DIR (ensuring top-level owner uid 10001)"
  sudo chown 10001:10001 "$RUSTFS_DATA_DIR"
fi

# --- 2. Start (or reuse) the side-by-side RustFS ----------------------------
if docker ps --format '{{.Names}}' | grep -qx "$MIGRATION_CONTAINER"; then
  log "Reusing running $MIGRATION_CONTAINER"
else
  docker rm -f "$MIGRATION_CONTAINER" > /dev/null 2>&1 || true
  log "Starting $MIGRATION_CONTAINER ($RUSTFS_IMAGE) on network $NETWORK"
  docker run -d --name "$MIGRATION_CONTAINER" \
    --network "$NETWORK" \
    -v "$RUSTFS_DATA_DIR:/data" \
    -e RUSTFS_ACCESS_KEY="$MINIO_ROOT_USER" \
    -e RUSTFS_SECRET_KEY="$MINIO_ROOT_PASSWORD" \
    -e RUSTFS_VOLUMES=/data \
    "$RUSTFS_IMAGE" > /dev/null
fi

log "Waiting for RustFS /health"
for i in $(seq 1 30); do
  if docker exec "$MIGRATION_CONTAINER" curl -sf http://localhost:9000/health > /dev/null 2>&1; then
    break
  fi
  [ "$i" -eq 30 ] && die "RustFS did not become healthy after 60s (docker logs $MIGRATION_CONTAINER)"
  sleep 2
done
log "RustFS is healthy"

# --- 3. Mirror + verify via mc (runs inside the docker network) -------------
# Credentials go in via env, never host argv (and not via MC_HOST_* URLs,
# which would need URL-encoding for special characters in the secret). mc is
# a generic S3 client and works against RustFS. --preserve keeps content-type
# + x-amz-meta-* metadata (rehearsed end-to-end 2026-06-11, incl.
# special-character keys).
run_mc() {
  docker run --rm --network "$NETWORK" \
    -e OLD_ENDPOINT="$OLD_ENDPOINT" \
    -e NEW_ENDPOINT="${MIGRATION_CONTAINER}:9000" \
    -e ACCESS_KEY="$MINIO_ROOT_USER" \
    -e SECRET_KEY="$MINIO_ROOT_PASSWORD" \
    --entrypoint sh "$MC_IMAGE" -c '
      set -e
      mc alias set old "http://$OLD_ENDPOINT" "$ACCESS_KEY" "$SECRET_KEY" > /dev/null
      mc alias set new "http://$NEW_ENDPOINT" "$ACCESS_KEY" "$SECRET_KEY" > /dev/null
      '"$1"
}

log "Live bucket inventory (confirm MINIO_BUCKET=$MINIO_BUCKET is right):"
# Capture once: an auth/network failure aborts here under set -e instead of
# being swallowed by a downstream `|| true` filter.
BUCKET_LISTING=$(run_mc "mc ls old")
echo "$BUCKET_LISTING"

# -F: bucket names are data, not regex (S3 allows `.` in bucket names).
# `|| true` only forgives grep's exit-1-on-no-match, never an mc failure.
EXTRA_BUCKETS=$(echo "$BUCKET_LISTING" | awk '{print $NF}' | sed 's#/$##' \
  | grep -vxF -e "$MINIO_BUCKET" -e "$ROSTER_BUCKET" || true)
if [ -n "$EXTRA_BUCKETS" ] && [ "${ALLOW_EXTRA_BUCKETS:-0}" != "1" ]; then
  die "unexpected live bucket(s) not covered by this migration:
$EXTRA_BUCKETS
Mirror them explicitly or re-run with ALLOW_EXTRA_BUCKETS=1 to declare them abandoned (runbook bucket-inventory precondition)."
fi

log "Non-ASCII object-key audit (runbook precondition; empty is good):"
# Capture first (listing failure aborts under set -e), then grep with a POSIX
# bracket range in the C locale (= bytes outside \x20-\x7e) instead of
# grep -P, which isn't available on all host distros.
KEY_LISTING=$(run_mc "mc ls --recursive old/$MINIO_BUCKET old/$ROSTER_BUCKET")
NON_ASCII_KEYS=$(echo "$KEY_LISTING" | LC_ALL=C grep '[^ -~]' || true)
if [ -n "$NON_ASCII_KEYS" ]; then
  echo "$NON_ASCII_KEYS"
  die "non-ASCII object keys found above — eyeball them before mirroring"
fi
log "  none found"

log "Mirroring old/$MINIO_BUCKET and old/$ROSTER_BUCKET → RustFS (incremental)"
run_mc "
  set -e
  mc mb --ignore-existing new/$MINIO_BUCKET new/$ROSTER_BUCKET
  mc mirror --preserve old/$MINIO_BUCKET new/$MINIO_BUCKET
  mc mirror --preserve old/$ROSTER_BUCKET new/$ROSTER_BUCKET
"

log "Verifying with mc diff (must be empty)"
# mc diff exit codes vary by build: some return 1 when differences exist,
# others return 0 and just list them. Treat rc==1 as "differences found" so
# it reaches the die message below instead of tripping set -e mid-substitution;
# anything >1 is an operational error (auth/network) and aborts loudly.
DIFF_OUT=""
for bucket in "$MINIO_BUCKET" "$ROSTER_BUCKET"; do
  set +e
  BUCKET_DIFF=$(run_mc "mc diff old/$bucket new/$bucket")
  rc=$?
  set -e
  if [ "$rc" -gt 1 ]; then
    echo "$BUCKET_DIFF"
    die "mc diff old/$bucket new/$bucket failed with exit $rc — operational error, not a content difference"
  fi
  if [ "$rc" -eq 1 ] && [ -z "$BUCKET_DIFF" ]; then
    BUCKET_DIFF="(mc diff exit 1 for $bucket but printed nothing — inspect manually)"
  fi
  DIFF_OUT="${DIFF_OUT}${BUCKET_DIFF}"
done
if [ -n "$DIFF_OUT" ]; then
  echo "$DIFF_OUT"
  die "mc diff is NOT empty — investigate before cutover (if the backend is still running, this may just be new writes: stop it and re-run for the final delta)"
fi
log "mc diff clean on both buckets"

log "Size comparison (old vs new):"
run_mc "mc du old/$MINIO_BUCKET; mc du new/$MINIO_BUCKET; mc du old/$ROSTER_BUCKET; mc du new/$ROSTER_BUCKET"

# --- 4. Stop the temp container; data stays in RUSTFS_DATA_DIR --------------
log "Stopping $MIGRATION_CONTAINER (data persists in $RUSTFS_DATA_DIR)"
docker rm -f "$MIGRATION_CONTAINER" > /dev/null

log "DONE. Next steps (runbook 'Cutover order'):"
log "  1. If the backend was running during this pass: stop it and re-run this script for the final delta."
log "  2. Switch the DB stack to the RustFS compose block:"
log "       docker compose -f docker-compose.<env>-db.yml up -d minio"
log "     (the old MinIO container is replaced; its volume is untouched = rollback)"
log "  3. Start the backend; run: docker exec <backend> python -m app.scripts.storage_compat_check  (expect 14/14 PASS)"
log "  4. Spot-check upload → preview → roster download; watch logs for S3Error for the first hour."
