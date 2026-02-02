#!/bin/bash
# BenchGoblins Database Restore Script
#
# Usage:
#   ./scripts/restore_db.sh <backup_file>
#
# Environment variables:
#   DATABASE_URL - PostgreSQL connection string (required)
#
# Examples:
#   DATABASE_URL=postgresql://... ./scripts/restore_db.sh backups/benchgoblins_backup_20260125_120000.sql.gz

set -euo pipefail

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

# Check arguments
if [ $# -lt 1 ]; then
    log_error "Backup file is required"
    echo "Usage: DATABASE_URL=postgresql://... $0 <backup_file>"
    exit 1
fi

BACKUP_FILE="$1"

# Check required environment variable
if [ -z "${DATABASE_URL:-}" ]; then
    log_error "DATABASE_URL environment variable is required"
    echo "Usage: DATABASE_URL=postgresql://... $0 <backup_file>"
    exit 1
fi

# Check backup file exists
if [ ! -f "${BACKUP_FILE}" ]; then
    log_error "Backup file not found: ${BACKUP_FILE}"
    exit 1
fi

log_warn "This will REPLACE all data in the database!"
log_warn "Backup file: ${BACKUP_FILE}"
read -p "Are you sure you want to continue? (yes/no): " CONFIRM

if [ "${CONFIRM}" != "yes" ]; then
    log_info "Restore cancelled"
    exit 0
fi

log_info "Starting database restore..."

# Restore from backup
if [[ "${BACKUP_FILE}" == *.gz ]]; then
    log_info "Decompressing and restoring from gzipped backup..."
    if gunzip -c "${BACKUP_FILE}" | psql "${DATABASE_URL}"; then
        log_info "Restore completed successfully!"
    else
        log_error "Restore failed!"
        exit 1
    fi
else
    log_info "Restoring from backup..."
    if psql "${DATABASE_URL}" < "${BACKUP_FILE}"; then
        log_info "Restore completed successfully!"
    else
        log_error "Restore failed!"
        exit 1
    fi
fi

log_info "Database restore complete!"
