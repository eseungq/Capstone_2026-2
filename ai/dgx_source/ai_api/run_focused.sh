#!/usr/bin/env bash
set -Eeuo pipefail
cd /path/to/private/validated-project
[[ $# == 1 ]] || { echo 'Usage: bash ai_api/run_focused.sh /path/to/cam_roi_export.json'; exit 2; }
roi_prepared=$(python3 - "$1" <<'PY'
import hashlib,json,sys
from pathlib import Path
from ai_api.focused_cam import validate_roi
p=Path(sys.argv[1]);blob=p.read_bytes();validate_roi(json.loads(blob))
dest=Path('/path/to/private/validated-project/ai_api/runtime')/('roi_'+hashlib.sha256(blob).hexdigest()+'.json')
dest.parent.mkdir(exist_ok=True)
if dest.exists():
    if dest.read_bytes()!=blob:raise ValueError('Existing ROI content differs')
else:dest.write_bytes(blob)
print(dest)
PY
)
export DOOR_API_ROI_FILE="$roi_prepared"
export DOOR_API_MODEL_VERSION='UNREGISTERED-door-swin-tiny-focused'
export DOOR_API_DEVELOPMENT_CONTRACT=1
export DOOR_DOCKER_SUDO="${DOOR_DOCKER_SUDO:-1}"
exec bash ai_api/run_gpu.sh focused
