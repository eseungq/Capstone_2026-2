#!/usr/bin/env bash
set -Eeuo pipefail
project=/path/to/private/validated-project
training=/path/to/private-user/다운로드/도어_SwinTiny_DGX_학습_20261009
mode=${1:-serve}
[[ "$mode" == serve || "$mode" == verify || "$mode" == diagnose || "$mode" == focused || "$mode" == integration || "$mode" == backend-verify ]] || { echo 'Usage: bash ai_api/run_gpu.sh serve|verify|diagnose|focused|integration|backend-verify'; exit 2; }
: "${DOOR_API_MODEL_VERSION:?Set an explicit model identifier; verify may use an UNREGISTERED development identifier}"
[[ "${DOOR_API_DEVELOPMENT_CONTRACT:-0}" == 1 ]] || { echo 'v4 schema is pending: explicitly set DOOR_API_DEVELOPMENT_CONTRACT=1 for development only'; exit 2; }
docker_cmd=(docker)
if [[ "${DOOR_DOCKER_SUDO:-0}" == 1 ]]; then docker_cmd=(sudo docker); fi
mkdir -p "$project/ai_api/runtime" "$project/ai_api/verification"
run_id="$(date -u +%Y%m%dT%H%M%SZ)_$$"
log="$project/ai_api/runtime/${mode}_${run_id}.log"
cidfile="$project/ai_api/runtime/${mode}_${run_id}.cid"
exec > >(tee -a "$log") 2>&1
printf '[LAUNCH] mode=%s\n[LOG] %s\n[CIDFILE] %s\n' "$mode" "$log" "$cidfile"
trap 'rc=$?; printf "[LAUNCH EXIT] code=%s\n" "$rc"' EXIT
exec 9>"$project/ai_api/runtime/.${mode}.lock"
flock -n 9 || { echo 'Another API launch of this mode is active'; exit 1; }
"${docker_cmd[@]}" image inspect nvcr.io/nvidia/pytorch:25.11-py3 >/dev/null
args=(--rm -i --init --name "door-ai-api-${mode}" --pull=never --gpus all --ipc=host
  --cidfile "$cidfile"
  --user "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1
  -e "DOOR_API_MODEL_VERSION=$DOOR_API_MODEL_VERSION" -e "DOOR_API_MODE=$mode"
  -v "$project:$project:ro" -v "$training:$training:ro"
  -v "$project/ai_api/runtime:$project/ai_api/runtime:rw"
  -v "$project/ai_api/verification:$project/ai_api/verification:rw" -w "$project")
if [[ "$mode" == serve || "$mode" == backend-verify ]]; then
  args+=(-e "DOOR_API_CAM_FORMAT=${DOOR_API_CAM_FORMAT:-png}" -e "DOOR_API_JPEG_QUALITY=${DOOR_API_JPEG_QUALITY:-90}")
fi
if [[ "$mode" == diagnose && -n "${DOOR_API_REUSE_HTTP_REPORT:-}" ]]; then
  args+=(-e "DOOR_API_REUSE_HTTP_REPORT=$DOOR_API_REUSE_HTTP_REPORT")
fi
if [[ "$mode" == diagnose && -n "${DOOR_API_SELECTION_FILE:-}" ]]; then
  args+=(-e "DOOR_API_SELECTION_FILE=$DOOR_API_SELECTION_FILE")
fi
if [[ "$mode" == serve ]]; then
  : "${DOOR_API_IMAGE_ORIGIN:?Set exact image origin reachable FROM the container, e.g. http://192.168.0.20:8080}"
  args+=(-e "DOOR_API_IMAGE_ORIGIN=$DOOR_API_IMAGE_ORIGIN"
    -e "DOOR_API_RESPONSE_PROFILE=${DOOR_API_RESPONSE_PROFILE:-development-proposal-v4-pending}" -p 127.0.0.1:8770:8770)
fi
if [[ "$mode" == focused ]]; then
  : "${DOOR_API_ROI_FILE:?Set the prepared human ROI JSON path}"
  args+=(-e "DOOR_API_ROI_FILE=$DOOR_API_ROI_FILE")
fi
if [[ "$mode" == serve && -n "${DOOR_API_SESSION_RECORD:-}" ]]; then
  python3 - "$DOOR_API_SESSION_RECORD" "$cidfile" "$DOOR_API_MODEL_VERSION" <<'SESSION'
import json, os, sys
from pathlib import Path
path=Path(sys.argv[1]);path.parent.mkdir(parents=True,exist_ok=True)
record={'cidfile':sys.argv[2],'modelVersion':sys.argv[3],
        'responseProfile':os.environ.get('DOOR_API_RESPONSE_PROFILE','development-proposal-v4-pending'),
        'launcherPid':os.getppid(),'scope':'owned-development-serve-launch'}
temp=path.with_suffix('.tmp');temp.write_text(json.dumps(record)+'\n');temp.replace(path)
SESSION
fi
"${docker_cmd[@]}" run "${args[@]}" nvcr.io/nvidia/pytorch:25.11-py3 bash -se <<'CONTAINER'
set -Eeuo pipefail
python -u - <<'PY'
import importlib.metadata as m
import torch
expected={'torch':'2.10.0a0+b558c986e8.nv25.11','torchvision':'0.25.0a0+7a13ad0f'}
for package,want in expected.items():
    actual=m.version(package)
    print(package,actual,flush=True)
    if actual!=want: raise RuntimeError('Validated GPU environment differs; no host packages changed')
if not torch.cuda.is_available(): raise RuntimeError('CUDA unavailable')
print('GPU',torch.cuda.get_device_name(0),flush=True)
PY
python -u -m pip install --no-deps --target /tmp/door-api-packages timm==1.0.30 Pillow==12.0.0 numpy==2.1.0
export PYTHONPATH=/tmp/door-api-packages:$PWD
if [[ "$DOOR_API_MODE" == backend-verify ]]; then
  exec python -u -m ai_api.verify_backend_profile --model-version "$DOOR_API_MODEL_VERSION" \
    --cam-format "$DOOR_API_CAM_FORMAT" --jpeg-quality "$DOOR_API_JPEG_QUALITY"
elif [[ "$DOOR_API_MODE" == integration ]]; then
  exec python -u -m ai_api.verify_integration --model-version "$DOOR_API_MODEL_VERSION"
elif [[ "$DOOR_API_MODE" == focused ]]; then
  exec python -u -m ai_api.focused_cam --model-version "$DOOR_API_MODEL_VERSION"
elif [[ "$DOOR_API_MODE" == diagnose ]]; then
  exec python -u -m ai_api.diagnostics --model-version "$DOOR_API_MODEL_VERSION"
elif [[ "$DOOR_API_MODE" == verify ]]; then
  exec python -u -m ai_api.verify_gpu --model-version "$DOOR_API_MODEL_VERSION"
else
  exec python -u -m ai_api.server --development-contract --model-version "$DOOR_API_MODEL_VERSION" \
    --response-profile "$DOOR_API_RESPONSE_PROFILE" \
    --cam-format "$DOOR_API_CAM_FORMAT" --jpeg-quality "$DOOR_API_JPEG_QUALITY" \
    --image-origin "$DOOR_API_IMAGE_ORIGIN" --host 0.0.0.0 --port 8770
fi
CONTAINER
