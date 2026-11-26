#!/usr/bin/env bash
set -Eeuo pipefail

project=/path/to/private/validated-project
prep=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
mode=${1:-}
case "$mode" in
    smoke) test "$#" -eq 1 ;;
    train) test "$#" -eq 2 && test "$2" = --start-training ;;
    *) echo 'Usage: bash run_cowl_pin.sh smoke | train --start-training' >&2; exit 2 ;;
esac

# Respect the existing door service lock before requesting Docker access.
exec 9>>"$project/outputs/door_next_runtime/.gpu.lock"
if ! flock -n 9; then
    echo 'GPU lock is held by another process; no training or server restart was attempted.' >&2
    exit 3
fi
docker_cmd=(docker)
if [[ "${COWL_DOCKER_SUDO:-0}" == 1 ]]; then docker_cmd=(sudo docker); fi
output="$project/outputs/cowl_pin_training"
mkdir -p "$output"
name="cowl-pin-${mode}-$(date -u +%Y%m%dT%H%M%SZ)-$$"
exec > >(tee -a "$output/$name.log") 2>&1
"${docker_cmd[@]}" run --rm --init --pull=never --gpus all --ipc=host --name "$name" \
    --user "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 \
    -v "$project:$project:ro" -v "$output:$output:rw" -w "$project" \
    nvcr.io/nvidia/pytorch:25.11-py3 bash -euc '
        python -m pip install --no-deps --disable-pip-version-check --target /tmp/cowl-packages timm==1.0.30 Pillow==12.0.0 numpy==2.1.0
        export PYTHONPATH=/tmp/cowl-packages:$PWD
        exec python -u "$1/cowl_pin_training.py" "$2" "$1" "${@:3}"
    ' bash "$prep" "$mode" "${@:2}"
