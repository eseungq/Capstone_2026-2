# Mock AI 추론 서버

백엔드 API 계약 v4 7장 규격을 흉내 내는 개발용 서버. 실제 모델이 아니며 반환 값은 전부 가짜다.

## 실행

```bash
cd mock-ai
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --port 8090
```

백엔드 `app.ai.base-url`이 `http://localhost:8090`이면 바로 연동된다.

## 시나리오

기본값 `AUTO`: 사진 내용(해시)에 따라 정상 응답 5종 중 하나. 같은 사진은 항상 같은 결과.

| 시나리오 | AI 응답 | 백엔드 기대 결과 (예시 정책 passThreshold 0.05 기준) |
|---|---|---|
| GOOD_CALIBRATED | GOOD, 보정 0.021 | COMPLETED · AUTO_PASS (최종 PASS, SYSTEM) |
| GOOD_ABOVE_THRESHOLD | GOOD, 보정 0.2 | COMPLETED · REVIEW (ABOVE_THRESHOLD) |
| GOOD_UNCALIBRATED | GOOD, 보정 null | COMPLETED · REVIEW (CALIBRATION_UNAVAILABLE) |
| DEFECT_GRADCAM | DEFECT, Grad-CAM PNG (`status: GENERATED`) | COMPLETED · REVIEW (DEFECT_PREDICTED), gradcamStatus GENERATED |
| DEFECT_GRADCAM_FAIL | DEFECT, Grad-CAM null | COMPLETED · REVIEW (DEFECT_PREDICTED), gradcamStatus FAILED |
| DEFECT_NO_ACTIVATION | DEFECT, 0맵 (`status: NO_ACTIVATION`, `mapType: ZERO_MAP`, 이미지 null) | COMPLETED · REVIEW (DEFECT_PREDICTED), gradcamStatus NO_ACTIVATION, CAM 이미지 없음 |
| DEFECT_GRADCAM_JPEG | DEFECT, Grad-CAM JPEG (`format: jpeg`) | COMPLETED · REVIEW (DEFECT_PREDICTED), gradcamStatus GENERATED, `image/jpeg`로 저장 |
| ERROR_4XX | 422 오류 본문 | FAILED · AI_REQUEST_REJECTED (재시도 없음) |
| ERROR_5XX | 500 오류 본문 | 1회 재시도 후 FAILED · AI_SERVER_ERROR |
| TIMEOUT | 15초 대기 | FAILED · AI_SERVER_TIMEOUT (백엔드 read-timeout 10초) |
| INVALID_RESPONSE | modelVersion 불일치 | FAILED · AI_RESPONSE_INVALID |

```bash
# 계속 적용
curl -X PUT localhost:8090/mock/scenario -H 'Content-Type: application/json' -d '{"scenario":"DEFECT_GRADCAM"}'
# 다음 요청 1건에만 적용
curl -X PUT localhost:8090/mock/scenario -H 'Content-Type: application/json' -d '{"scenario":"ERROR_5XX","once":true}'
# 현재 상태
curl localhost:8090/mock/scenario
```

- `once`로 `ERROR_5XX`를 걸면 백엔드의 1회 재시도는 AUTO 결과를 받아 성공한다 (재시도 동작 확인용). FAILED까지 보려면 `once` 없이 설정

환경 변수: `MOCK_SCENARIO`(시작 시나리오), `MOCK_TIMEOUT_SECONDS`(기본 15), `MOCK_DELAY_MS`(기본 300)

## 그 밖의 동작

- 모르는 모델 버전, 부품과 모델 불일치, 이미지 다운로드 실패 → 422 (백엔드는 AI_REQUEST_REJECTED)
- Grad-CAM은 EXIF 방향 보정한 원본과 같은 크기의 PNG
- `GET /internal/v1/models`: 로드 가능한 모델 목록
- 모델 버전 2개: `mock-door-swin-t-v1`(보정기 `mock-cal-v1`), `door-swin-tiny-e20-8d042c7bfab2`(실제 DOOR 모델 버전, 보정기 없음).
  보정기가 없는 모델은 어떤 시나리오든 보정 확률·보정기 버전을 null로 반환한다 (정책도 없으므로 GOOD은 REVIEW `NO_ACTIVE_POLICY`)
- 새 시나리오 2종은 AUTO 선택 대상에 넣지 않았다 (기존 사진별 결과 유지). 직접 지정해서 사용
