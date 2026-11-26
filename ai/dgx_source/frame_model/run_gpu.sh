#!/usr/bin/env bash
set -Eeuo pipefail
project=/path/to/private/validated-project
mode=${1:-check}
[[ "$mode" == check || "$mode" == benchmark || "$mode" == smoke || "$mode" == train || "$mode" == compare-smoke || "$mode" == compare-train || "$mode" == cam || "$mode" == cam-probe ]] || { echo 'Usage: bash frame_model/run_gpu.sh check|benchmark|smoke|train|compare-smoke|compare-train|cam|cam-probe'; exit 2; }
mkdir -p "$project/outputs/frame_runtime" "$project/outputs/frame_checks" "$project/outputs/frame_training" "$project/outputs/frame_cache" "$project/outputs/frame_cam_review" "$project/outputs/frame_cam_diagnosis"
run_id="$(date -u +%Y%m%dT%H%M%SZ)_$$"
log="$project/outputs/frame_runtime/${mode}_${run_id}.log"
cidfile="$project/outputs/frame_runtime/${mode}_${run_id}.cid"
exec > >(tee -a "$log") 2>&1
printf '[LOG] %s\n[CIDFILE] %s\n' "$log" "$cidfile"
trap 'rc=$?; printf "[FRAME EXIT] code=%s\n" "$rc"' EXIT
exec 9>"$project/outputs/frame_runtime/.gpu.lock"
flock -n 9 || { echo 'Another frame check is active'; exit 1; }
if [[ "$mode" == compare-* ]]; then
  if [[ -z "${FRAME_EXPERIMENT_PLAN:-}" ]]; then
    FRAME_EXPERIMENT_PLAN=$(python3 -c 'import json; print(json.load(open("frame_model/latest_experiment_plan.json"))["plan"])')
  fi
  FRAME_EXPERIMENT_PLAN=$(realpath "$FRAME_EXPERIMENT_PLAN")
  python3 -m frame_model.experiments --plan "$FRAME_EXPERIMENT_PLAN" --mode validate
else
  FRAME_EXPERIMENT_PLAN=""
fi
if [[ "$mode" == cam || "$mode" == cam-probe ]]; then
  if [[ -z "${FRAME_CAM_SELECTION:-}" ]]; then
    FRAME_CAM_SELECTION=$(python3 -c 'import json; print(json.load(open("frame_model/latest_cam_review.json"))["selection"])')
  fi
  FRAME_CAM_SELECTION=$(realpath "$FRAME_CAM_SELECTION")
else
  FRAME_CAM_SELECTION=""
fi
if [[ "$mode" == cam-probe ]]; then
  if [[ -z "${FRAME_CAM_PROBE:-}" ]]; then
    FRAME_CAM_PROBE=$(python3 -c 'import json; print(json.load(open("frame_model/latest_cam_probe.json"))["plan"])')
  fi
  FRAME_CAM_PROBE=$(realpath "$FRAME_CAM_PROBE")
else
  FRAME_CAM_PROBE=""
fi
docker_cmd=(docker)
if [[ "${FRAME_DOCKER_SUDO:-0}" == 1 ]]; then docker_cmd=(sudo docker); fi
"${docker_cmd[@]}" image inspect nvcr.io/nvidia/pytorch:25.11-py3 >/dev/null
"${docker_cmd[@]}" run --rm -i --init --pull=never --gpus all --ipc=host \
  --name "frame-prepare-$run_id" --cidfile "$cidfile" \
  --user "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 \
  -e "FRAME_MODE=$mode" -e "FRAME_CAM_PROBE=$FRAME_CAM_PROBE" -e "FRAME_CAM_SELECTION=$FRAME_CAM_SELECTION" -e "FRAME_EXPERIMENT_PLAN=$FRAME_EXPERIMENT_PLAN" -e "HF_HOME=$project/outputs/frame_cache/huggingface" -e "TORCH_HOME=$project/outputs/frame_cache/torch" -v "$project:$project:ro" \
  -v "$project/outputs/frame_checks:$project/outputs/frame_checks:rw" \
  -v "$project/outputs/frame_training:$project/outputs/frame_training:rw" \
  -v "$project/outputs/frame_cache:$project/outputs/frame_cache:rw" \
  -v "$project/outputs/frame_cam_review:$project/outputs/frame_cam_review:rw" \
  -v "$project/outputs/frame_cam_diagnosis:$project/outputs/frame_cam_diagnosis:rw" \
  -w "$project" nvcr.io/nvidia/pytorch:25.11-py3 bash -se <<'CONTAINER'
set -Eeuo pipefail
python - <<'PY'
import importlib.metadata as m
import torch
for package, expected in {'torch':'2.10.0a0+b558c986e8.nv25.11','torchvision':'0.25.0a0+7a13ad0f'}.items():
    actual=m.version(package)
    print(package, actual)
    if actual!=expected: raise RuntimeError('GPU environment differs from recorded versions')
if not torch.cuda.is_available(): raise RuntimeError('CUDA unavailable')
print('GPU',torch.cuda.get_device_name(0))
PY
python -m pip install --no-deps --target /tmp/frame-packages timm==1.0.30 Pillow==12.0.0 numpy==2.1.0
export PYTHONPATH=/tmp/frame-packages:$PWD
if [[ "$FRAME_MODE" == cam-probe ]]; then
  exec python -u -m frame_model.cam_objective_probe --plan "$FRAME_CAM_PROBE"
elif [[ "$FRAME_MODE" == cam ]]; then
  exec python -u -m frame_model.cam_review --selection "$FRAME_CAM_SELECTION" --diagnostic-good-cam
elif [[ "$FRAME_MODE" == compare-smoke ]]; then
  exec python -u -m frame_model.experiments --plan "$FRAME_EXPERIMENT_PLAN" --mode smoke
elif [[ "$FRAME_MODE" == compare-train ]]; then
  exec python -u -m frame_model.experiments --plan "$FRAME_EXPERIMENT_PLAN" --mode train --start-training
elif [[ "$FRAME_MODE" == smoke ]]; then
  exec python -u -m frame_model.train --mode smoke
elif [[ "$FRAME_MODE" == train ]]; then
  exec python -u -m frame_model.train --mode train --start-training
else
  exec python -u -m frame_model.check --mode "$FRAME_MODE" --steps 10
fi
CONTAINER
