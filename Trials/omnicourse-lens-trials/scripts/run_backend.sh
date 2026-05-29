#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHONPATH=backend uvicorn app.main:app --host "${BACKEND_HOST:-0.0.0.0}" --port "${PORT:-8000}" --reload
