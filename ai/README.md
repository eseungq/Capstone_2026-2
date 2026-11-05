# ai · 실제 e02 추론 서버와 학습 코드

담당: 김도현. 백엔드가 호출하는 `POST /internal/v1/predict`, `GET /internal/v1/models`를 포함합니다.
연동 기준은 [API 계약 v4 7장](../docs/백엔드_API계약_v4.md#7-ai-연동-규격-합의-1015)입니다.

## 현재 상태

- 모델: `door-swin-tiny-e02-28a2dd1cb40b-dev`, DOOR, Swin-Tiny 224, epoch 2.
- SHA256: `28a2dd1cb40b4bbecf3fc4e34dfc5354179dcb31c0c37297f1d3ee3bfe3d985e`.
- 11월 4일 실제 백엔드 연동에서 GOOD/DEFECT, JPEG CAM 저장, 4xx/503/timeout/연결 실패와 복구 후 재검사를 확인했습니다. B6 자연 발생 NO_ACTIVATION은 보류입니다.
- 보정기와 보정 확률은 null. 검증된 AUTO_PASS 정책은 없습니다. 성공한 분석도 백엔드에서 REVIEW가 됩니다.
- CAM은 현재 운영의 7×7 norm1 Grad-CAM, 기존 색상, JPEG 품질 90입니다. 새 28×28 HiResCAM/JET 연구 결과는 운영에 넣지 않았습니다.
- 이 브랜치는 실제 실행 코드의 공유본입니다. 운영 DGX 파일을 변경하지 않았습니다. 개인 경로/팀 주소는 환경변수로 분리했으며 추론·CAM 계산 메서드는 AST로 동일함을 확인합니다.

## 환경

`nvcr.io/nvidia/pytorch:25.11-py3`, NVIDIA GPU, Python 3.12 계열, CUDA build 13.0, FP32를 사용합니다. 정확한 패키지 버전은 `environment.json`입니다.
컨테이너의 torch/torchvision을 일반 pip 패키지로 교체하지 마세요. 나머지는 `python -m pip install --no-deps -r requirements.txt`로 맞춥니다. 실행 시 버전 불일치는 오류로 처리하며 CPU 가짜 예측으로 대체하지 않습니다.

## 실행에 필요한 비공개 자료

가중치·학습 사진·CSV·원본 run_config·검토 기록은 Git에 포함하지 않습니다. `AI_PROJECT_ROOT`는 DGX에서 이미 검증한 비공개 프로젝트 폴더입니다.

현재 엔진은 체크포인트 SHA뿐 아니라 run_config·훈련 소스·검토 결과·동결 분할과 학습/선정 이미지 존재까지 감사합니다. 따라서 **best.pt 하나만 받으면 독립 실행되는 패키지는 아닙니다.** 이 검사를 끄거나 빈 CSV로 우회하지 마세요.
모델 위치는 해당 비공개 루트 아래 `outputs/door_next_training/door_visible_20261029_162657_477520/best.pt`입니다. 모델 보유자에게 SSH/SCP 등 팀 내부 경로로 받습니다. 공개 다운로드 링크는 없습니다. AI-Hub 사진은 해당 데이터 이용 권한을 갖춘 환경에서 별도로 준비해야 합니다.
`AI_CANDIDATE_MANIFEST`가 지정되지 않으면 비공개 루트의 `ai_api/door_e02_candidate.json`을 읽습니다. 원본 artifact의 절대 경로와 해시를 보존해야 하므로 검증 프로젝트를 임의로 이동·수정하지 마세요.

## DGX의 검증 환경에서 실행

저장소의 ai/에서 실행합니다. 아래 변수는 실제 로컬 환경에 맞춰 지정합니다.

```bash
export AI_PROJECT_ROOT=/path/to/private/validated-project
export BACKEND_ORIGIN=http://backend-host:8080
export AI_PORT=8771
bash run_server.sh
```

서버는 컨테이너 내부 `0.0.0.0:8771`에서 실행합니다. Docker를 쓴다면 호스트 Tailscale 주소의 같은 포트를 연결해야 합니다. 이미 운영 중인 8771 서버를 이 명령으로 교체하거나 두 번 실행하지 마세요. 공유 GPU 잠금도 유지합니다.
컨테이너에는 이 ai/ 코드 폴더와 비공개 프로젝트를 같은 경로로 읽기 전용 마운트하고, runtime 및 GPU 잠금 폴더만 쓰기 가능하게 준비합니다. 운영 컨테이너 생성 방법과 인증정보를 하드코딩하지 않았습니다.

```bash
curl http://AI_HOST:8771/internal/v1/models
```

predict 요청은 JSON Content-Length가 필요합니다. 현재 chunked 요청을 받지 않습니다. imageUrl은 BACKEND_ORIGIN과 scheme/host/port가 일치해야 하고, 서명 URL은 문자열을 바꾸지 않고 GET 합니다. 서명 URL과 토큰은 로그에 남기지 않습니다.

## 판정과 시간 계약

- AI는 raw softmax 불량 점수 0.5를 기준으로 GOOD/DEFECT를 반환합니다. 이 값은 passThreshold와 별개입니다.
- AUTO_PASS/REVIEW는 백엔드가 결정합니다. DEFECT는 항상 REVIEW, GOOD도 호환 정책 ready·active 및 유효한 보정 확률/기준치 조건을 모두 만족해야 AUTO_PASS입니다. 자동 FAIL은 없습니다.
- `inferenceTimeMs`: handler 진입부터 응답 JSON 직렬화 직전까지. 이미지 다운로드·모델 잠금 대기·추론·CAM·JPEG 인코딩을 포함합니다. 직렬화·응답 전송·백엔드 후처리는 제외합니다.
- e02의 `requests.jsonl`에는 `requestId`로 연결되는 서비스 로그와 `wire_response` 로그가 남습니다. 서비스 로그의 구간별 시간은 모두 밀리초입니다.
  - `imageDownloadMs`는 이미지 출처 검사와 이미지 본문 다운로드에 걸린 시간입니다.
  - `preprocessingMs`는 분류에 사용하는 첫 입력 텐서의 디코딩·EXIF 보정·리사이즈·정규화 시간입니다. 별도로 수행되는 업로드 이미지 검증과 크기 확인은 제외합니다.
  - `camGenerationMs`는 CAM 함수 전체 시간입니다. CAM용 재전처리, CAM 계산, 오버레이 작성이 포함됩니다. 기존 `camEncodingMs`는 그 뒤 JPEG/PNG 응답 인코딩 시간입니다.
  - 실행하지 않은 구간은 `null`입니다. 실행 도중 실패한 구간은 실패 시점까지 걸린 시간을 기록합니다. HTTP 응답 필드는 기존과 같습니다.
- 요청은 여러 개 받을 수 있지만 모델 추론과 CAM은 공유 잠금으로 직렬 처리됩니다. 백엔드 동시 호출 수/timeout은 별도 설정입니다.
- 최종 HTTP 형식은 `ai_api/e02_integration/wire.py`와 handler입니다. contract.py/backend_contract.py 일부는 과거 내부 호환 코드이며 그 내부 프로필 이름을 앱 계약으로 사용하지 않습니다.

## 코드와 점검

- `ai_api/e02_integration/serve.py`: 실제 연동 진입점.
- `prototype/engine.py`: 공유 추론·Grad-CAM 메서드. e02는 CandidateEngine으로 초기화하며 과거 20회차 초기화는 사용하지 않습니다.
- `door_experiment/train_10.py`, `preflight.py`: 실제 10회 학습 코드와 동결 분할 감사. 학습은 ImageNet 초기화, batch 8, lr 1e-4, AMP/증강 없음, model_selection F1 기준입니다.
- `tools/evaluate_checkpoint.py`: 같은 엔진/전처리로 model_selection만 재평가하는 도구. 최종 시험을 자동으로 읽지 않습니다.
- `tools/audit_policy_readiness.py`: 예약 분할·해시·알려진 중복과 미해결 독립성 점검. 이미지나 최종 시험을 읽지 않습니다.
- `tools/evaluate_policy_scores.py`: 이미 준비된 보정 점수에 대해 GOOD 게이트와 임계값별 개발 지표를 계산합니다. ready=true를 만들거나 정책을 활성화하지 않습니다.
- `examples/`: 실제 형식 예시. NO_ACTIVATION은 강제 예시이고 JPEG base64는 축약돼 있습니다.

```bash
python -m ai_api.e02_integration.verify_stub_http
python -m unittest discover -s tests -v
python tools/audit_policy_readiness.py --root "$AI_PROJECT_ROOT" --output /path/to/private/new-audit.json
python -m door_experiment.train_10 --root "$AI_PROJECT_ROOT" --experiment-config "$AI_PROJECT_ROOT/configs/door_visible_region_experiment_v3_10epochs.json" --mode check
```

Stub HTTP 점검은 모델·GPU·실제 사진을 사용하지 않습니다. 이를 실제 GPU 재현 시험으로 표기하지 마세요. 기존 운영 서버의 연동 증빙과 공유본의 단독 점검을 구분합니다.

## Git에 넣지 않는 것

모델 가중치, AI-Hub 사진·라벨·분할 CSV, JPEG CAM, 개인 경로가 포함된 설정, 서명 URL, 토큰·비밀번호·키를 올리지 않습니다. 공개 저장소이므로 ai/.gitignore와 공개 파일 검사 결과를 함께 확인합니다.
