#!/usr/bin/env bash
set -Eeuo pipefail
project=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$project"
run_id=$(date -u +%Y%m%dT%H%M%SZ)
out="$project/outputs/door_e02_live/cam_cpu_$run_id"
log="$project/outputs/door_e02_live/cam_cpu_$run_id.log"
sudo -v
sudo docker inspect door-e02-team-api >/dev/null
python3 - "$out" "$log" <<'PY'
import json,sys
from pathlib import Path
Path('ai_api/e02_integration/latest_cam_cpu.json').write_text(json.dumps(dict(output=sys.argv[1],log=sys.argv[2],mode='CPU only; production/GPU unchanged'))+'\n')
PY
sudo docker exec -d -u "$(id -u):$(id -g)"  -e CUDA_VISIBLE_DEVICES= -e OMP_NUM_THREADS=2 -e MKL_NUM_THREADS=2  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH="/tmp/door-e02-team-packages:$project"  -w "$project" door-e02-team-api bash -c  'exec python -u -m ai_api.e02_integration.diagnose_cam_cpu --output "$1" > "$2" 2>&1'  bash "$out" "$log"
printf '[CPU DIAGNOSTIC STARTED]\n[OUTPUT] %s\n[LOG] %s\n' "$out" "$log"
echo 'No GPU inference or production server configuration was changed.'
