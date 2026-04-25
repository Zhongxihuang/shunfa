#!/usr/bin/env bash
# =============================================================================
# migrate_to_postgresql.sh
#
# One-time migration of the SQLite database to PostgreSQL.
# Run this ONCE, in the following order, before switching traffic.
#
# Prerequisites:
#   - PostgreSQL running (docker-compose up -d postgres)
#   - psycopg2-binary installed (pip install psycopg2-binary)
#   - Alembic installed
# =============================================================================

set -euo pipefail

# ── Config ──────────────────────────────────────────────────────────────────
POSTGRES_USER="${POSTGRES_USER:-shunfa}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-shunfa}"
POSTGRES_DB="${POSTGRES_DB:-shunfa}"
POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"

SQLITE_DB="${SQLITE_DB:-./shunfa.db}"
EXPORT_SQL="${EXPORT_SQL:-/tmp/shunfa_export.sql}"

# PostgreSQL connection string (used by Alembic and psql)
export DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"

echo "=== Shunfa: SQLite → PostgreSQL Migration ==="
echo "PostgreSQL: ${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
echo "SQLite:     ${SQLITE_DB}"
echo ""

# ── Step 0: Safety check ────────────────────────────────────────────────────
if [ ! -f "$SQLITE_DB" ]; then
    echo "ERROR: SQLite database not found at ${SQLITE_DB}"
    exit 1
fi

echo "[1/5] Checking PostgreSQL connectivity..."
if ! PGPASSWORD="$POSTGRES_PASSWORD" psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d postgres -c "SELECT 1" > /dev/null 2>&1; then
    echo "ERROR: Cannot connect to PostgreSQL at ${POSTGRES_HOST}:${POSTGRES_PORT}"
    echo "       Make sure PostgreSQL is running (docker-compose up -d postgres)"
    exit 1
fi
echo "      PostgreSQL OK"

# Create the database if it doesn't exist
echo "[2/5] Ensuring PostgreSQL database exists..."
PGPASSWORD="$POSTGRES_PASSWORD" psql -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" -d postgres -c \
    "SELECT 'CREATE DATABASE ${POSTGRES_DB}' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${POSTGRES_DB}')" 2>/dev/null || true
echo "      Database '${POSTGRES_DB}' ready"

# ── Step 3: Run Alembic migrations ──────────────────────────────────────────
echo "[3/5] Running Alembic migrations (creates tables in PostgreSQL)..."
alembic upgrade head
echo "      Migrations complete"

# ── Step 4: Export data from SQLite ─────────────────────────────────────────
echo "[4/5] Exporting data from SQLite..."
# Use SQLite's .dump to export all tables, then transform for PostgreSQL compatibility
sqlite3 "$SQLITE_DB" ".dump" > "$EXPORT_SQL"

# Remove SQLite-specific pragmas and沃·若普雷斯-specific constructs
sed -i '' \
    -e '/PRAGMA/d' \
    -e '/BEGIN TRANSACTION/d' \
    -e '/COMMIT/d' \
    -e 's/Integer PRIMARY KEY AUTOINCREMENT/ SERIAL PRIMARY KEY/g' \
    -e 's/BOOL (0|1)/BOOLEAN/g' \
    "$EXPORT_SQL" 2>/dev/null || \
sed \
    -e '/PRAGMA/d' \
    -e '/BEGIN TRANSACTION/d' \
    -e '/COMMIT/d' \
    -e 's/Integer PRIMARY KEY AUTOINCREMENT/ SERIAL PRIMARY KEY/g' \
    -e 's/BOOL (0|1)/BOOLEAN/g' \
    -i "$EXPORT_SQL"

echo "      Exported to ${EXPORT_SQL} (manual review recommended)"

# ── Step 5: Import into PostgreSQL ──────────────────────────────────────────
echo "[5/5] Importing data into PostgreSQL..."
echo "      NOTE: This script does NOT auto-import data."
echo "      For small datasets, manually run:"
echo "        PGPASSWORD='$POSTGRES_PASSWORD' psql -h $POSTGRES_HOST -p $POSTGRES_PORT -U $POSTGRES_USER -d $POSTGRES_DB < $EXPORT_SQL"
echo ""
echo "      For zero-downtime migration in production, use pgloader or a"
echo "      dual-write approach instead of this script."
echo ""
echo "=== Migration preparation complete ==="
echo ""
echo "Next steps:"
echo "  1. Review ${EXPORT_SQL} for data correctness"
echo "  2. Import: PGPASSWORD='$POSTGRES_PASSWORD' psql -h $POSTGRES_HOST -p $POSTGRES_PORT -U $POSTGRES_USER -d $POSTGRES_DB < $EXPORT_SQL"
echo "  3. Set in production: DATABASE_URL='postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}'"
echo "  4. Restart the backend service"
