# 백엔드 API 계약 v4 (초안)

3조 김이홍 · 백엔드 API 이승규 · 2026-10-15 작성

- 기준 1: 「자동차부품_공정모니터링_개발계획서_최종합의반영」(10/14 합의본)
- 기준 2: 「요구사항명세서_패치검사_개정본3」(9/30)의 규칙 중 합의본과 충돌하지 않는 것은 그대로 승계
- 기준 3: 10/15 팀 회신 (김도현 AI 답변, 홍승인 정리, 김남균 DB 주간보고)

표기
- **[확정]** 합의본에 명시된 내용
- **[승계]** 명세서 개정본3에서 이미 정한 규칙을 그대로 유지
- **[합의 10/15]** 10/15 팀 회신으로 확정된 내용
- **[제안]** 합의본이 백엔드에 결정을 맡긴 부분. 이의가 없으면 이대로 구현
- **[TBD-xx]** 미확정. 명세서 11장 번호 체계를 따름 (12장 목록)

공유 대상: 홍승인(앱) · 김남균(DB) · 김도현(AI, 7장)

---

## 0. 변경 요약

### 0.1 개정본3(패치 검사) 대비

| 구분 | 개정본3 | v4 |
|---|---|---|
| AI 결과 | defects[] bbox·patchScore | 이미지 단위 분류 + Grad-CAM 오버레이 이미지 |
| 입력 | 작업자가 앱에서 부품·검사항목 선택 후 촬영 | 부품별 사진 순차 입력 (입력 프로그램) |
| 접수 | 동기 (분석 끝나야 응답) | 비동기 (202 + inspectionId 즉시 반환) |
| 정책 | 목표 미검출률별 정책 중 선택 | passThreshold를 관리자가 검증 범위 안에서 조정 |
| 알림 | 없음 | REVIEW·FAILED 알림 (Expo 푸시 + 앱 실행 중 폴링) |
| 확인 권한 | 본인/ADMIN | WORKER만 (ADMIN은 조회) |
| 조회 범위 | 본인 검사/ADMIN 전체 | 작업자도 전체 검사 조회 (카메라 입력이라 "본인 검사"가 없음) [제안] |
| 제외 | — | 통계 API·적중률·라인별 빈도·히트맵·모델 재학습 |

### 0.2 개정본3에서 그대로 유지하는 규칙 [승계]

- 공통 응답·오류 형식, traceId, 오류 코드표(5.7)
- Access/Refresh Token, 로그아웃 시 Refresh Token 폐기, 로그인 실패 잠금(TBD-10)
- FAILED는 `recommendedAction`·`finalJudgement` null. **FAILED로 확정된 검사는 이후 변경하지 않음**
- **FAILED 재검사는 새 inspectionId로 생성하고 이전 기록 보존**
- Idempotency-Key로 통신 재전송 식별 (TBD-12). 비동기에 맞춰 응답만 조정 (6.2)
- AI 응답 계약 검증(필수 필드·값 범위·modelVersion 일치), 위반 시 FAILED
- 실행 타임아웃 안에 끝났지만 성능 목표(10초)를 넘긴 검사는 COMPLETED
- 활성 모델은 AI 서버가 실제로 로드할 수 있을 때만 사용 가능으로 표시
- 작업자 확인: 같은 값 재전송은 기존 결과 반환, 다른 값 재제출은 409, 동시 제출 시 1건만 저장
- Mock 모델 버전은 `mock-`, 예시 정책 버전은 `example-` 접두어로 실제와 구분

---

## 1. 담당 경계

| 기능 | 담당 | 백엔드 취급 |
|---|---|---|
| Swin-T 추론, 보정 확률, Grad-CAM 이미지 생성 | AI (김도현) | 추론 응답으로 받아 판정·저장 |
| passThreshold 후보 값, 검증 범위, 평가 근거 | AI (김도현) | 정책 등록 자료로 받아 저장·검증 |
| 검사·이미지·정책·작업자 결과 저장 구조 | DB (김남균) | 9장 변경안 기준으로 협의 |
| 모니터링·상세·REVIEW·관리자 화면 | 앱 (홍승인) | 6장 API, 8장 알림 제공 |
| 접수·AI 호출·정책 적용·알림·권한 | 백엔드 (이승규) | 본 문서 |

---

## 2. 공통 규약 [승계]

- Base URL: `/api/v1`. HTTPS + JSON. 이미지 업로드만 `multipart/form-data`
- 성공 응답: `{ "data": ... }`
- 오류 응답: `{ "error": { "code", "message", "traceId", "inspectionId"?, "status"? } }`
  - `inspectionId`·`status`는 검사와 연결된 오류에만 포함
- ID: UUID 문자열. 시각: ISO-8601 오프셋 포함 (`2026-10-15T14:03:21+09:00`)
- 화면 표시용 검사 번호 `inspectionNo`: `INS-000006` 형식, 백엔드가 접수 순서로 발급. 내부 식별·API 경로는 `inspectionId`(UUID) 사용 [제안, 10/15 앱 프로토타입 검토 반영]
- 확률 값: 0~1 소수, 소수점 6자리
- 인증: `Authorization: Bearer <accessToken>`
- 응답 헤더 `X-Trace-Id`로 서버 로그 추적. 로그에 비밀번호·토큰·서명값을 남기지 않음

### 역할

| 역할 | 주체 | 비고 |
|---|---|---|
| `WORKER` | 현장 작업자 | 모니터링, 상세 조회, REVIEW 최종 판정 |
| `ADMIN` | 시스템 관리자 | 전체 조회, 정책 관리. **REVIEW 판정은 하지 않음** [확정] |
| `DEVICE` | 사진 입력 프로그램 | 검사 접수만 가능 [합의 10/15] |

