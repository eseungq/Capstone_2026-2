#!/usr/bin/env bash
set -Eeuo pipefail
project=/path/to/private/validated-project
cd "$project"
manifest=$(python3 -c 'import json; print(json.load(open("ai_api/cam_model_comparison_20261104/latest.json"))["output"]+"/comparison_manifest.json")')
out=$(dirname "$manifest")
if [[ -f "$out/launch.json" || -f "$out/report.json" || -f "$out/run.log" ]]; then
  echo 'This comparison was already launched. Inspect its saved report instead of duplicating it.'
  exit 2
fi
sudo -v
sudo docker inspect door-e02-team-api >/dev/null
sudo docker exec -u "$(id -u):$(id -g)" -e CUDA_VISIBLE_DEVICES= -e OMP_NUM_THREADS=2 -e MKL_NUM_THREADS=2 -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH="/tmp/door-e02-team-packages:$project" -w "$project" door-e02-team-api python ai_api/cam_model_comparison_20261104/launch.py --manifest "$manifest"
printf 'CPU model comparison launched. Output: %s\n' "$out"
echo 'The running AI server and its model were not changed.'
