#!/usr/bin/env bash
set -Eeuo pipefail
project=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project"
export DOOR_EXPERIMENT_CONFIG="$project/configs/door_visible_region_experiment_v3_10epochs.json"
export DOOR_REVIEW_RUN="$project/outputs/door_next_training/door_visible_20261029_162657_477520"
python3 -m door_experiment.prepare_model_review --run "$DOOR_REVIEW_RUN"
exec bash "$project/door_experiment/run_gpu_10.sh" review
