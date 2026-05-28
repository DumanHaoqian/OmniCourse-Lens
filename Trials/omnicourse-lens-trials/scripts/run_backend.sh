#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHONPATH=backend uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8000}" --reload