관리자 API는 앱 메뉴 숨김과 별개로 서버에서 권한 검사 → 작업자가 직접 호출하면 403 [확정]

---

## 3. 검사 상태 모델

### 3.1 필드

| 필드 | 값 | 설명 |
|---|---|---|
| `status` | `RECEIVED` / `ANALYZING` / `COMPLETED` / `FAILED` | 처리 단계. RECEIVED는 v4 추가 |
| `recommendedAction` | `AUTO_PASS` / `REVIEW` / `null` | 정책 적용 결과. COMPLETED에서만 값 존재 [승계] |
| `finalJudgement` | `PASS` / `FAIL` / `null` | 최종 판정 [승계] |
| `judgedBy` | `SYSTEM` / `WORKER` / `null` | 최종 판정 주체. AUTO_PASS는 SYSTEM [제안] |
| `displayState` | 아래 표 | 앱 표시용 파생 값 [제안] |

### 3.2 상태 조합 (앱은 `displayState`만 보고 표시해도 됨)

| displayState | status | recommendedAction | finalJudgement | judgedBy | 알림 |
|---|---|---|---|---|---|
| `ANALYZING` | RECEIVED / ANALYZING | null | null | null | 없음 |
| `AUTO_PASS` | COMPLETED | AUTO_PASS | PASS | SYSTEM | 없음 |
| `REVIEW_PENDING` | COMPLETED | REVIEW | null | null | **확인 필요 알림** |
| `REVIEW_DONE` | COMPLETED | REVIEW | PASS / FAIL | WORKER | 없음 |
| `FAILED` | FAILED | null | null | null | **오류 알림** |

규칙
- FAILED이면 `recommendedAction`과 `finalJudgement`는 반드시 null [확정·승계]
- AUTO_PASS는 작업자 확인이 아니므로 작업자 확인 기록을 만들지 않음 [확정]
- REVIEW는 불량 확정이 아님. 정상 쪽 예측이어도 AUTO_PASS 조건을 못 맞추면 REVIEW [확정]
- 불량(DEFECT) 예측은 보정 확률과 관계없이 항상 REVIEW. 자동 FAIL은 없음 [합의 10/15]
- 작업자 판정은 AI 결과·정책 결과를 덮어쓰지 않고 별도로 저장 [확정·승계]

### 3.3 상태 전이

```
RECEIVED ──▶ ANALYZING ──▶ COMPLETED (AUTO_PASS)
                       ├─▶ COMPLETED (REVIEW) ──▶ 작업자 PASS/FAIL
                       └─▶ FAILED (이후 변경 없음)
                                │
                     재검사 요청 → 새 inspectionId로 RECEIVED (retryOf = 원래 ID)
```

---

## 4. AUTO_PASS 판정 규칙 (백엔드 수행)

분석이 정상 완료된 건에 대해 아래 조건을 **모두** 만족하면 AUTO_PASS, 하나라도 아니면 REVIEW [확정·합의 10/15]

1. `predictedQuality = GOOD` (DEFECT 예측은 확률과 무관하게 REVIEW) [합의 10/15, TBD-06 해소]
2. `calibratedDefectProbability`가 null이 아님
3. 해당 부품·`modelVersion`·`calibratorVersion`에 맞는 정책이 존재 [보정기 버전 호환: 합의 10/15]
4. 그 정책이 `ready = true` 이고 `active = true`
5. `calibratedDefectProbability ≤ passThreshold`

- `predictedQuality`는 AI가 보정 전 softmax 불량 점수(`rawDefectProbability`) 0.5 이상이면 DEFECT, 미만이면 GOOD으로 반환. 이 0.5는 학습 분류 기준이며 passThreshold와 별개 [합의 10/15]
- 비교 대상은 **보정된 불량 확률**. 보정 전 점수를 쓰지 않음 [확정]
- 판정 당시의 정책 버전과 `passThreshold`를 검사 기록에 스냅숏으로 저장 → 기준이 바뀌어도 과거 판정은 그대로 [확정]
- Grad-CAM 유무는 판정에 쓰지 않음. Grad-CAM이 없다는 사실을 정상 확정이나 자동 통과 근거로 쓰지 않음 [확정·합의 10/15]
- AI 파트의 정책 평가도 같은 규칙(GOOD 예측 건만 자동 통과 후보)으로 진행 [합의 10/15]

REVIEW 사유 코드 `reviewReason` [확정 10/15]: 앱 상세 화면에서 "왜 확인이 필요한지" 표시용

| 우선순위 | reviewReason | 의미 |
|---|---|---|
| 1 | `DEFECT_PREDICTED` | AI가 불량으로 예측 |
| 2 | `NO_ACTIVE_POLICY` | 부품·모델·보정기 버전에 맞는 정책이 없거나 ready·active가 아님 |
| 3 | `CALIBRATION_UNAVAILABLE` | 보정 확률이 null |
| 4 | `ABOVE_THRESHOLD` | 보정 불량 확률 > passThreshold |

- 여러 사유가 동시에 해당하면 우선순위가 가장 높은 **하나만** 기록 [제안]. 나머지 근거는 상세의 `ai`·`policy` 블록 값으로 확인 가능
- 예: DEFECT 예측 + 정책 없음 → `DEFECT_PREDICTED`

---

## 5. 처리 흐름 (비동기 접수)

