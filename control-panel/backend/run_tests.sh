#!/usr/bin/env bash
# AgentOS Backend - One-click Test Script (Linux/macOS)
# Usage: ./run_tests.sh [--coverage]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo " AgentOS Backend Test Runner"
echo "========================================"
echo ""

# Step 1: Check uv
echo "[1/3] Checking uv..."
if ! command -v uv &> /dev/null; then
    echo "  uv not found. Installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
echo "  uv OK"

# Step 2: Sync dependencies
echo "[2/3] Syncing dependencies..."
uv sync --dev 2>&1 > /dev/null
echo "  Dependencies OK"

# Step 3: Run tests
echo "[3/3] Running tests..."
echo ""

if [ "$1" = "--coverage" ]; then
    uv run pytest tests/ -v --tb=short --cov=app --cov-report=term-missing
else
    uv run pytest tests/ -v --tb=short
fi

echo ""
echo "========================================"
echo " Done!"
echo "========================================"
