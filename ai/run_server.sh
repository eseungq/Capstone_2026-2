#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
: "${AI_PROJECT_ROOT:?Set the existing private validated project root}"
: "${BACKEND_ORIGIN:?Set the allowed backend image origin, including its port}"
export PYTHONDONTWRITEBYTECODE=1
python tools/verify_source.py
runtime="${AI_RUNTIME_DIR:-$AI_PROJECT_ROOT/outputs/door_e02_live/requests}"
gpu_lock="${AI_GPU_LOCK:-$AI_PROJECT_ROOT/outputs/door_next_runtime/.gpu.lock}"
exec python -u -m ai_api.e02_integration.serve --host 0.0.0.0 --port "${AI_PORT:-8771}" --image-origin "$BACKEND_ORIGIN" --runtime "$runtime" --gpu-lock "$gpu_lock"