```
입력 프로그램 ─POST /inspections─▶ 백엔드: 입력 검증, 원본 저장, RECEIVED, 202 반환
                                      │ (스레드 풀에서 처리)
                                      ▼
                               ANALYZING ─▶ AI /predict
                                      │
                       성공: 응답 검증 → Grad-CAM 저장 → 정책 적용 → COMPLETED
                       실패: FAILED + error_code (이후 변경 없음)
                                      │
                       REVIEW 또는 FAILED이면 푸시 알림 발송
```

- 다음 사진은 이전 사진 분석 완료를 기다리지 않고 접수 가능 [확정 방향, 구현 방식은 제안]
- 구현: Spring `@Async` + `ThreadPoolTaskExecutor`. 별도 메시지 큐 없음 [제안]
- AI 동시 호출 수는 풀 크기로 제한 (초기값 2, 실측 후 조정) [제안]
- 동시에 분석하므로 **완료 순서는 접수 순서와 달라질 수 있음**. 모니터링·목록은 완료 순서가 아니라 접수 시각(`receivedAt`) 기준으로 정렬하고, 알림은 각 검사가 완료되는 시점에 발송 [확정 10/15]
- 서버 재시작 시 RECEIVED로 남은 건은 다시 처리. ANALYZING으로 남은 건은 결과를 알 수 없으므로 FAILED(`INTERNAL_SERVER_ERROR`)로 확정 [제안]

---

## 6. API

### 6.1 전체 목록

| 메서드 | 경로 | 설명 | 권한 |
|---|---|---|---|
| POST | `/auth/login` | 로그인·토큰 발급 | 공개 |
| POST | `/auth/refresh` | 토큰 재발급 | Refresh Token |
| POST | `/auth/logout` | 로그아웃 (Refresh Token 폐기, 기기 토큰 해제) | 인증 |
| GET | `/parts` | 부품 목록·모델 사용 가능 여부·정책 적용 여부 | WORKER, ADMIN |
| POST | `/inspections` | 사진 접수 (비동기, 선택 헤더 Idempotency-Key) | DEVICE (ADMIN은 시연용 허용) |
| GET | `/monitoring/parts` | 부품별 최근 상태 요약 | WORKER, ADMIN |
| GET | `/monitoring/queue` | 확인 필요·오류 목록 | WORKER, ADMIN |
| GET | `/inspections` | 검사 이력 (필터·페이지) | WORKER, ADMIN |
| GET | `/inspections/{id}` | 검사 상세 (원본·Grad-CAM 접근 정보 포함) | WORKER, ADMIN |
| POST | `/inspections/{id}/confirm` | REVIEW 최종 판정 | **WORKER** |
| POST | `/inspections/{id}/retry` | FAILED 재검사 (새 검사 생성) | WORKER, ADMIN |
| POST | `/notifications/devices` | 푸시 기기 토큰 등록 | WORKER, ADMIN |
| DELETE | `/notifications/devices/{token}` | 기기 토큰 해제 | WORKER, ADMIN |
| GET | `/admin/models` | 모델 버전·로드 가능 여부 조회 | ADMIN |
| GET | `/admin/policies` | 정책 목록·ready·active·평가 근거 | ADMIN |
| POST | `/admin/policies` | 정책 등록 (AI 검증 자료) | ADMIN [TBD-03] |
| POST | `/admin/policies/{id}/threshold` | passThreshold 조정 → 새 버전 생성 | ADMIN |
| POST | `/admin/policies/{id}/activate` | 적용 시작 | ADMIN |
| POST | `/admin/policies/{id}/deactivate` | 적용 중지 | ADMIN |
| POST | `/internal/v1/predict` | AI 추론 (7장) | 백엔드 → AI |
| GET | `/internal/v1/models` | AI 서버의 로드 가능 모델 확인 | 백엔드 → AI |

개정본3 대비 제외
- `/statistics`: 이번 범위 제외 [확정]. 집계용 데이터는 계속 저장 (9.1)
- `/recalculations`: 개정본3에서도 "프로토타입 범위 밖, 설계만 제시". 유지 여부 [TBD-15]
- 모델 등록·활성화 API (`POST /models`, `PUT /models/{id}/activation`): 시드 데이터·설정으로 대체하고 조회만 제공 [제안]. 로드 가능 여부 확인 규칙은 유지 [승계]

### 6.2 사진 접수 `POST /inspections`

요청 (`multipart/form-data`)

| 필드 | 필수 | 설명 |
|---|---|---|
| `image` | Y | JPEG/PNG, 최대 20MB (임시 기준, TBD-08). 원본의 해상도·압축을 바꾸지 않음 [승계] |
| `partCode` | Y | 부품 코드 (`DOOR` 등) |
| `lineCode` | N | 라인 식별값. 없으면 null 저장. 지금은 보내지 않아도 됨 (향후 라인별 통계 대비, 9.1) |
| `capturedAt` | N | 촬영(모사) 시각. 없으면 접수 시각 사용 |

선택 헤더: `Idempotency-Key` [승계, TBD-12]

응답 `202 Accepted`

```json
{
  "data": {
    "inspectionId": "8f3c1e2a-...",
    "inspectionNo": "INS-000008",
    "partCode": "DOOR",
    "status": "RECEIVED",
    "receivedAt": "2026-10-15T14:03:21+09:00"
  }
}
```

Idempotency-Key 재전송 처리 (비동기에 맞춰 조정)

