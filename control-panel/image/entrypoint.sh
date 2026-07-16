#!/bin/bash
set -e

export PATH="/opt/agentos/backend/.venv/bin:$PATH"
export PYTHONPATH="/opt/agentos/backend"

echo "[entrypoint] Starting backend on :8000..."
/opt/agentos/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir /opt/agentos/backend &
BACKEND_PID=$!

# Wait for backend to be ready
echo "[entrypoint] Waiting for backend..."
for i in $(seq 1 30); do
    if curl -s http://127.0.0.1:8000/health > /dev/null 2>&1; then
        echo "[entrypoint] Backend is ready."
        break
    fi
    sleep 1
done

echo "[entrypoint] Starting nginx..."
nginx

echo "[entrypoint] All services started."
wait $BACKEND_PID
