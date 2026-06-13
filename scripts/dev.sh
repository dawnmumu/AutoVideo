#!/usr/bin/env bash
set -euo pipefail

export AUTOVIDEO_HOST="${AUTOVIDEO_HOST:-0.0.0.0}"
export AUTOVIDEO_PORT="${AUTOVIDEO_PORT:-8090}"
export AUTOVIDEO_DATA_DIR="${AUTOVIDEO_DATA_DIR:-./data}"

"${PYTHON_BIN:-python}" -m autovideo.main