| 상황 | 개정본3 (동기) | v4 (비동기) |
|---|---|---|
| 같은 키 + 같은 사진·partCode, 처리 완료 | 기존 결과 반환 | 기존 `inspectionId`와 현재 `status` 반환 (200), 새 검사 생성 안 함 |
| 같은 키 + 같은 사진·partCode, 처리 중 | 409 `REQUEST_IN_PROGRESS` | 위와 같음 (200). 비동기라 처리 중을 오류로 볼 필요가 없음 [제안] |
| 같은 키 + 다른 사진·partCode | 422 `IDEMPOTENCY_KEY_MISMATCH` | 동일 [승계] |
| 키 없음 | 매 요청을 새 검사로 처리 | 동일 [승계] |

같은 사진 판단은 저장된 원본 체크섬으로 비교 [승계]

오류: `400 INVALID_PART_CODE`, `400 INVALID_IMAGE_FORMAT`, `400 IMAGE_RESOLUTION_TOO_LOW`, `413 IMAGE_TOO_LARGE`, `422 MODEL_NOT_AVAILABLE`, `422 IDEMPOTENCY_KEY_MISMATCH`, `500 STORAGE_UPLOAD_FAILED`

- 모델이 없거나 로드할 수 없는 부품은 검사 기록을 만들기 전에 422로 거절 [승계]
- 부품 하나에 라인 하나이므로 모니터링 단위는 `partCode` [확정]. 라인 마스터·라인 관리 API는 만들지 않고 `lineCode`는 저장만 해 둠 [제안]

### 6.3 부품별 모니터링 `GET /monitoring/parts`

```json
{
  "data": [
    {
      "partCode": "DOOR",
      "partName": "도어",
      "modelAvailable": true,
      "policyActive": false,
      "lastReceivedAt": "2026-10-15T14:03:21+09:00",
      "pendingReviewCount": 3,
      "failedCount": 1,
      "recent": [
        { "inspectionId": "...", "displayState": "REVIEW_PENDING",
          "receivedAt": "...", "thumbnailUrl": "..." }
      ]
    }
  ]
}
```

- `recent`: 부품별 최근 N건 (기본 10) [제안]
- 통계로 확장하지 않음. 건수는 화면 배지 표시용 [확정]

### 6.4 확인 필요 목록 `GET /monitoring/queue`

쿼리: `type=REVIEW|FAILED|ALL` (기본 ALL), `partCode`, `cursor`, `size`(기본 20)

```json
{
  "data": {
    "items": [
      {
        "inspectionId": "...",
        "partCode": "DOOR",
        "displayState": "REVIEW_PENDING",
        "predictedQuality": "GOOD",
        "reviewReason": "NO_ACTIVE_POLICY",
        "errorCode": null,
        "receivedAt": "...",
        "thumbnailUrl": "..."
      }
    ],
    "nextCursor": "..."
  }
}
```

- 오래된 순으로 정렬 (먼저 들어온 사진부터 확인) [제안]
- FAILED 건 중 이미 재검사한 건은 목록에서 제외 [제안]
- 목록 항목 선택 → `GET /inspections/{id}`로 상세 이동 [확정]

### 6.5 검사 상세 `GET /inspections/{id}`

```json
{
  "data": {
    "inspectionId": "...",
    "inspectionNo": "INS-000006",
    "partCode": "DOOR",
    "lineCode": null,
    "status": "COMPLETED",
    "displayState": "REVIEW_PENDING",
    "receivedAt": "...",
    "completedAt": "...",
    "retryOf": null,

    "ai": {
      "modelVersion": "mock-door-swin-t-v1",
      "calibratorVersion": null,
      "predictedQuality": "GOOD",
      "rawDefectProbability": 0.231044,
      "calibratedDefectProbability": null,
      "inferenceTimeMs": 412
    },
    "policy": {
      "automationPolicyReady": false,
      "policyVersion": null,
      "passThreshold": null,
      "recommendedAction": "REVIEW",
      "reviewReason": "CALIBRATION_UNAVAILABLE"
    },
    "judgement": {
      "finalJudgement": null,
      "judgedBy": null,
      "confirmedBy": null,
      "confirmedAt": null
    },
    "images": {
      "original": { "url": "...", "width": 3024, "height": 4032 },
      "gradcam": null,
      "gradcamStatus": "NOT_REQUIRED",
      "urlExpiresAt": "2026-10-15T14:13:21+09:00"
    },
    "error": null
  }
}
```

- AI 결과, 정책 결과, 작업자 판정을 블록으로 분리 [확정·승계]
- Grad-CAM은 원본에 히트맵을 겹친 이미지. 결함 좌표·마스크가 아님 [확정]
- `gradcamStatus` [합의 10/15 반영, 값 이름은 제안]
  - `GENERATED`: DEFECT 예측이고 Grad-CAM 생성 성공 → `images.gradcam`에 접근 정보
  - `NOT_REQUIRED`: GOOD 예측이라 생성하지 않음 → 앱은 원본과 AI 결과만 표시
  - `FAILED`: DEFECT 예측인데 생성 실패 → "판단 근거 이미지 없음" 표시. 검사는 COMPLETED 유지
  - 셋 다 판정에는 영향 없음
- 이미지 접근 정보는 만료됨. 만료되면 상세를 다시 조회 [승계]. 저장소가 로컬이든 S3든 앱 쪽 계약은 같음 (TBD-01)
- `width`·`height`는 방향 보정된 표시 기준 [승계]. 원본과 Grad-CAM의 방향을 맞추는 처리 지점은 [TBD-09]
- FAILED이면 `ai`·`policy`는 null, `error`에 `{ "code", "message", "retryable" }`
- 앱은 passThreshold를 해석해 상태를 바꾸지 않고 백엔드가 준 상태를 표시 [승계]

### 6.6 검사 이력 `GET /inspections`

