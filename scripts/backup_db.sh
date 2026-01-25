#!/bin/bash
# GameSpace Database Backup Script
#
# Usage:
#   ./scripts/backup_db.sh [output_dir]
#
# Environment variables:
#   DATABASE_URL - PostgreSQL connection string (required)
#   BACKUP_RETENTION_DAYS - Days to keep old backups (default: 7)
#
# Examples:
#   # Basic backup
#   DATABASE_URL=postgresql://... ./scripts/backup_db.sh
#
#   # Custom output directory
#   DATABASE_URL=postgresql://... ./scripts/backup_db.sh /path/to/backups

set -euo pipefail

# Configuration
OUTPUT_DIR="${1:-./backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILENAME="gamespace_backup_${TIMESTAMP}.sql.gz"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check required environment variable
if [ -z "${DATABASE_URL:-}" ]; then
    log_error "DATABASE_URL environment variable is required"
    echo "Usage: DATABASE_URL=postgresql://... $0 [output_dir]"
    exit 1
fi

# Create output directory if it doesn't exist
mkdir -p "${OUTPUT_DIR}"

log_info "Starting database backup..."
log_info "Output directory: ${OUTPUT_DIR}"
log_info "Backup filename: ${BACKUP_FILENAME}"

# Perform backup using pg_dump
# The --no-owner and --no-acl flags make the backup portable
log_info "Dumping database..."
if pg_dump "${DATABASE_URL}" \
    --no-owner \
    --no-acl \
    --clean \
    --if-exists \
    --format=plain \
    | gzip > "${OUTPUT_DIR}/${BACKUP_FILENAME}"; then

    BACKUP_SIZE=$(du -h "${OUTPUT_DIR}/${BACKUP_FILENAME}" | cut -f1)
    log_info "Backup completed successfully!"
    log_info "Backup size: ${BACKUP_SIZE}"
else
    log_error "Backup failed!"
    exit 1
fi

# Cleanup old backups
if [ "${RETENTION_DAYS}" -gt 0 ]; then
    log_info "Cleaning up backups older than ${RETENTION_DAYS} days..."
    DELETED_COUNT=$(find "${OUTPUT_DIR}" -name "gamespace_backup_*.sql.gz" -type f -mtime +${RETENTION_DAYS} -delete -print | wc -l)
    if [ "${DELETED_COUNT}" -gt 0 ]; then
        log_info "Deleted ${DELETED_COUNT} old backup(s)"
    fi
fi

# List current backups
log_info "Current backups:"
ls -lh "${OUTPUT_DIR}"/gamespace_backup_*.sql.gz 2>/dev/null || log_warn "No backups found"

# Output the backup path for scripts to use
echo ""
echo "BACKUP_PATH=${OUTPUT_DIR}/${BACKUP_FILENAME}"
