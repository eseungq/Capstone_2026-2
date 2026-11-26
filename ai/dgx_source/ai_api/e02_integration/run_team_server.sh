#!/usr/bin/env bash
set -Eeuo pipefail
project=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$project"
name=door-e02-team-api
bind_ip=127.0.0.1
port=8771
runtime="$project/outputs/door_e02_live"
mkdir -p "$runtime" outputs/door_next_runtime
python3 - <<'CHECK'
from ai_api.e02_engine import validate_candidate
from ai_api.e02_integration.verify_stub_http import main
import socket
m,_,_=validate_candidate()
assert m['modelVersion']=='door-swin-tiny-e02-28a2dd1cb40b-dev'
s=socket.socket();s.bind(('127.0.0.1',8771));s.close()
print('[PRECHECK]',main()['status'],m['modelVersion'],flush=True)
CHECK
docker_cmd=(docker)
if [[ "${DOOR_DOCKER_SUDO:-0}" == 1 ]]; then docker_cmd=(sudo docker); fi
if "${docker_cmd[@]}" container inspect "$name" >/dev/null 2>&1; then
 echo 'Named container already exists; inspect it before creating or replacing it.'; exit 1
fi
"${docker_cmd[@]}" image inspect nvcr.io/nvidia/pytorch:25.11-py3 >/dev/null
cid=$("${docker_cmd[@]}" run -d --init --restart unless-stopped --pull=never --gpus all --ipc=host  --name "$name" --user "$(id -u):$(id -g)"  -e HOME=/tmp -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1  -p "$bind_ip:$port:$port"  -v "$project:$project:ro"  -v "$runtime:$runtime:rw"  -v "$project/outputs/door_next_runtime:$project/outputs/door_next_runtime:rw"  -w "$project" nvcr.io/nvidia/pytorch:25.11-py3 bash -se -c '
set -Eeuo pipefail
if [[ ! -f /tmp/door-e02-team-packages/.installed ]]; then
 python -m pip install --no-deps --target /tmp/door-e02-team-packages timm==1.0.30 Pillow==12.0.0 numpy==2.1.0
 touch /tmp/door-e02-team-packages/.installed
fi
export PYTHONPATH=/tmp/door-e02-team-packages:$PWD
exec python -u -m ai_api.e02_integration.serve  --image-origin http://127.0.0.1:8080 --host 0.0.0.0 --port 8771  --runtime "$PWD/outputs/door_e02_live/requests"  --ready-file "$PWD/outputs/door_e02_live/ready.json"  --gpu-lock "$PWD/outputs/door_next_runtime/.gpu.lock"
')
printf '%s\n' "$cid" > "$runtime/container_id.txt"
printf '[CONTAINER] %s\n[MODELS] http://%s:%s/internal/v1/models\n' "$cid" "$bind_ip" "$port"
for i in $(seq 1 90); do
 if curl --noproxy '*' -fsS --max-time 2 "http://$bind_ip:$port/internal/v1/models" > "$runtime/models.json.tmp"; then
  mv "$runtime/models.json.tmp" "$runtime/models.json"
  cat "$runtime/models.json"
  echo; echo '[TEAM API READY]'; exit 0
 fi
 running=$("${docker_cmd[@]}" inspect -f '{{.State.Running}}' "$name")
 if [[ "$running" != true ]]; then break; fi
 sleep 2
done
"${docker_cmd[@]}" logs --tail 50 "$name"
echo 'Startup not confirmed. Container preserved for inspection.'; exit 1
