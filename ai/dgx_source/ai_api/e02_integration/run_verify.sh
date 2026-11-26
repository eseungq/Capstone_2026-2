#!/usr/bin/env bash
set -Eeuo pipefail
project=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$project"
mkdir -p outputs/door_e02_integration_runtime outputs/door_e02_integration_http outputs/door_next_runtime
run_id="$(date -u +%Y%m%dT%H%M%SZ)_$$"
log="$project/outputs/door_e02_integration_runtime/verify_${run_id}.log"
cidfile="$project/outputs/door_e02_integration_runtime/verify_${run_id}.cid"
exec > >(tee -a "$log") 2>&1
printf '[E02 HTTP LAUNCH]\n[LOG] %s\n[CIDFILE] %s\n' "$log" "$cidfile"
trap 'rc=$?; printf "[E02 HTTP EXIT] code=%s\n" "$rc"' EXIT
python3 - <<'PY'
from ai_api.e02_engine import validate_candidate
manifest,_,_=validate_candidate()
print('[E02 CPU READY]',manifest['modelVersion'],manifest['checkpointSHA256'])
PY
PYTHONDONTWRITEBYTECODE=1 python3 -m ai_api.e02_integration.verify_stub_http
exec 9>outputs/door_next_runtime/.gpu.lock
flock -n 9 || { echo 'Another DOOR GPU experiment is active'; exit 1; }
docker_cmd=(docker)
if [[ "${DOOR_DOCKER_SUDO:-0}" == 1 ]]; then docker_cmd=(sudo docker); fi
"${docker_cmd[@]}" image inspect nvcr.io/nvidia/pytorch:25.11-py3 >/dev/null
"${docker_cmd[@]}" run --rm -i --init --pull=never --gpus all --ipc=host \
 --name "door-e02-integration-$run_id" --cidfile "$cidfile" \
 --user "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 \
 -v "$project:$project:ro" \
 -v "$project/outputs/door_e02_integration_http:$project/outputs/door_e02_integration_http:rw" \
 -w "$project" nvcr.io/nvidia/pytorch:25.11-py3 bash -se <<'CONTAINER'
python -m pip install --no-deps --target /tmp/door-e02-packages timm==1.0.30 Pillow==12.0.0 numpy==2.1.0
export PYTHONPATH=/tmp/door-e02-packages:$PWD
exec python -u -m ai_api.e02_integration.verify_http
CONTAINER
