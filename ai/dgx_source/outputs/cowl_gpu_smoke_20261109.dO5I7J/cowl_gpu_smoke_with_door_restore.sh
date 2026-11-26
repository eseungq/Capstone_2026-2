#!/usr/bin/env bash
set -Eeuo pipefail

project=/path/to/private/validated-project
stage=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
prep="$project/outputs/cowl_pin_training_prep_20261109.c2TQKc"
door=door-e02-team-api
smoke=cowl-pin-quick-20261109
deps=cowl-pin-deps-20261109
timer=cowl-pin-door-restore-20261109
image=nvcr.io/nvidia/pytorch:25.11-py3
expected=28a2dd1cb40b4bbecf3fc4e34dfc5354179dcb31c0c37297f1d3ee3bfe3d985e
models=http://127.0.0.1:8771/internal/v1/models
lock="$project/outputs/door_next_runtime/.gpu.lock"
output="$project/outputs/cowl_pin_training"
docker=(sudo -n /usr/bin/docker)
run_uid="$(id -u):$(id -g)"
mkdir -p "$stage/packages" "$output"
exec > >(tee -a "$stage/supervisor.log") 2>&1
exec 8>"$stage/supervisor.lock"
flock -n 8

check_door() {
    curl --noproxy '*' -fsS --max-time 2 -D "$stage/door.headers" -o "$stage/door.json" "$models" 2>/dev/null &&
        tr -d '\r' < "$stage/door.headers" | grep -Fqi "X-AI-Model-SHA256: $expected" &&
        python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["data"] == [{"partCode":"DOOR","modelVersion":"door-swin-tiny-e02-28a2dd1cb40b-dev","calibratorVersion":None,"loadable":True}]' "$stage/door.json"
}

if [[ -e "$stage/result.txt" ]]; then
    echo 'This smoke run has already completed; inspect result.txt and supervisor.log.'
    exit 1
fi
test -s "$prep/preflight.json"
test "$("${docker[@]}" inspect --format '{{.Id}}' "$door")" = "$(cat "$project/outputs/door_e02_live/container_id.txt")"
check_door
if "${docker[@]}" container inspect "$smoke" >/dev/null 2>&1 ||
   "${docker[@]}" container inspect "$deps" >/dev/null 2>&1; then
    echo 'A fixed-pin test container already exists. Inspect before retrying.'
    exit 1
fi

echo "[DEPENDENCY PREFLIGHT] $(date -Iseconds) · door online"
if ! timeout 100s "${docker[@]}" run --rm --pull=never --name "$deps" --user "$run_uid" -e HOME=/tmp \
    -v "$stage/packages:/opt/cowl-packages:rw" "$image" bash -euc '
        python -m pip install --no-deps --disable-pip-version-check --target /opt/cowl-packages timm==1.0.30 Pillow==12.0.0 numpy==2.1.0
        PYTHONPATH=/opt/cowl-packages python -c '"'"'import importlib.metadata as m; expected={"torch":"2.10.0a0+b558c986e8.nv25.11","torchvision":"0.25.0a0+7a13ad0f","timm":"1.0.30","Pillow":"12.0.0","numpy":"2.1.0"}; assert {k:m.version(k) for k in expected}==expected'"'"'
    '; then
    "${docker[@]}" rm -f "$deps" >/dev/null 2>&1 || true
    echo 'Package preflight failed while the door API was still online.'
    exit 1
fi

sudo -n /usr/bin/systemd-run --quiet --unit="$timer" --on-active=210s --timer-property=AccuracySec=1s \
    /bin/bash -c '/usr/bin/docker rm -f cowl-pin-quick-20261109 >/dev/null 2>&1 || true; /usr/bin/docker start door-e02-team-api'

restore() {
    local rc=$?
    trap - EXIT HUP INT TERM
    "${docker[@]}" rm -f "$smoke" >/dev/null 2>&1 || true
    if [[ -e /proc/$$/fd/9 ]]; then exec 9>&-; fi
    "${docker[@]}" start "$door" >/dev/null || true
    for _ in $(seq 1 45); do
        if check_door; then
            sudo -n /usr/bin/systemctl stop "$timer.timer" || true
            printf 'smoke_exit=%s\ndoor_restored=%s\n' "$rc" "$(date -Iseconds)" >"$stage/result.txt"
            echo "[DOOR RESTORED] $(date -Iseconds)"
            exit "$rc"
        fi
        sleep 1
    done
    printf 'smoke_exit=%s\ndoor_restored=unconfirmed\n' "$rc" >"$stage/result.txt"
    echo '[DOOR RESTORE UNCONFIRMED] Fallback timer remains active.' >&2
    exit 1
}
trap restore EXIT
trap 'exit 130' INT
trap 'exit 143' HUP TERM

"${docker[@]}" stop --time 12 "$door" >/dev/null
echo "[DOOR STOPPED] $(date -Iseconds)"
exec 9>>"$lock"
flock -n 9
"${docker[@]}" run -d --init --pull=never --gpus all --ipc=host --name "$smoke" \
    --user "$run_uid" -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 \
    -e "PYTHONPATH=/opt/cowl-packages:$project" -v "$stage/packages:/opt/cowl-packages:ro" \
    -v "$project:$project:ro" -v "$output:$output:rw" -w "$project" "$image" \
    python -u "$prep/cowl_pin_training.py" smoke "$prep" >"$stage/smoke_container.txt"
set +e
result=$(timeout 120s "${docker[@]}" wait "$smoke")
wait_rc=$?
set -e
"${docker[@]}" logs "$smoke" 2>&1 | tee "$stage/smoke.log"
if (( wait_rc != 0 )); then exit "$wait_rc"; fi
if [[ "$result" != 0 ]]; then echo "Smoke container exit: $result"; exit 1; fi
grep -q '^\[FRAME SMOKE PASSED\]' "$stage/smoke.log"
echo '[COWL GPU SMOKE PASSED]'
