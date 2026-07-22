#!/bin/bash
# Remote database backup driver used by .github/workflows/db-backup.yml.
#
# Runs ON the self-hosted runner. SSHes into the DB-VM and dumps the
# postgres container to a dated directory on that VM (backups stay on the
# DB host — dumps contain PII and must NOT be uploaded as GitHub artifacts).
#
# Required environment variables:
#   SSH_HOST      DB-VM hostname/IP
#   SSH_USER      SSH user on the DB-VM
#   SSH_KEY_PATH  Path to the SSH private key on the runner
#   DB_CONTAINER  Postgres container name on the DB-VM
#   ENV_NAME      Environment label used in backup filenames (staging/production)
# Optional:
#   SSH_PORT        SSH port on the DB-VM (default: 8822)
#   RETENTION_DAYS  Days of dated backup directories to keep (default: 30)
#   BACKUP_ROOT     Backup directory on the DB-VM (default: /opt/scholarship/postgres/backups)

set -euo pipefail

: "${SSH_HOST:?SSH_HOST is required}"
: "${SSH_USER:?SSH_USER is required}"
: "${SSH_KEY_PATH:?SSH_KEY_PATH is required}"
: "${DB_CONTAINER:?DB_CONTAINER is required}"
: "${ENV_NAME:?ENV_NAME is required}"
SSH_PORT="${SSH_PORT:-8822}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
BACKUP_ROOT="${BACKUP_ROOT:-/opt/scholarship/postgres/backups}"

if ! [[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]] || [ "$RETENTION_DAYS" -lt 1 ]; then
    echo "ERROR: RETENTION_DAYS must be a positive integer (got: ${RETENTION_DAYS})" >&2
    exit 1
fi
if ! [[ "$ENV_NAME" =~ ^[a-z0-9_-]+$ ]]; then
    echo "ERROR: ENV_NAME must match ^[a-z0-9_-]+$ (got: ${ENV_NAME})" >&2
    exit 1
fi

echo "=== Database backup: ${ENV_NAME} ==="
echo "Target: ${SSH_USER}@${SSH_HOST}:${SSH_PORT} container=${DB_CONTAINER}"
echo "Backup root: ${BACKUP_ROOT} (retention: ${RETENTION_DAYS} days)"

# Pass parameters to the remote shell as safely-quoted env assignments so the
# remote script body itself can stay single-quoted (no local interpolation).
REMOTE_ENV=$(printf "DB_CONTAINER=%q ENV_NAME=%q RETENTION_DAYS=%q BACKUP_ROOT=%q" \
    "$DB_CONTAINER" "$ENV_NAME" "$RETENTION_DAYS" "$BACKUP_ROOT")

ssh -p "$SSH_PORT" -i "$SSH_KEY_PATH" \
    -o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=30 \
    "${SSH_USER}@${SSH_HOST}" "${REMOTE_ENV} bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }

if ! docker ps --format '{{.Names}}' | grep -qx "${DB_CONTAINER}"; then
    log "ERROR: container ${DB_CONTAINER} is not running on $(hostname)"
    docker ps --format '  running: {{.Names}}' || true
    exit 1
fi

# Credentials come from the container itself — pg_dump runs over the
# container-local unix socket (trust auth), so no password crosses SSH.
PGUSER=$(docker exec "${DB_CONTAINER}" printenv POSTGRES_USER)
PGDB=$(docker exec "${DB_CONTAINER}" printenv POSTGRES_DB)

DATE_DIR=$(date +%Y%m%d)
STAMP=$(date +%Y%m%d_%H%M%S)
TARGET_DIR="${BACKUP_ROOT}/${DATE_DIR}"
BACKUP_FILE="scholarship_db_${ENV_NAME}_${STAMP}.dump"

if ! mkdir -p "${TARGET_DIR}" 2>/dev/null; then
    log "mkdir needs elevated permissions, retrying with sudo -n"
    sudo -n mkdir -p "${TARGET_DIR}"
    sudo -n chown "$(id -un):$(id -gn)" "${TARGET_DIR}"
fi

log "Dumping ${PGDB} from ${DB_CONTAINER} -> ${TARGET_DIR}/${BACKUP_FILE}"
docker exec "${DB_CONTAINER}" pg_dump \
    -U "${PGUSER}" -d "${PGDB}" \
    --format=custom --compress=9 \
    > "${TARGET_DIR}/${BACKUP_FILE}"

if [ ! -s "${TARGET_DIR}/${BACKUP_FILE}" ]; then
    log "ERROR: backup file is empty"
    rm -f "${TARGET_DIR}/${BACKUP_FILE}"
    exit 1
fi

# Integrity check: the archive TOC must be readable by pg_restore.
log "Verifying archive with pg_restore --list"
if ! docker exec -i "${DB_CONTAINER}" pg_restore --list /dev/stdin \
        < "${TARGET_DIR}/${BACKUP_FILE}" > /dev/null; then
    log "ERROR: pg_restore could not read the archive — backup is corrupt"
    rm -f "${TARGET_DIR}/${BACKUP_FILE}"
    exit 1
fi

(cd "${TARGET_DIR}" && sha256sum "${BACKUP_FILE}" > "${BACKUP_FILE}.sha256")
chmod 640 "${TARGET_DIR}/${BACKUP_FILE}" "${TARGET_DIR}/${BACKUP_FILE}.sha256"

BACKUP_SIZE=$(du -h "${TARGET_DIR}/${BACKUP_FILE}" | cut -f1)
log "Backup created: ${BACKUP_FILE} (${BACKUP_SIZE})"

# Retention: prune dated directories older than the cutoff. This intentionally
# applies the same retention to backups written by the in-container cron
# service (production), which uses the same YYYYMMDD directory layout.
CUTOFF_DATE=$(date -d "${RETENTION_DAYS} days ago" +%Y%m%d 2>/dev/null \
    || date -u -d "@$(($(date +%s) - RETENTION_DAYS * 86400))" +%Y%m%d)
log "Pruning backups older than ${CUTOFF_DATE}"
DELETED=0
for dir in "${BACKUP_ROOT}"/*/; do
    [ -d "${dir}" ] || continue
    base=$(basename "${dir}")
    if [[ "${base}" =~ ^[0-9]{8}$ ]] && [ "${base}" -lt "${CUTOFF_DATE}" ]; then
        log "  deleting ${base}"
        rm -rf "${dir}"
        DELETED=$((DELETED + 1))
    fi
done
log "Pruned ${DELETED} old backup directory(ies)"

TOTAL_BACKUPS=$(find "${BACKUP_ROOT}" -name "*.dump" 2>/dev/null | wc -l)
TOTAL_SIZE=$(du -sh "${BACKUP_ROOT}" 2>/dev/null | cut -f1)
log "Total dumps on host: ${TOTAL_BACKUPS} (${TOTAL_SIZE})"
log "BACKUP OK: ${TARGET_DIR}/${BACKUP_FILE} (${BACKUP_SIZE})"
REMOTE_SCRIPT

echo "=== ${ENV_NAME} backup finished successfully ==="
