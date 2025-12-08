#!/bin/sh
# Database backup script for scholarship system
# This script runs inside the postgres-backup container via cron
# It creates compressed PostgreSQL backups with retention management

set -e

# Configuration from environment variables
POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-scholarship_db}"
POSTGRES_USER="${POSTGRES_USER:-scholarship_user}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"

# Timestamp for backup file
BACKUP_DATE=$(date +%Y%m%d)
BACKUP_TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="scholarship_db_backup_${BACKUP_TIMESTAMP}.dump"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_DATE}"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log "========================================="
log "Starting database backup process"
log "========================================="

# Create backup directory for today
mkdir -p "${BACKUP_PATH}"

# Setup secure password authentication using temporary .pgpass file
log "Setting up secure authentication..."
PGPASS_FILE="${HOME}/.pgpass.backup.$$"

# Create .pgpass file with error handling
if ! echo "${POSTGRES_HOST}:${POSTGRES_PORT}:${POSTGRES_DB}:${POSTGRES_USER}:${POSTGRES_PASSWORD}" > "${PGPASS_FILE}"; then
    log "ERROR: Failed to create password file"
    exit 1
fi

# Set secure permissions with error handling
if ! chmod 600 "${PGPASS_FILE}"; then
    log "ERROR: Failed to set secure permissions on password file"
    rm -f "${PGPASS_FILE}"
    exit 1
fi

# Export PGPASSFILE to use our temporary file
export PGPASSFILE="${PGPASS_FILE}"
log "Password file created with secure permissions"

# Check PostgreSQL connection
log "Testing database connection..."
if ! pg_isready -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; then
    log "ERROR: Cannot connect to PostgreSQL database"
    log "  Host: ${POSTGRES_HOST}:${POSTGRES_PORT}"
    log "  Database: ${POSTGRES_DB}"
    log "  User: ${POSTGRES_USER}"
    rm -f "${PGPASS_FILE}"
    exit 1
fi
log "Database connection successful"

# Create backup
log "Creating backup: ${BACKUP_FILE}"
log "  Database: ${POSTGRES_DB}"
log "  Format: Custom (compressed)"

if pg_dump \
    -h "${POSTGRES_HOST}" \
    -p "${POSTGRES_PORT}" \
    -U "${POSTGRES_USER}" \
    -d "${POSTGRES_DB}" \
    --format=custom \
    --compress=9 \
    --file="${BACKUP_PATH}/${BACKUP_FILE}" \
    --verbose 2>&1 >/dev/null; then

    # Verify backup file was created
    if [ -f "${BACKUP_PATH}/${BACKUP_FILE}" ]; then
        BACKUP_SIZE=$(du -h "${BACKUP_PATH}/${BACKUP_FILE}" | cut -f1)
        log "Backup created successfully: ${BACKUP_FILE} (${BACKUP_SIZE})"

        # Create checksum for integrity verification
        cd "${BACKUP_PATH}"
        sha256sum "${BACKUP_FILE}" > "${BACKUP_FILE}.sha256"
        log "Checksum created: ${BACKUP_FILE}.sha256"

        # Set appropriate permissions
        chmod 640 "${BACKUP_FILE}"
        chmod 640 "${BACKUP_FILE}.sha256"
        log "Permissions set: 640 (read-only for group)"
    else
        log "ERROR: Backup file was not created"
        rm -f "${PGPASS_FILE}"
        exit 1
    fi
else
    log "ERROR: pg_dump failed"
    rm -f "${PGPASS_FILE}"
    exit 1
fi

# Cleanup old backups
log "----------------------------------------"
log "Cleaning up old backups (retention: ${BACKUP_RETENTION_DAYS} days)"

# Calculate cutoff date (BusyBox compatible)
# BusyBox date doesn't support -d or -v, so we calculate manually
CUTOFF_DATE=$(date -d "${BACKUP_RETENTION_DAYS} days ago" +%Y%m%d 2>/dev/null || date -u -d "@$(($(date +%s) - ${BACKUP_RETENTION_DAYS} * 86400))" +%Y%m%d 2>/dev/null || date +%Y%m%d)
log "Cutoff date: ${CUTOFF_DATE}"

DELETED_COUNT=0
cd "${BACKUP_DIR}"

for backup_dir in */; do
    if [ -d "${backup_dir}" ]; then
        dir_date=${backup_dir%/}  # Remove trailing slash

        # Check if directory name is a valid date (8 digits)
        if echo "$dir_date" | grep -qE '^[0-9]{8}$'; then
            # Compare dates numerically
            if [ "$dir_date" -lt "$CUTOFF_DATE" ] 2>/dev/null; then
                log "Deleting old backup directory: ${dir_date}"
                rm -rf "${backup_dir}"
                DELETED_COUNT=$((DELETED_COUNT + 1))
            fi
        fi
    fi
done

if [ $DELETED_COUNT -eq 0 ]; then
    log "No old backups to delete"
else
    log "Deleted ${DELETED_COUNT} old backup directory(ies)"
fi

# Generate backup report
log "----------------------------------------"
log "Backup Summary"
log "----------------------------------------"

TOTAL_BACKUPS=$(find "${BACKUP_DIR}" -name "*.dump" | wc -l)
TOTAL_SIZE=$(du -sh "${BACKUP_DIR}" 2>/dev/null | cut -f1)

log "Total backup files: ${TOTAL_BACKUPS}"
log "Total storage used: ${TOTAL_SIZE}"
log "Latest backup: ${BACKUP_PATH}/${BACKUP_FILE}"

# List recent backups (last 7 days)
log ""
log "Recent backups (last 7 days):"
find "${BACKUP_DIR}" -name "*.dump" -mtime -7 -exec ls -lh {} \; | \
    awk '{printf "  %s %s %s - %s (%s)\n", $6, $7, $8, $9, $5}' | \
    head -n 10

log "========================================="
log "Backup completed successfully"
log "========================================="

# Cleanup password file
rm -f "${PGPASS_FILE}"

# Exit with success
exit 0
