#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_BIN="${INTERNVIDEO3_PYTHON:-/home/haoqian/miniconda3/envs/omniC/bin/python}"
MODEL_PATH="${INTERNVIDEO3_MODEL_PATH:-/home/haoqian/Data/OmniCourse-Lens/Trials/checkpoints/InternVideo3-8B-Instruct}"
HOST="${INTERNVIDEO3_HOST:-127.0.0.1}"
PORT="${INTERNVIDEO3_PORT:-8011}"

exec "$PYTHON_BIN" scripts/internvideo3_server.py \
  --model-path "$MODEL_PATH" \
  --host "$HOST" \
  --port "$PORT"
