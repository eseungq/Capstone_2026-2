#!/usr/bin/env bash
set -Eeuo pipefail
project=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
mode=${1:-check}
[[ "$mode" == check || "$mode" == gpu-check || "$mode" == smoke || "$mode" == train || "$mode" == review ]] || { echo 'Usage: bash door_experiment/run_gpu.sh check|gpu-check|smoke|train|review'; exit 2; }
cd "$project"
experiment_config=${DOOR_EXPERIMENT_CONFIG:-$project/configs/door_visible_region_experiment_v1.json}
if [[ "$mode" != check && "$mode" != review && -z "${DOOR_EXPERIMENT_CONFIG:-}" ]]; then
  echo "Set DOOR_EXPERIMENT_CONFIG to the explicitly frozen experiment JSON"; exit 2
fi
experiment_config=$(realpath "$experiment_config")
mkdir -p outputs/door_next_runtime outputs/door_next_training outputs/door_next_cache outputs/door_next_review
run_id="$(date -u +%Y%m%dT%H%M%SZ)_$$"
log="$project/outputs/door_next_runtime/${mode}_${run_id}.log"
exec > >(tee -a "$log") 2>&1
printf '[LOG] %s\n' "$log"
trap 'rc=$?; printf "[DOOR PREP EXIT] code=%s\n" "$rc"' EXIT
python3 -m door_experiment.train --root "$project" --experiment-config "$experiment_config" --mode check
[[ "$mode" != check ]] || exit 0
exec 9>outputs/door_next_runtime/.gpu.lock
flock -n 9 || { echo 'Another DOOR experiment is active'; exit 1; }
docker_cmd=(docker)
if [[ "${DOOR_DOCKER_SUDO:-0}" == 1 ]]; then docker_cmd=(sudo docker); fi
"${docker_cmd[@]}" image inspect nvcr.io/nvidia/pytorch:25.11-py3 >/dev/null
cidfile="$project/outputs/door_next_runtime/${mode}_${run_id}.cid"
printf '[CIDFILE] %s\n' "$cidfile"
"${docker_cmd[@]}" run --rm -i --init --pull=never --gpus all --ipc=host \
 --name "door-next-${mode}-$run_id" --cidfile "$cidfile" \
 --user "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 \
 -e "DOOR_EXPERIMENT_CONFIG=$experiment_config" -e "DOOR_REVIEW_RUN=${DOOR_REVIEW_RUN:-$project/outputs/door_next_training/door_visible_20261028_065548_667023}" -e "DOOR_EXPERIMENT_MODE=$mode" -e "HF_HOME=$project/outputs/door_next_cache/huggingface" \
 -e "TORCH_HOME=$project/outputs/door_next_cache/torch" \
 -v "$project:$project:ro" -v "$project/outputs/door_next_cache:$project/outputs/door_next_cache:rw" \
 -v "$project/outputs/door_next_training:$project/outputs/door_next_training:rw" \
 -v "$project/outputs/door_next_review:$project/outputs/door_next_review:rw" \
 -w "$project" nvcr.io/nvidia/pytorch:25.11-py3 bash -se <<'CONTAINER'
python - <<'PY'
import importlib.metadata as m
import torch
for p,v in {'torch':'2.10.0a0+b558c986e8.nv25.11','torchvision':'0.25.0a0+7a13ad0f'}.items():
    if m.version(p)!=v: raise RuntimeError('Recorded GPU environment mismatch: '+p)
if not torch.cuda.is_available(): raise RuntimeError('CUDA unavailable')
print('GPU',torch.cuda.get_device_name(0))
PY
python -m pip install --no-deps --target /tmp/door-next-packages timm==1.0.30 Pillow==12.0.0 numpy==2.1.0
export PYTHONPATH=/tmp/door-next-packages:$PWD
if [[ "$DOOR_EXPERIMENT_MODE" == review ]]; then
  exec python -u -m door_experiment.review --run "$DOOR_REVIEW_RUN"
fi
if [[ "$DOOR_EXPERIMENT_MODE" == train ]]; then
  exec python -u -m door_experiment.train --root "$PWD" --experiment-config "$DOOR_EXPERIMENT_CONFIG" --mode train --start-training
fi
exec python -u -m door_experiment.train --root "$PWD" --experiment-config "$DOOR_EXPERIMENT_CONFIG" --mode "$DOOR_EXPERIMENT_MODE"
CONTAINER
