#!/bin/bash
set -e

echo "Running database migrations..."
alembic upgrade head 2>/dev/null || echo "Alembic migration skipped (no versions yet)"

echo "Starting application..."
exec "$@"
