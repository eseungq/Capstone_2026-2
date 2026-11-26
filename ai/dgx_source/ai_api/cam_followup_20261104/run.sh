#!/usr/bin/env bash
set -Eeuo pipefail
project=/path/to/private/validated-project
cd "$project"
selection=$(python3 -c 'import json; print(json.load(open("ai_api/cam_followup_20261104/latest.json"))["output"]+"/selection.json")')
out=$(dirname "$selection")
if [[ -f "$out/report.json" ]]; then
  echo 'This frozen sample run has already started. Check report.json; not starting a duplicate.'
  exit 2
fi
sudo -v
sudo docker inspect door-e02-team-api >/dev/null
sudo docker exec -u "$(id -u):$(id -g)" -e CUDA_VISIBLE_DEVICES= -e OMP_NUM_THREADS=2 -e MKL_NUM_THREADS=2 -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH="/tmp/door-e02-team-packages:$project" -w "$project" door-e02-team-api python ai_api/cam_followup_20261104/launch.py --selection "$selection"
printf 'CPU follow-up launched. Output: %s\n' "$out"
echo 'The existing AI server was not stopped. CUDA is disabled for this diagnostic.'