쿼리: `partCode`, `displayState`, `from`, `to`, `page`(0부터), `size`(기본 20)
응답: 6.4 항목 형식 + `finalJudgement`, `judgedBy`, `confirmedAt`

- 작업자도 모든 검사를 조회 가능 [제안]. 합의본 표현은 "공통 업무 범위에서 조회"

### 6.7 작업자 확인 `POST /inspections/{id}/confirm`

```json
{ "finalJudgement": "FAIL", "comment": "도장 스크래치 확인" }
```

- `displayState = REVIEW_PENDING`인 건만 가능
- 응답 `200`: `{ inspectionId, inspectionNo, predictedQuality, recommendedAction, finalJudgement, judgedBy, confirmedBy, confirmedAt }` (앱 판정 제출 결과 화면용) [제안]
- 같은 값 재전송은 기존 결과 반환(200), 다른 값 재제출은 `409 ALREADY_CONFIRMED`, 동시 제출 시 1건만 저장 [승계]
- 오류: `409 NOT_REVIEWABLE` (AUTO_PASS·FAILED·분석 중), `403 ACCESS_DENIED` (ADMIN·DEVICE 호출)
- `comment`는 선택, 최대 200자 [제안]

### 6.8 재검사 `POST /inspections/{id}/retry`

- FAILED 건만 가능. **새 inspectionId로 검사를 만들고 이전 FAILED 기록은 그대로 둠** [승계]
- 권한: WORKER·ADMIN 모두 허용 [확정 10/15]
- 저장된 원본을 다시 사용하므로 사진을 다시 올리지 않음. 새 검사의 `retryOf`에 원래 ID 기록 [제안]
- 응답 `202`: 새 검사의 `{ inspectionId, inspectionNo, status: "RECEIVED", retryOf }`
- 오류: `409 NOT_RETRYABLE` (FAILED가 아님), `409 ALREADY_RETRIED` (이미 재검사함) [제안]

### 6.9 관리자: 모델·정책

정책 1건 형식

```json
{
  "policyId": "...",
  "policyVersion": "example-door-p1",
  "partCode": "DOOR",
  "modelVersion": "mock-door-swin-t-v1",
  "calibratorVersion": "example-cal-v1",
  "passThreshold": 0.032,
  "validatedMin": 0.020,
  "validatedMax": 0.045,
  "ready": true,
  "active": false,
  "metrics": { "sampleCount": 0, "note": "AI 검증 결과 요약" },
  "createdAt": "...",
  "activatedAt": null
}
```

- `ready`: 검증 근거가 준비됐는지. `active`: 현재 적용 중인지 [확정]
- 위 숫자는 형식 예시일 뿐 실제 값이 아님. 실제 값과 범위는 AI 검증 후 제공 [확정]. 검증 전 시연용 정책은 `example-` 접두어 [승계]
- **threshold 조정**: `{ "passThreshold": 0.030 }`. `validatedMin ≤ 값 ≤ validatedMax`가 아니면 `400 POLICY_THRESHOLD_OUT_OF_RANGE`. 통과하면 기존 정책을 수정하지 않고 **새 버전을 만들고** `active = false`로 시작 [제안]
- **activate**: `ready = true`이고 활성 모델과 호환되는 정책만 가능, 아니면 `409 POLICY_NOT_READY` [승계]. 같은 부품·모델 버전의 다른 정책은 자동으로 비활성 (active 최대 1개) [승계]
- `ready`는 AI 검증 자료를 등록할 때 검증 기준 충족 여부로 결정. 자료 등록만으로 ready=true가 되거나 관리자가 임의로 지정하지 않음 [합의 10/15]. 실제 ready 기준 값과 허용 범위는 AI 평가 후 제공 [TBD-03]
- 정책은 `modelVersion`과 `calibratorVersion`이 모두 맞는 검사에만 적용 [합의 10/15]
- 모델 가중치·보정값 수정 API는 만들지 않음 [확정]
- `GET /admin/models`: 모델 버전, 부품, AI 서버 로드 가능 여부, 활성 여부 조회만 제공 [제안]

---

## 7. AI 연동 규격 [합의 10/15]

### 7.1 요청 `POST {AI}/internal/v1/predict`

```json
{
  "inspectionId": "8f3c1e2a-...",
  "partCode": "DOOR",
  "requestedModelVersion": "mock-door-swin-t-v1",
  "imageUrl": "<만료되는 접근 URL>"
}
```

`inspectionItemCode`는 TBD-04 결정에 따라 유지·삭제

### 7.2 정상 응답

```json
{
  "inspectionId": "8f3c1e2a-...",
  "modelVersion": "mock-door-swin-t-v1",
  "predictedQuality": "GOOD",
  "rawDefectProbability": 0.231044,
  "calibratedDefectProbability": null,
  "calibratorVersion": null,
  "imageWidth": 3024,
  "imageHeight": 4032,
  "gradcam": null,
  "inferenceTimeMs": 412
}
```

