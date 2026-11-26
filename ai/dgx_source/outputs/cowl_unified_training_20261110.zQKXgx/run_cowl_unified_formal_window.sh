#!/usr/bin/env bash
set -Eeuo pipefail

stage=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd -- "$stage/../.." && pwd)
packages="$project/outputs/cowl_gpu_smoke_20261109.dO5I7J/packages"
output="$stage/runs"
api=door-e02-team-api
worker=cowl-unified-formal-12e
fallback=cowl-unified-door-fallback
image=nvcr.io/nvidia/pytorch:25.11-py3
url=http://127.0.0.1:8771/internal/v1/models
training_limit=27000s
smoke_limit=150s

cd "$project"
timeout --kill-after=15s "$training_limit" true
timeout --kill-after=15s "$smoke_limit" true
test -d "$output"
test -d "$packages/timm"
PYTHONPATH="$project" PYTHONDONTWRITEBYTECODE=1 python3 "$stage/cowl_unified_training.py" check "$stage"
if [[ ${1:-} == check && $# == 1 ]]; then exit 0; fi
[[ ${1:-} == --start-training && $# == 1 && $EUID == 0 ]]

exec 8>"$stage/supervisor.lock"
flock -n 8
exec > >(tee -a "$stage/supervisor.log") 2>&1
expected=$(cat "$project/outputs/door_e02_live/container_id.txt")
runtime_user=$(stat -c '%u:%g' "$output")
ready() {
    curl --noproxy '*' -fsS --max-time 3 "$url" | python3 -c '
import json, sys
assert json.load(sys.stdin)["data"] == [{
    "partCode":"DOOR","modelVersion":"door-swin-tiny-e02-28a2dd1cb40b-dev",
    "calibratorVersion":None,"loadable":True,
}]' 2>/dev/null
}
[[ $(docker inspect --format '{{.Id}} {{.State.Running}}' "$api") == "$expected true" ]]
ready
if docker container inspect "$worker" >/dev/null 2>&1; then exit 1; fi
test ! -e "$output/smoke"
test ! -e "$output/train"
image_id=$(docker image inspect --format '{{.Id}}' "$image")
mounts=(--user "$runtime_user" --network none -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1
        -e "PYTHONPATH=/opt/cowl-packages:$project" -v "$packages:/opt/cowl-packages:ro")
docker run --rm --pull=never "${mounts[@]}" "$image_id" python -c '
import importlib.metadata as m
expected={"torch":"2.10.0a0+b558c986e8.nv25.11","torchvision":"0.25.0a0+7a13ad0f","timm":"1.0.30","Pillow":"12.0.0","numpy":"2.1.0"}
assert {k:m.version(k) for k in expected} == expected'

systemd-run --quiet --unit="$fallback" --on-active=8h --timer-property=AccuracySec=1s \
    /bin/bash -c '/usr/bin/docker rm -f cowl-unified-formal-12e >/dev/null 2>&1 || true; exec /usr/bin/docker start door-e02-team-api'

restore() {
    local rc=$?
    trap - EXIT
    trap '' HUP INT TERM
    timeout 35s docker rm -f "$worker" >/dev/null 2>&1 || true
    exec 9<&-
    if timeout 35s docker start "$api" >/dev/null; then
        for _ in $(seq 1 30); do
            if ready; then
                systemctl stop "$fallback.timer" || true
                printf 'training_exit=%s\ndoor_restored=%s\n' "$rc" "$(date -Iseconds)" >"$stage/result.txt"
                exit "$rc"
            fi
            sleep 1
        done
    fi
    printf 'training_exit=%s\ndoor_restored=unconfirmed\n' "$rc" >"$stage/result.txt"
    exit 1
}
trap restore EXIT
trap 'exit 143' HUP INT TERM
docker stop --time 15 "$api" >/dev/null
exec 9<"$project/outputs/door_next_runtime/.gpu.lock"
flock -n 9

run() {
    local mode=$1 limit=$2
    timeout --kill-after=15s "$limit" docker run --rm --init --pull=never --gpus all --ipc=host --name "$worker" \
        "${mounts[@]}" -v "$project:$project:ro" -v "$output:$output:rw" -w "$project" "$image_id" \
        python -u "$stage/cowl_unified_training.py" "$mode" "$stage"
}
echo "[COWL UNIFIED GPU SMOKE] $(date -Iseconds)"
run smoke "$smoke_limit"
echo "[COWL UNIFIED 12 EPOCHS START] $(date -Iseconds)"
run train "$training_limit"
python3 - "$output/train" <<'PY'
import csv, json, sys
from pathlib import Path
run = Path(sys.argv[1])
status = json.loads((run / "status.json").read_bytes())
assert status["status"] == "passed" and status["mode"] == "train"
with (run / "history.csv").open(newline="") as stream:
    assert [int(row["epoch"]) for row in csv.DictReader(stream)] == list(range(1, 13))
assert all((run / name).stat().st_size > 0 for name in ("best.pt", "last.pt"))
print("COWL_UNIFIED_12E_COMPLETE", run)
PY
