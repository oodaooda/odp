#!/usr/bin/env bash
# ODP Restore Script
# Restores Postgres database + runtime artifacts from a backup.
# Usage: ./scripts/restore.sh <backup_dir>
set -euo pipefail

BACKUP_DIR="${1:?Usage: restore.sh <backup_dir>}"
DB_URL="${ODP_DATABASE_URL:-postgresql://odp:odp@localhost:5432/odp}"
ARTIFACT_DIR="${ODP_ARTIFACT_DIR:-runtime/artifacts}"

if [ ! -d "${BACKUP_DIR}" ]; then
  echo "ERROR: Backup directory not found: ${BACKUP_DIR}"
  exit 1
fi

echo "==> Restoring from ${BACKUP_DIR}"

# 1. Postgres restore
DB_DUMP="${BACKUP_DIR}/odp_db.dump"
if [ -f "${DB_DUMP}" ]; then
  echo "  Restoring database..."
  pg_restore --dbname="${DB_URL}" --clean --if-exists --no-owner "${DB_DUMP}" 2>/dev/null || \
    pg_restore --dbname="postgresql://odp:odp@localhost:5432/odp" --clean --if-exists --no-owner "${DB_DUMP}"
  echo "  Database restored."
else
  echo "  WARNING: No database dump found at ${DB_DUMP}"
fi

# 2. Artifacts
ARTIFACTS_TAR="${BACKUP_DIR}/artifacts.tar.gz"
if [ -f "${ARTIFACTS_TAR}" ]; then
  echo "  Restoring artifacts..."
  mkdir -p "$(dirname "${ARTIFACT_DIR}")"
  tar xzf "${ARTIFACTS_TAR}" -C "$(dirname "${ARTIFACT_DIR}")"
  echo "  Artifacts restored to ${ARTIFACT_DIR}"
else
  echo "  No artifacts archive found; skipping."
fi

echo "==> Restore complete."
