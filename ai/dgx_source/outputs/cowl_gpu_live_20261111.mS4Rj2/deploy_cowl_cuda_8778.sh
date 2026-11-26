#!/usr/bin/env bash
set -Eeuo pipefail

stage=$(dirname "$(realpath "$0")")
cd "$HOME/car-parts-ai"
project=$PWD
cpu="$project/outputs/cowl_unified_calibrated_api_20261111.BN4EGS"
gpu_trial="$project/outputs/cowl_gpu_trial_20261111.QDGlXg"
training="$project/outputs/cowl_unified_training_20261110.zQKXgx"
study="$project/outputs/cowl_unified_policy_20261110.8sMbOO"
python="$HOME/jupyterlab/.venv/bin/python"
host=127.0.0.1
origin=http://127.0.0.1:8080
session=cowl-unified-trial-8778
relay=cowl-unified-tailnet-8778

api_paths="$gpu_trial:$cpu:$training:$project/outputs/cowl_unified_trial_api_20261110.m6Jwh2"
api_paths="$api_paths:$project/outputs/cowl_pin_trial_api_20261109.TXlm5V:$project/outputs/cowl_pin_policy_development_20261109.xFQpFZ"
api_paths="$api_paths:$project/outputs/cowl_linkage_official_20261110.VxAkw0:$project/outputs/cowl_linkage_trial_api_20261110.F0bcSB:$project"

check_inventory() {
    local url=$1
    curl -fsS --connect-timeout 2 --max-time 4 "$url/internal/v1/models" |
        "$python" -c 'import json,sys
r=json.load(sys.stdin)["data"]
assert r==[dict(partCode="COWL_COVER",modelVersion="cowl-cover-unified-swin-tiny-e08-458a07d46453-dev",calibratorVersion="cowl-unified-e08-temperature-2d80fc926685-demo",loadable=True)]
print(json.dumps(r))'
}

loopback_listener() {
    ss -H -ltn '( sport = :8778 )' | awk '$4 == "127.0.0.1:8778"'
}

await_ready() {
    local smoke=$1
    local log=$2
    for _ in {1..45}; do
        if [[ -s "$smoke" ]] && grep -q '^COWL_UNIFIED_CALIBRATED_READY' "$log" &&
            check_inventory "http://$host:8778"; then
            return 0
        fi
        tmux has-session -t "=$session" || break
        sleep 1
    done
    tail -n 25 "$log" >&2 || true
    return 1
}

rollback_needed=false
finished=false
rollback_on_failure() {
    local code=$?
    if [[ "$rollback_needed" == true && "$finished" == false ]]; then
        tmux kill-session -t "=$session" 2>/dev/null || true
        for _ in {1..12}; do
            [[ -z "$(loopback_listener)" ]] && break
            sleep 1
        done
        tmux new-session -d -s "$session" "exec bash '$cpu/launch.sh' '$stage/cpu-rollback' --port 8778 --image-origin '$origin' --serve > '$stage/cpu-rollback.log' 2>&1"
        if await_ready "$stage/cpu-rollback/smoke.json" "$stage/cpu-rollback.log"; then
            echo CPU_RESTORED > "$stage/status"
        else
            echo CPU_RESTORE_UNCONFIRMED > "$stage/status"
        fi
    elif [[ "$finished" == false ]]; then
        echo PREFLIGHT_FAILED_CPU_RETAINED > "$stage/status"
    fi
    exit "$code"
}
trap rollback_on_failure EXIT

test "$(tailscale ip -4)" = "$host"
tmux has-session -t "=$relay"
[[ "$(tmux list-panes -t "=$session" -F '#{pane_start_command}')" == *"$cpu/launch.sh"* ]]
check_inventory "http://$host:8778"
"$python" -c 'import json,sys
with open(sys.argv[1]) as f: r=json.load(f)
assert r["threshold"]==.0163 and len(r["compared"])==2
assert all(not s["threshold_flips"] and s["counts"]["class_flips"]==s["counts"]["gpu_pass_defect"]==0
           for s in r["compared"].values())
' "$gpu_trial/gpu_policy_comparison.json"

cat > "$stage/launch.sh" <<EOF
set -euo pipefail
cd '$project'
export CUDA_VISIBLE_DEVICES=0 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH='$api_paths'
exec '$python' -u '$stage/serve_cowl_cuda_trial.py' '$training/runs/train' '$study' "\$@"
EOF
bash "$stage/launch.sh" "$stage/preflight" --image-origin "$origin" > "$stage/preflight.log" 2>&1
grep -q '^COWL_DEVICE=cuda' "$stage/preflight.log"
test -s "$stage/preflight/smoke.json"
echo PREFLIGHT_PASSED > "$stage/status"

tmux kill-session -t "=$session"
rollback_needed=true
for _ in {1..12}; do
    [[ -z "$(loopback_listener)" ]] && break
    sleep 1
done
[[ -z "$(loopback_listener)" ]]
tmux new-session -d -s "$session" "exec bash '$stage/launch.sh' '$stage/live' --port 8778 --image-origin '$origin' --serve > '$stage/live.log' 2>&1"
await_ready "$stage/live/smoke.json" "$stage/live.log"
grep -q '^COWL_DEVICE=cuda' "$stage/live.log"
for port in 8771 8774; do
    curl -fsS --connect-timeout 2 --max-time 4 "http://$host:$port/internal/v1/models"
    printf '\n'
done
finished=true
echo GPU_ACTIVE > "$stage/status"