| 필드 | 필수 | 규칙 |
|---|---|---|
| `inspectionId` | Y | 요청과 같은 값 [합의 10/15] |
| `modelVersion` | Y | 요청한 `requestedModelVersion`과 같아야 함 [승계] |
| `predictedQuality` | Y | `GOOD` / `DEFECT`. `rawDefectProbability ≥ 0.5`이면 DEFECT [합의 10/15] |
| `rawDefectProbability` | Y | 보정 전 softmax 불량 점수. 0~1 유한한 값 [합의 10/15]. 명칭 [TBD-07] |
| `calibratedDefectProbability` | N | 보정기 준비 전이면 null → 백엔드가 REVIEW 처리. null 허용과 계약 위반은 구분 [승계] |
| `calibratorVersion` | N | 보정값이 있으면 필수, 없으면 둘 다 null [합의 10/15] |
| `imageWidth`, `imageHeight` | Y | 방향 보정된 표시 기준 크기 [승계, TBD-09] |
| `gradcam` | N | **DEFECT 예측 건만 생성**. `{ targetClass: "DEFECT", format: "png", imageBase64 }`. GOOD 예측이거나 생성 실패면 null [합의 10/15] |
| `inferenceTimeMs` | Y | AI 서버가 요청을 받은 시점부터 응답 직전까지(이미지 읽기·전처리·추론·Grad-CAM 생성 포함, 모델 최초 로드 제외) [제안, 측정 범위 AI 확인] |

- Grad-CAM 전달: 응답 안에 base64 PNG로 포함 [합의 10/15]. 용량 문제가 생기면 multipart로 변경
- `gradcam = null`일 때 백엔드가 `gradcamStatus`를 정함: GOOD 예측이면 `NOT_REQUIRED`, DEFECT 예측이면 `FAILED`. 어느 쪽도 검사를 FAILED로 만들지 않음 [합의 10/15]
- 원본과 Grad-CAM은 같은 표시 방향·크기 기준. 학습 전처리 여백 제거와 원본 크기 복원은 AI에서 수행 [합의 10/15]
- 학습과 같은 EXIF 방향 처리·리사이즈·여백·정규화는 AI 쪽에서 수행 [확정]
- 백엔드는 Grad-CAM 이미지를 저장소에 따로 보관하고, `ai_response_json`에는 이미지 데이터를 빼고 나머지 응답만 저장 [제안]
- AI는 분류가 끝난 경우에만 정상 응답. 분류 실패는 필수 값을 null로 채운 정상 응답이 아니라 HTTP 오류 상태와 오류 본문으로 반환 [합의 10/15]
- AI 오류 본문: `{ "error": { "code", "message", "traceId", "inspectionId" } }` (공통 형식과 동일) [합의 10/15]

### 7.3 실패 처리 [승계]

| 상황 | 결과 |
|---|---|
| 연결 실패·5xx·모델 로드 실패 | `AI_SERVER_ERROR` → FAILED. 자동 재시도 1회 후 확정 |
| AI 4xx (요청 형식 오류, 지원하지 않는 모델 버전, 이미지 읽기 불가 등) | `AI_REQUEST_REJECTED` → FAILED. 재시도하지 않음. AI 오류 코드·메시지는 `error_detail`에 그대로 저장 [제안, AI 요청 반영] |
| 실행 타임아웃 (설정값, TBD-01) | `AI_SERVER_TIMEOUT` → FAILED. 이후 AI 결과가 와도 상태를 바꾸지 않음 |
| 필수 필드 누락·범위 밖 값·`modelVersion` 불일치 | `AI_RESPONSE_INVALID` → FAILED |

- 개발 중에는 이 규격대로 Mock AI 서버를 띄워 연동. Mock 모델 버전은 `mock-` 접두어 [승계]

---

## 8. 알림 계약 (홍승인 확인 필요)

### 8.1 방식

앱은 React Native + Expo로 확정, iPhone 실행까지 확인됨 [합의 10/15]

| 상황 | 방식 | 범위 |
|---|---|---|
| 앱 실행 중 (iOS·Android) | `/monitoring/parts`·`/monitoring/queue`를 **5초 간격 폴링** | **필수** [확정] |
| 앱 종료·백그라운드 (Android) | Expo 푸시 알림 서비스로 발송 (Android는 FCM 경유) | 권장 [제안] |
| 앱 종료·백그라운드 (iOS) | Expo 푸시 알림 서비스 (APNs 경유) | 선택 [제안, TBD-14] |

- iOS 원격 푸시는 Apple Developer Program 유료 계정과 APNs 인증 키가 있어야 함. 계정이 없으면 이번 필수 범위에서 제외하고 앱 실행 중 폴링으로 대체 (합의본이 허용한 대안) [제안, 팀 결정 필요]
- 백엔드는 FCM을 직접 호출하지 않고 Expo Push API로 보내는 방식을 제안. 앱이 받은 Expo 푸시 토큰을 등록하면 Android·iOS 발송 코드를 하나로 유지할 수 있음 [제안]
- 촬영 시점과 알림 도착 시점이 같다고 표현하지 않음 [확정]

### 8.2 발송 대상·이벤트

| 이벤트 | 발송 조건 | 대상 |
|---|---|---|
| `REVIEW_REQUIRED` | COMPLETED + REVIEW | 등록된 WORKER·ADMIN 기기 전체 [제안] |
| `ANALYSIS_FAILED` | FAILED | 등록된 WORKER·ADMIN 기기 전체 [제안] |
| (없음) | AUTO_PASS | 발송 안 함 |

### 8.3 푸시 data payload

```json
{
  "type": "REVIEW_REQUIRED",
  "inspectionId": "8f3c1e2a-...",
  "inspectionNo": "INS-000006",
  "partCode": "DOOR",
  "occurredAt": "2026-10-15T14:03:24+09:00"
}
```

- 알림 탭하면 `inspectionId`로 상세 화면 이동
- 기기 토큰 등록: 로그인 직후 `POST /notifications/devices` `{ "token": "ExponentPushToken[...]", "platform": "ANDROID" | "IOS" }`
- 알림 기록 테이블은 두지 않음. 확인 필요 목록은 검사 기록에서 조회 [제안, DB 주간보고의 조건부 Notification 테이블은 미생성]

