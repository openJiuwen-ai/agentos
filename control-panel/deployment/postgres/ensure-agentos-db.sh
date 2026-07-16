#!/bin/bash
set -e

# Start official postgres entrypoint in background
/usr/local/bin/docker-entrypoint.sh postgres &
PG_PID=$!

# Wait until postgres is ready
until pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_USER}" 2>/dev/null; do
    sleep 1
done

# Create agentos database if it doesn't exist (idempotent)
if ! psql -U "${POSTGRES_USER}" -d "${POSTGRES_USER}" -tAc \
    "SELECT 1 FROM pg_database WHERE datname = 'agentos'" | grep -q 1; then
    psql -U "${POSTGRES_USER}" -d "${POSTGRES_USER}" -c "CREATE DATABASE agentos"
    echo "[ensure-agentos-db] Created agentos database."
else
    echo "[ensure-agentos-db] agentos database already exists."
fi

# Create litellm database if it doesn't exist (idempotent)
if ! psql -U "${POSTGRES_USER}" -d "${POSTGRES_USER}" -tAc \
    "SELECT 1 FROM pg_database WHERE datname = 'litellm'" | grep -q 1; then
    psql -U "${POSTGRES_USER}" -d "${POSTGRES_USER}" -c "CREATE DATABASE litellm"
    echo "[ensure-agentos-db] Created litellm database."
else
    echo "[ensure-agentos-db] litellm database already exists."
fi

# Bring postgres back to foreground
wait $PG_PID
