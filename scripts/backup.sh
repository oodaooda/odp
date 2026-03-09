#!/usr/bin/env bash
# ODP Backup Script
# Dumps Postgres database + tars runtime artifacts.
# Usage: ./scripts/backup.sh [backup_dir]
set -euo pipefail

BACKUP_DIR="${1:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DEST="${BACKUP_DIR}/${TIMESTAMP}"

DB_URL="${ODP_DATABASE_URL:-postgresql://odp:odp@localhost:5432/odp}"
ARTIFACT_DIR="${ODP_ARTIFACT_DIR:-runtime/artifacts}"

mkdir -p "${DEST}"

echo "==> Backing up to ${DEST}"

# 1. Postgres dump
echo "  Dumping Postgres..."
pg_dump "${DB_URL}" --format=custom --file="${DEST}/odp_db.dump" 2>/dev/null || \
  pg_dump "postgresql://odp:odp@localhost:5432/odp" --format=custom --file="${DEST}/odp_db.dump"
echo "  Database dump: ${DEST}/odp_db.dump"

# 2. Artifacts tarball
if [ -d "${ARTIFACT_DIR}" ]; then
  echo "  Archiving artifacts..."
  tar czf "${DEST}/artifacts.tar.gz" -C "$(dirname "${ARTIFACT_DIR}")" "$(basename "${ARTIFACT_DIR}")"
  echo "  Artifacts archive: ${DEST}/artifacts.tar.gz"
else
  echo "  No artifact directory found at ${ARTIFACT_DIR}; skipping."
fi

# 3. Metadata
echo "{\"timestamp\":\"${TIMESTAMP}\",\"db_url\":\"${DB_URL}\",\"artifact_dir\":\"${ARTIFACT_DIR}\"}" \
  > "${DEST}/backup_meta.json"

echo "==> Backup complete: ${DEST}"
ls -lh "${DEST}/"