---

## 9. 저장 구조 변경안 (김남균 협의)

현재 백엔드 코드의 V1 스키마와 개정본3 8.1 속성 기준 변경. V1은 수정하지 않고 Flyway `V3__monitoring_gradcam.sql`로 반영. 김남균 DB 설계 v2(`01_schema.sql`)와 맞춰 작성 [제안]

김남균 동의 사항 [합의 10/15]: `inspection_no` 추가, 원본·Grad-CAM 구분 저장, `judged_by`와 최종 판정 일관성, 재검사 연결, 정책 조정 시 새 버전·기존 기준치 보존, `storage_uri`에 상대 키 저장, 과거 결과 재계산 제외

| 테이블 | 변경 |
|---|---|
| `part` | 그대로. 라인 마스터 테이블은 만들지 않음, partCode가 모니터링 단위 [제안] |
| `inspection_item` | 유지. 모델이 정상·불량 전체를 분류하므로 항목 코드 이름은 AI·DB가 정함 (예: `APPEARANCE`) [TBD-04] |
| `inspection` | `inspection_no`(UNIQUE, NOT NULL, 표시용 번호 `INS-000006`) 추가 · `user_id` → nullable, `source`(DEVICE/ADMIN) 추가 · `status`에 RECEIVED 추가 · `review_reason`, `judged_by`, `pass_threshold_applied`(스냅숏), `gradcam_status`(GENERATED·NOT_REQUIRED·FAILED), `calibrator_version`, `received_at`, `retry_of_inspection_id` 추가 · **`line_code`(nullable), `captured_at` 추가 (9.1)** · 개정본3 속성 중 V1에 없는 `client_request_id`, `ai_response_json`, `error_detail`, `trace_id` 추가 [승계] · `patch_inspection_supported`는 신규 기록에서 미사용 |
| `image_storage` | `storage_uri`는 저장소 상대 키 [합의 10/15] · `image_type`(ORIGINAL/GRADCAM) 추가, `inspection_id` UNIQUE → (`inspection_id`, `image_type`) UNIQUE · `exif_orientation` 추가 [승계, V1에 없음] |
| `automation_policy` | `target_miss_rate` → nullable (과거 기록 보존), `validated_min`·`validated_max`·`calibrator_version`·`activated_at` 추가. `metrics_json`은 AI 평가 근거로 계속 사용 [승계]. 조정 시 행 수정 대신 새 행 |
| `defect_detection` | 신규 기록 중단, 테이블은 유지 (과거 기록 보존) [확정] |
| `ai_model` | `patch_inspection_supported` 신규 미사용. `calibrator_version` 추가 |
| `worker_confirmation` | `comment` 추가. 그 외 그대로 |
| `recalculation_run`·`recalculation_result` | 제외 [합의 10/15, TBD-15 해소] |
| **신규** `device_token` | id, user_id, token(UNIQUE), platform, created_at, last_seen_at |

제약·인덱스
- 복합 FK 유지: 검사의 부품–검사항목, 정책의 모델–검사항목 일치를 DB에서 보장 [승계]
- `(user_id, client_request_id)` UNIQUE, null 허용 [승계]
- 상태 조합 CHECK: AUTO_PASS면 final_judgement=PASS·judged_by=SYSTEM, FAILED면 recommended_action·final_judgement null 등. NULL 비교가 통과되지 않도록 `IS NOT NULL`을 함께 검사 [김남균 DB 설계 반영]
- `final_judgement`와 `worker_confirmation`은 한 트랜잭션으로 저장 [합의 10/15]
- `inspection (part_id, received_at)`: 부품별 최근 목록 [제안]
- `inspection (status, recommended_action, final_judgement, received_at)`: 확인 필요 목록 [제안]
- `inspection (line_code, received_at)`: 라인별 통계를 실제로 만들 때 추가 (지금은 만들지 않음)

### 9.1 향후 통계 대비

통계 화면·API는 이번 필수 범위에서 제외 [확정]. 대신 나중에 추가할 때 과거 기록부터 바로 집계할 수 있도록 **필요한 값은 지금부터 저장**해 둡니다. 통계 전용 컬럼은 따로 만들지 않고, 아래처럼 기존 기록에서 계산합니다.

| 향후 통계 | 계산 근거 (저장 필드) | 비고 |
|---|---|---|
| 확정 불량률 FAIL/(PASS+FAIL) | `final_judgement` | REVIEW 대기·FAILED는 분모에서 제외 [승계] |
| AUTO_PASS·REVIEW 비율, FAILED 건수 | `status`, `recommended_action` | 분석 성공 건을 분모로 [승계] |
| REVIEW 사유별 건수 | `review_reason` | 정책 미적용으로 REVIEW가 된 비율 확인용 |
| AI 예측과 작업자 판정 일치율 | `predicted_quality` + `worker_confirmation.final_judgement` | **REVIEW 건 기준 일치율**. AUTO_PASS는 작업자 확인이 없어 제외되므로 모델 전체 정확도로 표현하지 않음 |
| 라인별 불량 빈도 | `line_code` | 값이 들어오기 시작한 시점 이후만 집계 가능 |
| 시간대·기간별 추이 | `captured_at`, `received_at` | |
| 정책 버전별 자동화율 | `policy_id`, `pass_threshold_applied` | 기준 변경 전후 비교 |
| 작업자 확인 소요 시간 | `completed_at` → `confirmed_at` | |

- 불량 **유형별** 통계는 불가: 현재 AI가 정상·불량 2분류만 반환하므로 유형 정보가 없음

