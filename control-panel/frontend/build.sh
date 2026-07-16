#!/usr/bin/env bash

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================"
echo " AgentOS Frontend Build"
echo "========================================"
echo ""

echo "[1/3] Checking Node.js..."
if ! command -v node &> /dev/null; then
  echo "error: node not found" >&2
  exit 1
fi
if ! command -v npm &> /dev/null; then
  echo "error: npm not found" >&2
  exit 1
fi
echo "  node $(node -v), npm $(npm -v)"

echo "[2/3] Installing dependencies..."
npm ci

echo "[3/3] Building..."
npm run build

echo ""
echo "========================================"
echo " Done: $SCRIPT_DIR/dist"
echo "========================================"
