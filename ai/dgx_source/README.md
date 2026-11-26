# DGX·Windows AI 소스 보완본 · 2026-11-26

GitHub 기존 ai/에는 도어 중심 공유 코드가 있었으나 프레임·카울커버의 실제 배포 및 일부 학습·평가 소스가 빠져 있어 추가했다. 기존 ai/ai_api·prototype 등의 공개 실행 코드를 덮어쓰지 않고 별도 트리로 보존한다.

## 포함 범위

- ai_api/: DGX의 추론 API, CAM·계약 처리, 자료 점검·검토 도구 및 테스트·화면 템플릿.
- frame_model/: 프레임 통합/유형별 학습·평가 및 CAM 비교 코드.
- cowl_model/: 카울커버 자료 확인·유사도·검토 도구.
- door_experiment/: 도어 분할·학습·검토 도구.
- prototype/, src/: 초기 추론·CAM 및 내부 평가 코드. 최종 배포와 구분한다.
- outputs/: 생성 결과를 올린 것이 아니라 실제 이 경로에 저장되어 실행되는 자체 작성 .py/.sh 소스만 원래 상대 경로로 보존했다. 모델·사진·CSV·실행 결과는 포함하지 않는다.
- legacy_training/: 프로젝트 외부에 보관됐던 최초 Swin-Tiny 학습 소스.
- windows_tools/: Windows에서 사용한 원본·라벨·중복 검사 도구와 테스트.

## 현재 배포 코드 위치

| 부품 | 실제 진입점·핵심 소스 |
|---|---|
| 도어 8771 | ai_api/e02_integration/serve.py 및 handler.py, e02_engine.py, prototype/engine.py |
| 도어 보정 서버 8785 | outputs/door_e02_calibrated_demo_20261117/serve_door_e02_demo.py |
| 프레임 8774 | outputs/frame_layercam28_20261109.2V8EMY/8774/frame_policy_trial_20261109.py, 같은 트리 8773/frame_unified_test_api_20261107.py와 frame_layercam28.py |
| 카울커버 8778 | outputs/cowl_gpu_live_20261111.mS4Rj2/serve_cowl_cuda_trial.py 및 launch.sh, cowl_gpu_trial_20261111.QDGlXg·cowl_unified_calibrated_api_20261111.BN4EGS 등 의존 트리 |

카울커버 통합 학습은 outputs/cowl_unified_training_20261110.zQKXgx/cowl_unified_training.py, 보정·기준 계산은 outputs/cowl_unified_policy_20261110.8sMbOO/evaluate_cowl_unified_policy.py를 참고한다.

## 공개용 변경과 실행 조건

원본 개인 프로젝트 경로는 /path/to/private/validated-project, 사용자 홈은 /path/to/private-user, 팀 전용 IP는 127.0.0.1로 치환했다. 이들은 실제 배포 주소가 아니다. source_manifest.json에 원본·공개본 SHA-256과 변경 여부를 기록한다. Python AST 비교로 이 문자열 치환 외의 코드 구조·수치가 보존되는지 검사했다. 공개본은 LF 줄바꿈으로 통일하고 AST가 같은 Python 행 끝 공백만 정리했다.

가중치·보정 자료·동결 분할·원본 설정·사진·라벨·실행 결과는 공개하지 않는다. 추론 코드가 검증하는 비공개 아티팩트와 GPU 환경이 필요하므로 이 폴더만으로 독립 실행된다는 뜻이 아니다. 실행 경로·호스트는 보유 환경에 맞게 별도로 구성해야 하며, 이 사본을 실행 중인 DGX 원본에 덮어쓰거나 launch.sh를 그대로 실행하지 않는다. 원본 해시를 검사하는 코드가 있으므로 비공개 원본과 공개용 사본의 역할을 구분한다.

기법·CAM 추출 층·가중치·입력 크기·정규화·학습 조건·온도 보정 수치는 변경하지 않았다. 새 학습·추론·배포·정책 활성화는 수행하지 않았다. 비교/시험 스크립트의 과거 기준과 후보값은 당시 실험용이며 현재 적용 결정을 자동 갱신하지 않는다.

## 확인 방법

ai/에서 다음 명령으로 공개 소스의 해시·문법을 확인한다.

```bash
python tools/verify_dgx_source.py
python -m unittest discover -s tests -v
```

두 번째 명령은 기존 공개본의 테스트이며 이 추가본 전체의 GPU 재현 시험을 뜻하지 않는다. 현재 부품별 자동 판정 적용값은 README의 최신 결정 절을 따른다.