---

## 10. 오류 코드

개정본3 5.7 오류 코드표 유지 [승계] + 아래 변경

| 구분 | HTTP | 코드 | 상황 |
|---|---|---|---|
| 추가 | 400 | `POLICY_THRESHOLD_OUT_OF_RANGE` | 검증 범위 밖 passThreshold |
| 추가 | 404 | `POLICY_NOT_FOUND` | 정책 없음 |
| 추가 | 404 | `IMAGE_NOT_AVAILABLE` | Grad-CAM 없음·이미지 유실 |
| 추가 | 409 | `NOT_RETRYABLE` | FAILED가 아닌 건 재검사 |
| 추가 | 409 | `ALREADY_RETRIED` | 이미 재검사한 FAILED 건 |
| 추가 | 400 | `INVALID_DEVICE_TOKEN` | 기기 토큰 형식 오류 |
| 추가 | 502 | `AI_REQUEST_REJECTED` | AI 서버가 4xx로 요청을 거절 (검사는 FAILED, 재시도 안 함) |
| 미사용 | 409 | `REQUEST_IN_PROGRESS` | 비동기 접수로 불필요 (6.2) [제안] |
| 미사용 | 409 | `MODEL_NOT_LOADABLE` | 모델 활성화 API를 두지 않으면 불필요. 로드 확인 자체는 `/parts`·접수에서 유지 |
| 조건부 | 400 | `INVALID_INSPECTION_ITEM` | TBD-04 결정에 따라 유지·삭제 |

---

## 11. 명세서 반영 현황

- 반영 완료 (명세서 개정본4, 10/15): 표지·통합 기준, 1~3장, 4.2 백엔드, 5장, 6.3, 8장, 9장 일부, 10·11장, 그림 1~8 (시스템 구성·업무 흐름·유스케이스·클래스·ERD·시퀀스 3종) 재작성
- 미반영: 4.1 앱, 4.3 DB, 4.4 AI 요구사항, 9장 NFR-HW-01·QUAL-01·REP-01, 5.6 '미검출률과 정책 평가' 문단 → 각 담당자 개정 후 반영
- 10/15 팀 회신 반영 완료: 판정 규칙(DEFECT 예측 REVIEW), reviewReason, Grad-CAM 생성 대상·상태, 보정기 버전 호환, inspectionNo, AI 4xx 처리, 재계산 제외, Expo 푸시. 명세서 6.3·8.1 표 오류 수정, 그림 1·2·5·6 갱신
- 이후 팀 검토 결과에 따라 그림과 본문을 함께 수정

---

## 12. 미확정 사항 (명세서 11장 번호 체계)

| ID | 내용 | v4 상태 | 백엔드 제안 / 임시 기준 | 확인 대상 |
|---|---|---|---|---|
| TBD-01 | 배포 환경·이미지 저장소·타임아웃 | 유지 | 개발은 로컬 저장소·Mock AI. 계약은 "만료되는 접근 정보"로만 기술 | 이승규·김도현·김남균 |
| TBD-02 | 목표 미검출률 지정 방식 | **폐지** | 합의본에서 passThreshold 조정 방식으로 대체 | — |
| TBD-03 | ready 판정 기준 값·최소 표본 수 | 일부 확정 | 설정 주체는 확정(검증 자료 등록 시 기준 충족 여부로 결정). 기준 값은 AI 평가 후 제공 | 김도현 |
| TBD-04 | 검사항목 코드 이름 | 일부 확정 | 테이블 유지, API 비노출. 이름만 결정 (예: APPEARANCE) | 김남균·김도현 |
| TBD-05 | AI 응답 세부·오류 본문·Grad-CAM 전달 | **해소** | base64 PNG, DEFECT 예측만 생성, 오류는 공통 형식 (7장) | — |
| TBD-06 | predictedQuality와 정책 판정의 충돌 처리 | **해소** | DEFECT 예측은 항상 REVIEW, GOOD 예측만 AUTO_PASS 후보 (4장) | — |
| TBD-07 | rawDefectProbability 명칭 | 유지 | 현재 명칭 유지 | 전체 |
| TBD-08 | 업로드 형식·용량·해상도 | 유지 | JPEG·PNG, 20MB, 최소 해상도 검사 없음 | 이승규·김도현 |
| TBD-09 | EXIF 방향 보정 처리 지점 | 확장 | 원본과 Grad-CAM의 방향 일치까지 포함 | 이승규·김도현·홍승인 |
| TBD-10 | 로그인 실패 잠금 기준 | 유지 | 임시 5회, 관리자 해제 | 이승규 |
| TBD-11 | 시연·지원 부품 범위 | 일부 확정 | 시연·초기 연동은 도어. 최종 목표 약 4개 부품, 추가 부품과 시점은 AI가 추후 공유. 모델 없는 부품은 미지원 표시, 등록 정보 추가로 확장하는 구조 유지 | 김도현 |
| TBD-12 | Idempotency-Key 적용 여부 | 갱신 | 적용 주체가 앱에서 입력 프로그램으로 바뀜 | 이승규 |
| TBD-13 | 입력 프로그램 인증 | **해소** | DEVICE 역할 계정 로그인 → JWT | — |
| TBD-14 | iOS 종료·백그라운드 푸시 포함 여부 | 일부 확정 | RN + Expo 확정. 앱 실행 중 폴링 필수, Android 푸시 권장, iOS 푸시는 Apple Developer 계정 여부에 따라 결정 (8.1) | 전체 |
| TBD-15 | 과거 결과 재계산 설계 유지 여부 | **해소** | 제외 | — |
