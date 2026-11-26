#!/usr/bin/env bash
set -Eeuo pipefail
project=/path/to/private/validated-project
training=/path/to/private-user/다운로드/도어_SwinTiny_DGX_학습_20261009
image=nvcr.io/nvidia/pytorch:25.11-py3
# Run from a host terminal with existing Docker access. Never installs host packages.
docker_cmd=(docker)
if [[ "${DOOR_DOCKER_SUDO:-0}" == 1 ]]; then
  docker_cmd=(sudo docker)
fi
mkdir -p "$project/outputs/evaluation/launch_logs"
log="$project/outputs/evaluation/launch_logs/door_$(date +%Y%m%d_%H%M%S)_$$.log"
exec > >(tee -a "$log") 2>&1
trap 'rc=$?; printf "[실패] exit=%s line=%s command=%s\n로그: %s\n" "$rc" "$LINENO" "$BASH_COMMAND" "$log"; exit "$rc"' ERR
printf '[시작] Docker 평가 실행 준비\n로그: %s\n' "$log"
# Keep the lock until the foreground Docker command exits.
exec 9>"$project/outputs/evaluation/.door_internal.lock"
if ! flock -n 9; then
  echo '[중단] 다른 평가 실행 스크립트가 실행 중입니다.'
  exit 1
fi
if [[ "${DOOR_DOCKER_SUDO:-0}" == 1 ]]; then
  echo '[환경] sudo 인증 확인'
  sudo -v
fi
echo '[환경] Docker 접근 및 기존 이미지 확인'
"${docker_cmd[@]}" image inspect "$image" >/dev/null
active=$("${docker_cmd[@]}" ps --filter 'name=^/door-internal-evaluation$' --format '{{.ID}}')
if [[ -n "$active" ]]; then
  echo "[중단] 기존 평가 컨테이너 실행 중: $active"
  exit 1
fi
echo '[환경] 컨테이너 시작: bash -se, 표준입력 연결(-i)'
"${docker_cmd[@]}" run --rm -i --name door-internal-evaluation --pull=never --gpus all --ipc=host \
  --user "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUNBUFFERED=1 \
  -v "$project:$project" \
  -v "$project/data:$project/data:ro" \
  -v "$project/src:$project/src:ro" \
  -v "$project/outputs/training:$project/outputs/training:ro" \
  -v "$project/outputs/manifests:$project/outputs/manifests:ro" \
  -v "$project/outputs/reviews:$project/outputs/reviews:ro" \
  -v "$training:$training:ro" \
  -w "$project" "$image" bash -se <<'CONTAINER'
set -Eeuo pipefail
trap 'rc=$?; printf "[컨테이너 실패] exit=%s line=%s command=%s\n" "$rc" "$LINENO" "$BASH_COMMAND"; exit "$rc"' ERR
echo '[환경] 컨테이너 코드 진입 / torch 버전 및 CUDA 검사 시작'
python -u - <<'PY'
import importlib.metadata as m
expected={'torch':'2.10.0a0+b558c986e8.nv25.11','torchvision':'0.25.0a0+7a13ad0f'}
for p,want in expected.items():
    actual=m.version(p)
    print(f'{p}: {actual}', flush=True)
    if actual!=want:
        raise RuntimeError(f'Existing Docker environment mismatch: {p} {actual} != {want}; no torch changes made')
import torch
if not torch.cuda.is_available():
    raise RuntimeError('Docker GPU unavailable')
print('Docker GPU:',torch.cuda.get_device_name(0),flush=True)
PY
# Only temporary container packages; --no-deps prevents torch replacement.
echo '[환경 완료] GPU 확인 / 컨테이너 임시 패키지 준비 시작'
python -u -m pip install --no-deps --target /tmp/door-evaluation-packages timm==1.0.30 Pillow==12.0.0 numpy==2.1.0
echo '[패키지 완료] 내부 검증 평가 프로그램 시작'
PYTHONPATH=/tmp/door-evaluation-packages python -u src/evaluate_door_internal.py
echo '[컨테이너 완료] 평가 프로그램 종료. 최종 status.json의 평가/보고서/Grad-CAM 상태를 확인하세요.'
CONTAINER
printf '[실행 종료] 로그: %s\n' "$log"
