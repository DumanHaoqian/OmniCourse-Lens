#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python scripts/create_demo_data.py
python scripts/rebuild_index.py
PORT="${PORT:-8000}" scripts/run_backend.sh &
backend_pid=$!
trap 'kill $backend_pid 2>/dev/null || true' EXIT
sleep 2
BACKEND_PORT="$PORT" scripts/run_frontend.sh
