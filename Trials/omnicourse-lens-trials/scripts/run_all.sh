#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python scripts/create_demo_data.py
python scripts/rebuild_index.py
python scripts/run_backend.sh
