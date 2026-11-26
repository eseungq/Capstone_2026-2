#!/usr/bin/env bash
set -Eeuo pipefail
project=/path/to/private/validated-project
docker_cmd=(docker)
if [[ "${DOOR_DOCKER_SUDO:-0}" == 1 ]]; then docker_cmd=(sudo docker);sudo -v;fi
running=$("${docker_cmd[@]}" inspect --format '{{.State.Running}}' door-local-prototype)
if [[ "$running" != true ]]; then echo '[중단] 기존 door-local-prototype 컨테이너가 실행 중이어야 합니다.';exit 1;fi
# Executes a diagnostic process in the existing container. Does not start/stop a service.
# The original production Engine is loaded once in this process; user DB/cache are read-only inputs.
echo '[점검 시작] 기존 컨테이너 / 동일 이미지 / logits[0,0]와 logits[0,1] / 새 진단 폴더만 기록'
"${docker_cmd[@]}" exec --user "$(id -u):$(id -g)" \
  -e PYTHONPATH=/tmp/door-prototype-packages -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 \
  -w "$project" door-local-prototype python -u prototype/audit_cam_classes.py
