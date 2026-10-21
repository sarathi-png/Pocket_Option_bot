#!/usr/bin/env bash
# Start backend + frontend for local development (Ctrl+C stops both).
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -x .venv/bin/python ]; then
  echo "Run 'make install' first." >&2
  exit 1
fi

(cd backend && ../.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000) &
BACKEND_PID=$!
trap 'kill $BACKEND_PID 2>/dev/null || true' EXIT INT TERM

npm --prefix frontend run dev
