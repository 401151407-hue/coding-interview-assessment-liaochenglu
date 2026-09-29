#!/usr/bin/env bash
# Optional convenience script: start the API and the frontend dev server together.
# Usage:  bash app/run-dev.sh
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -d "$root/frontend/node_modules" ]; then
  echo "Installing frontend dependencies..."
  (cd "$root/frontend" && npm install)
fi

cleanup() {
  echo ""
  echo "Stopping services..."
  kill 0 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Starting API on http://127.0.0.1:8000 ..."
(cd "$root/backend" && python -m uvicorn backend.main:app --reload --port 8000) &

echo "Starting frontend on http://127.0.0.1:5173 ..."
(cd "$root/frontend" && npm run dev) &

wait
