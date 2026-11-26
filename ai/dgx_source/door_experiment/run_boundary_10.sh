#!/usr/bin/env bash
set -Eeuo pipefail
project=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project"
mkdir -p outputs/door_next_runtime outputs/door_boundary_review outputs/door_next_cache
run_id="$(date -u +%Y%m%dT%H%M%SZ)_$$"
log="$project/outputs/door_next_runtime/boundary_${run_id}.log"
cidfile="$project/outputs/door_next_runtime/boundary_${run_id}.cid"
exec > >(tee -a "$log") 2>&1
printf '[LOG] %s\n[CIDFILE] %s\n' "$log" "$cidfile"
trap 'rc=$?; printf "[BOUNDARY EXIT] code=%s\n" "$rc"' EXIT
python3 -m door_experiment.prepare_model_review --run "$project/outputs/door_next_training/door_visible_20261029_162657_477520"
exec 9>outputs/door_next_runtime/.gpu.lock
flock -n 9 || { echo 'Another DOOR GPU task is active'; exit 1; }
docker_cmd=(docker)
if [[ "${DOOR_DOCKER_SUDO:-0}" == 1 ]]; then docker_cmd=(sudo docker); fi
"${docker_cmd[@]}" image inspect nvcr.io/nvidia/pytorch:25.11-py3 >/dev/null
"${docker_cmd[@]}" run --rm -i --init --pull=never --gpus all --ipc=host \
 --name "door-boundary-$run_id" --cidfile "$cidfile" \
 --user "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 \
 -v "$project:$project:ro" \
 -v "$project/outputs/door_boundary_review:$project/outputs/door_boundary_review:rw" \
 -w "$project" nvcr.io/nvidia/pytorch:25.11-py3 bash -se <<'CONTAINER'
python -m pip install --no-deps --target /tmp/door-boundary-packages timm==1.0.30 Pillow==12.0.0 numpy==2.1.0
export PYTHONPATH=/tmp/door-boundary-packages:$PWD
exec python -u -m door_experiment.boundary_review --report "$PWD/outputs/door_next_review/20261030T020059_489653Z/report.json"
CONTAINER
