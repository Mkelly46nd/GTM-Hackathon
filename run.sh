#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "Installing backend dependencies..."
pip install -q -r server/requirements.txt

echo "Installing frontend dependencies..."
cd web && npm install --silent
cd "$ROOT"

echo "Starting FastAPI backend on port 5000..."
uvicorn server.main:app --host 0.0.0.0 --port 5000 &
sleep 3

echo "Starting Next.js frontend on port ${PORT:-3000}..."
cd web && exec npm run dev -- -p "${PORT:-3000}"
