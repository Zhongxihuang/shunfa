#!/usr/bin/env bash
# =============================================================================
# 顺发数据库备份脚本
# 每天凌晨 3:00 通过系统 cron 运行：
#   0 3 * * * /path/to/backend/scripts/backup.sh
#
# 环境变量（可选）：
#   BACKUP_DIR     备份存储目录（默认：/var/backups/shunfa）
#   DB_PATH        SQLite 数据库路径（默认：/path/to/backend/shunfa.db）
#   BACKUP_S3_BUCKET  OSS/S3 bucket 名称（如设置了则自动上传）
#   RETENTION_DAYS  保留天数（默认：7）
# =============================================================================

set -euo pipefail

# ── Config ───────────────────────────────────────────────────────────────────
BACKUP_DIR="${BACKUP_DIR:-/var/backups/shunfa}"
DB_PATH="${DB_PATH:-$(dirname "$0")/../shunfa.db}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/shunfa_backup_${TIMESTAMP}.db"

# ── Guard ────────────────────────────────────────────────────────────────────
if [[ ! -f "$DB_PATH" ]]; then
    echo "[backup] ERROR: database not found at $DB_PATH"
    exit 1
fi

mkdir -p "$BACKUP_DIR"

# ── Backup ───────────────────────────────────────────────────────────────────
# Use SQLite VACUUM INTO to create a consistent, compressed backup without
# blocking reads on the main database.
echo "[backup] Starting backup of $DB_PATH → $BACKUP_FILE"
sqlite3 "$DB_PATH" "VACUUM INTO '${BACKUP_FILE}'"

# Compress to save space
gzip "$BACKUP_FILE"
COMPRESSED_FILE="${BACKUP_FILE}.gz"
echo "[backup] Compressed → ${COMPRESSED_FILE} ($(du -sh "$COMPRESSED_FILE" | cut -f1))"

# ── Upload to OSS/S3 (optional) ──────────────────────────────────────────────
if [[ -n "${BACKUP_S3_BUCKET:-}" ]]; then
    echo "[backup] Uploading to s3://${BACKUP_S3_BUCKET}/"
    if command -v aws &> /dev/null; then
        aws s3 cp "$COMPRESSED_FILE" "s3://${BACKUP_S3_BUCKET}/shunfa_backup_${TIMESTAMP}.db.gz"
    elif command -v ossutil &> /dev/null; then
        ossutil cp "$COMPRESSED_FILE" "oss://${BACKUP_S3_BUCKET}/shunfa_backup_${TIMESTAMP}.db.gz"
    else
        echo "[backup] WARNING: BACKUP_S3_BUCKET set but neither aws nor ossutil found, skipping upload"
    fi
fi

# ── Cleanup old backups ───────────────────────────────────────────────────────
DELETED_COUNT=0
while IFS= read -r old_backup; do
    rm -f "$old_backup"
    DELETED_COUNT=$((DELETED_COUNT + 1))
    echo "[backup] Removed old backup: $old_backup"
done < <(find "$BACKUP_DIR" -name "shunfa_backup_*.db.gz" -mtime +"$RETENTION_DAYS" 2>/dev/null)

echo "[backup] Done. Created ${COMPRESSED_FILE}, removed ${DELETED_COUNT} old backup(s)."
