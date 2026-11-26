#!/usr/bin/env bash
set -Eeuo pipefail
project=/path/to/private/validated-project
training=/path/to/private-user/다운로드/도어_SwinTiny_DGX_학습_20261009
image=nvcr.io/nvidia/pytorch:25.11-py3
docker_cmd=(docker)
if [[ "${DOOR_DOCKER_SUDO:-0}" == 1 ]]; then docker_cmd=(sudo docker); fi
mkdir -p "$project/prototype/storage/launch_logs"
log="$project/prototype/storage/launch_logs/service_$(date +%Y%m%d_%H%M%S)_$$.log"
exec > >(tee -a "$log") 2>&1
trap 'rc=$?; printf "[실패] exit=%s line=%s command=%s\n로그: %s\n" "$rc" "$LINENO" "$BASH_COMMAND" "$log"; exit "$rc"' ERR
printf '[시작] 도어 로컬 프로토타입\n로그: %s\n' "$log"
exec 9>"$project/prototype/storage/.service.lock"
if ! flock -n 9; then echo '[중단] 프로토타입 실행 스크립트가 이미 실행 중입니다.';exit 1;fi
if [[ "${DOOR_DOCKER_SUDO:-0}" == 1 ]]; then sudo -v;fi
"${docker_cmd[@]}" image inspect "$image" >/dev/null
existing=$("${docker_cmd[@]}" ps -a --filter 'name=^/door-local-prototype$' --format '{{.ID}} {{.Status}}')
if [[ -n "$existing" ]]; then echo "[중단] 기존 프로토타입 컨테이너 확인 필요: $existing";exit 1;fi
echo '[환경] 기존 GPU Docker 시작 / DGX 로컬 포트 8765'
"${docker_cmd[@]}" run --rm -i --init --name door-local-prototype --pull=never --gpus all --ipc=host \
  --user "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONUNBUFFERED=1 -e PYTHONDONTWRITEBYTECODE=1 \
  -p 127.0.0.1:8765:8765 \
  -v "$project:$project:ro" \
  -v "$project/prototype/storage:$project/prototype/storage:rw" \
  -v "$training:$training:ro" -w "$project" \
  "$image" bash -se <<'CONTAINER'
set -Eeuo pipefail
trap 'rc=$?; printf "[컨테이너 실패] exit=%s line=%s command=%s\n" "$rc" "$LINENO" "$BASH_COMMAND"; exit "$rc"' ERR
echo '[환경] 검증된 torch/torchvision 및 CUDA 확인'
python -u - <<'PY'
import importlib.metadata as m
import torch
expected={'torch':'2.10.0a0+b558c986e8.nv25.11','torchvision':'0.25.0a0+7a13ad0f'}
for package,want in expected.items():
    actual=m.version(package);print(package,actual,flush=True)
    if actual!=want: raise RuntimeError('GPU container version differs from validated run; torch is not modified')
if not torch.cuda.is_available(): raise RuntimeError('CUDA GPU unavailable')
print(torch.cuda.get_device_name(0),flush=True)
PY
echo '[환경] 컨테이너 /tmp에만 라이브러리 준비, torch 교체 없음'
python -u -m pip install --no-deps --target /tmp/door-prototype-packages timm==1.0.30 Pillow==12.0.0 numpy==2.1.0
echo '[서비스 시작] 실제 내부 검증 사진 1장 연결 점검 후 웹 앱 대기'
exec env PYTHONPATH=/tmp/door-prototype-packages python -u prototype/app.py --host 0.0.0.0 --port 8765 --self-check
CONTAINER
echo '[종료] 업로드와 검사 이력은 prototype/storage에 보존됩니다.'
