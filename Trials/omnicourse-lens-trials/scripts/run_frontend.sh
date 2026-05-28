#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../frontend"
export VITE_API_BASE="${VITE_API_BASE:-http://localhost:${BACKEND_PORT:-8000}}"
npm run dev -- --host 127.0.0.1 --port "${FRONTEND_PORT:-5173}"
