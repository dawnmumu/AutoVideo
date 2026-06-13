#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

export AUTOVIDEO_HOST="${AUTOVIDEO_HOST:-0.0.0.0}"
export AUTOVIDEO_PORT="${AUTOVIDEO_PORT:-8090}"
export AUTOVIDEO_DATA_DIR="${AUTOVIDEO_DATA_DIR:-./data}"

cd "${REPO_ROOT}"

"${PYTHON_BIN:-python}" -m autovideo.main
