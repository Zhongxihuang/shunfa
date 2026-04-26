#!/usr/bin/env sh
set -eu

PORT="${PORT:-8080}"

echo "[start_prod] running alembic migrations"
alembic upgrade head

echo "[start_prod] starting uvicorn on port ${PORT}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
