# 백엔드 API 계약 v4 (11/18 갱신 · 최종 확정 전)

3조 김이홍 · 백엔드 API 이승규 · 2026-10-15 작성 · 10/28 갱신 (AI 연동 준비·V5: 6.5, 7.2, 9장, 12장) · 11/02 갱신 (구현 세부 반영: 6.1~6.4, 6.6~6.9, 7.4, 8장, 10장, 12장) · 11/04 갱신 (실제 AI 연결 확인: 7.3, 7.4, 12장 TBD-01) · 11/05 갱신 (통합 시험: 6.2 모델 확인 타임아웃, 8.4 앱 시험, 12장 TBD-01·14) · 11/09 갱신 (12장 TBD-01 실행 타임아웃 20초) · 11/10 갱신 (6.1·6.9 계정 잠금 해제, 9.1 통계, 10장 USER_NOT_FOUND, 12장 TBD-10·14) · 11/11 갱신 (6.3 recent inspectionNo, 12장 TBD-01 부품별 AI 서버, **수동 판정** 3장·4장·6.1·6.5·6.6·6.8·6.10·10장) · 11/17 갱신 (TBD-04 확정 `UNIFIED`: 7장·9장·12장) · 11/18 갱신 (6.1 검사 기록 CSV 내보내기, 6.6 `mismatch` 필터) · 11/23 제안 (REVIEW 개선·판정 확인 요청: 6.1·6.4·6.5·6.6·6.7.1·6.12·10장·12장 TBD-18·19 / 자동 불량·날짜별 이력: 3장·4.1·6.9·6.13·8.2)

- 기준 1: 「자동차부품_공정모니터링_개발계획서_최종합의반영」(10/14 합의본)
- 기준 2: 「요구사항명세서_패치검사_개정본3」(9/30)의 규칙 중 합의본과 충돌하지 않는 것은 그대로 승계
- 기준 3: 10/15 팀 회신 (김도현 AI 답변, 홍승인 정리, 김남균 DB 주간보고)
- 기준 4: 10/28 합의 (AI 김도현·모바일 홍승인·DB 김남균 확인): 실제 DOOR 모델 버전, Grad-CAM 0맵·상수맵, JPEG 허용, V5 무결성 제약

표기
- **[확정]** 합의본에 명시된 내용
- **[승계]** 명세서 개정본3에서 이미 정한 규칙을 그대로 유지
- **[합의 10/15]** 10/15 팀 회신으로 확정된 내용
- **[합의 10/28]** 10/28 팀 확인으로 확정된 내용
- **[제안]** 합의본이 백엔드에 결정을 맡긴 부분. 이의가 없으면 이대로 구현
- **[구현 MM/DD]** 계약에 없어서 구현하면서 정한 세부. 이의가 있으면 이승규에게 알림
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
| `recommendedAction` | `AUTO_PASS` / `AUTO_FAIL` / `REVIEW` / `null` | 정책 적용 결과. COMPLETED에서만 값 존재 [승계]. `AUTO_FAIL`은 4.1 [제안 11/23] |
| `finalJudgement` | `PASS` / `FAIL` / `null` | 최종 판정 [승계] |
| `judgedBy` | `SYSTEM` / `WORKER` / `null` | 최종 판정 주체. AUTO_PASS·AUTO_FAIL은 SYSTEM [제안] |
| `displayState` | 아래 표 | 앱 표시용 파생 값 [제안] |
| `source` | `DEVICE` / `ADMIN` / `RETRY` / `MANUAL` | 검사가 생긴 경로. `MANUAL`은 AI 없이 작업자 판정용으로 만든 검사 (6.10) [구현 11/11] |

### 3.2 상태 조합 (앱은 `displayState`만 보고 표시해도 됨)

| displayState | status | recommendedAction | finalJudgement | judgedBy | 알림 |
|---|---|---|---|---|---|
| `ANALYZING` | RECEIVED / ANALYZING | null | null | null | 없음 |
| `AUTO_PASS` | COMPLETED | AUTO_PASS | PASS | SYSTEM | 없음 |
| `AUTO_FAIL` [제안 11/23] | COMPLETED | AUTO_FAIL | FAIL | SYSTEM | **자동 불량 알림** (8.2) |
| `REVIEW_PENDING` | COMPLETED | REVIEW | null | null | **확인 필요 알림** |
| `REVIEW_DONE` | COMPLETED | REVIEW | PASS / FAIL | WORKER | 없음 |
| `FAILED` | FAILED | null | null | null | **오류 알림** |

규칙
- FAILED이면 `recommendedAction`과 `finalJudgement`는 반드시 null [확정·승계]
- AUTO_PASS는 작업자 확인이 아니므로 작업자 확인 기록을 만들지 않음 [확정]
- REVIEW는 불량 확정이 아님. 정상 쪽 예측이어도 AUTO_PASS 조건을 못 맞추면 REVIEW [확정]
- 불량(DEFECT) 예측은 보정 확률과 관계없이 항상 REVIEW. 자동 FAIL은 없음 [합의 10/15]
  - **11/23 변경 [합의 11/23 김도현, TBD-18]:** 정책에서 자동 불량을 켠 경우에만 4.1 조건을 만족하는 DEFECT 예측이 `AUTO_FAIL`. 기본은 꺼짐이라 켜기 전까지 위 규칙 그대로
- AUTO_FAIL도 작업자 확인 기록을 만들지 않음. 발생 사실은 자동 불량 알림(8.2)으로 알림. 다르게 확인되면 판정 확인 요청(6.12)으로 정정하고 최초 판정은 그대로 [제안 11/23]
- 작업자 판정은 AI 결과·정책 결과를 덮어쓰지 않고 별도로 저장 [확정·승계]
- 수동 판정 건(`source=MANUAL`)은 COMPLETED·REVIEW(`AI_UNAVAILABLE`)로 생성되어 위 표의 `REVIEW_PENDING` → `REVIEW_DONE`을 그대로 따름. AI 결과·정책 값은 없음 (6.10) [구현 11/11]
- AUTO_PASS 건이 표본 재확인(6.11)으로 뽑히고 재확인 결과가 FAIL이어도 `displayState`·`finalJudgement`·`judgedBy`는 **바뀌지 않음**. 재확인 결과는 상세의 `recheck` 블록에 표시하고 원래 판정과 함께 보여 줌 [제안 11/18]

### 3.3 상태 전이

```
RECEIVED ──▶ ANALYZING ──▶ COMPLETED (AUTO_PASS)
                       ├─▶ COMPLETED (AUTO_FAIL, 자동 불량을 켠 정책만)
                       ├─▶ COMPLETED (REVIEW) ──▶ 작업자 PASS/FAIL
                       └─▶ FAILED (이후 변경 없음)
                                │
                     재검사 요청 → 새 inspectionId로 RECEIVED (retryOf = 원래 ID)
                     또는 수동 판정 전환 → 새 inspectionId로 COMPLETED·REVIEW(AI_UNAVAILABLE) → 작업자 PASS/FAIL
                     (FAILED 1건당 재검사·수동 전환 중 1건만)
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
| — | `AI_UNAVAILABLE` | AI 결과 없이 작업자가 판정하는 수동 판정 건 전용. 판정 규칙으로 정해지는 값이 아님 (6.10) [구현 11/11] |

- 여러 사유가 동시에 해당하면 우선순위가 가장 높은 **하나만** 기록 [제안]. 나머지 근거는 상세의 `ai`·`policy` 블록 값으로 확인 가능
- 예: DEFECT 예측 + 정책 없음 → `DEFECT_PREDICTED`

### 4.1 AUTO_FAIL 판정 규칙 [제안 11/23, 합의 11/23 김도현 범위 변경, TBD-18]

분석이 정상 완료된 건이 아래를 **모두** 만족하면 AUTO_FAIL(`FAIL · SYSTEM`), 아니면 지금처럼 REVIEW(`DEFECT_PREDICTED`)

1. `predictedQuality = DEFECT`
2. `calibratedDefectProbability`가 null이 아님
3. 4장 3·4번과 같은 정책(부품·모델·보정기 호환, ready·active)
4. 그 정책의 `autoFailEnabled = true`이고 `failThreshold`가 있음
5. `calibratedDefectProbability ≥ failThreshold` (같으면 자동 불량. 반올림 전 값으로 비교)

- 자동 통과(4장)는 지금처럼 정책 `active`로 켜고 끔. 자동 불량은 같은 정책 안에서 `autoFailEnabled`로 **따로** 켬. 가능한 조합은 둘 다 꺼짐(정책 중지)·자동 통과만·둘 다 켜짐. "자동 불량만"은 두지 않음 [제안] (쓰임이 없고 새 REVIEW 사유가 필요해짐)
- 기본은 꺼짐: 기존 정책과 새로 등록한 정책 모두 `autoFailEnabled = false`, `failThreshold = null`. 과거 검사에 소급하지 않음
- 판정 당시 `failThreshold`를 검사에 스냅숏으로 저장(`failThresholdApplied`). 자동 불량을 켠 정책으로 판정한 건은 AUTO_PASS·REVIEW에도 남고(기준 상세 6.13에 씀), 꺼져 있었으면 null. 정책을 바꿔도 과거 검사의 판정·기준은 그대로
- REVIEW 사유는 바뀌지 않음: 자동 불량 조건을 못 맞춘 DEFECT 예측은 `DEFECT_PREDICTED`
- Grad-CAM은 지금처럼 DEFECT 예측이면 생성 (자동 불량 건도 근거 이미지로 표시). 판정에는 쓰지 않음
- 자동 불량의 정상 오판은 판정 확인 요청(6.12)으로 확인된 건만 셈. 전체 오판율은 추정할 수 없음 (TBD-19)

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
- AI 동시 호출 수는 풀 크기로 제한 (초기값 2 → 11/04 실측 후 1. 실제 AI가 추론·CAM을 한 건씩 처리) [제안]
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
| POST | `/inspections/confirm-batch` | 선택한 REVIEW 건 일괄 FAIL (검사 ID별 결과) [제안 11/23] | **WORKER** |
| POST | `/inspections/{id}/judgement-requests` | 시스템 판정 건 판정 확인 요청 [제안 11/23] | **WORKER** |
| POST | `/inspections/{id}/retry` | FAILED 재검사 (새 검사 생성) | WORKER, ADMIN |
| POST | `/inspections/{id}/manual` | FAILED를 AI 없이 작업자 판정으로 전환 (새 검사 생성) [구현 11/11] | **WORKER** |
| GET | `/rechecks` | AUTO_PASS 표본 재확인 목록 (대기·완료, 결과·확인함 필터) [제안·구현 11/18] | WORKER, ADMIN |
| POST | `/inspections/{id}/recheck` | AUTO_PASS 표본 재확인 결과 기록 (시스템 판정은 그대로, 화면 체류 시간 선택) [제안·구현 11/18] | **WORKER** |
| POST | `/notifications/devices` | 푸시 기기 토큰 등록 | WORKER, ADMIN |
| DELETE | `/notifications/devices/{token}` | 기기 토큰 해제 | WORKER, ADMIN |
| GET | `/admin/models` | 모델 버전·로드 가능 여부 조회 | ADMIN |
| GET | `/admin/policies` | 정책 목록·ready·active·평가 근거 | ADMIN |
| POST | `/admin/policies` | 정책 등록 (AI 검증 자료) | ADMIN [TBD-03] |
| POST | `/admin/policies/{id}/threshold` | passThreshold 조정 → 새 버전 생성 | ADMIN |
| POST | `/admin/policies/{id}/activate` | 적용 시작 | ADMIN |
| POST | `/admin/policies/{id}/deactivate` | 적용 중지 | ADMIN |
| GET | `/admin/policies/{id}/simulation` | 후보 기준치 비교 (같은 검사 기록에 현재·후보 기준치 대입, 조회만) [구현 11/18] | ADMIN |
| POST | `/admin/rechecks/{inspectionId}/acknowledge` | 재확인 FAIL 건 관리자 확인함 (해결 완료 아님) [구현 11/18] | ADMIN |
| GET | `/admin/judgement-requests` | 판정 확인 요청 목록 (대기·처리 완료) [제안 11/23] | ADMIN |
| POST | `/admin/judgement-requests/{requestId}/resolve` | 판정 확인 요청 처리 (유지·정정) [제안 11/23] | ADMIN |
| GET | `/admin/rechecks/summary` | 재확인 요약 (규칙별 구간 집계·누락·대기·비교 비율·대기 시간·체류 시간) [구현 11/18] | ADMIN |
| POST | `/admin/users/{loginId}/unlock` | 계정 잠금 해제 [구현 11/10] | ADMIN |
| GET | `/admin/inspections/export` | 검사 기록 CSV (이력과 같은 partCode·displayState·mismatch·from·to, 접수 시각 오름차순, 최대 10,000건, 엑셀용 UTF-8 BOM, 이미지·AI 원문 제외). 보고서용, 앱 미사용 [구현 11/18] | ADMIN |
| POST | `/internal/v1/predict` | AI 추론 (7장) | 백엔드 → AI |
| GET | `/internal/v1/models` | AI 서버의 로드 가능 모델 확인 | 백엔드 → AI |

개정본3 대비 제외
- `/statistics`: 이번 범위 제외 [확정]. 집계용 데이터는 계속 저장 (9.1)
- `/recalculations`: 개정본3에서도 "프로토타입 범위 밖, 설계만 제시". 유지 여부 [TBD-15]
- 모델 등록·활성화 API (`POST /models`, `PUT /models/{id}/activation`): 시드 데이터·설정으로 대체하고 조회만 제공 [제안]. 로드 가능 여부 확인 규칙은 유지 [승계]

`GET /parts` 응답 항목 [구현 11/02]

```json
{
  "partCode": "DOOR",
  "name": "도어",
  "items": [
    { "inspectionItemCode": "UNIFIED", "name": "...", "modelAvailable": true, "policyActive": true,
      "activeModelVersion": "mock-door-swin-t-v1" }
  ]
}
```

- `modelAvailable`: 활성 모델이 있고 AI 서버 확인 결과가 AVAILABLE일 때만 true (6.2). `/monitoring/parts`와 같은 판단
- `policyActive`: 활성 모델에 ready·active 정책이 있음
- `patchInspectionSupported`는 제거

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

- 모델이 없거나 로드할 수 없는 부품은 검사 기록을 만들기 전에 422로 거절 [승계]. 단, AI 서버에 연결되지 않아 확인할 수 없는 경우는 거절하지 않음 [구현 11/02, 아래 표]

모델 로드 확인 결과 [구현 11/02] (`GET {AI}/internal/v1/models`, 7.4)

| 결과 | 조건 | 접수·재검사 | `modelAvailable` |
|---|---|---|---|
| AVAILABLE | 목록에 있고 `loadable = true` | 정상 접수 | true |
| NOT_LOADABLE | 목록에 없거나 `loadable = false` | 기록·파일 저장 없이 `422 MODEL_NOT_AVAILABLE` | false |
| UNKNOWN | 연결 실패·타임아웃·형식 오류·404 | **정상 접수**. AI 오류면 분석 단계에서 기존 규칙대로 FAILED | false |

- UNKNOWN을 거절하지 않는 이유: AI가 꺼졌을 때 거절하면 사진과 기록이 남지 않아 FAILED → 재검사 흐름이 성립하지 않음
- 결과는 성공 30초·실패 5초 캐시. 확인 전용 타임아웃(연결·읽기 각 2초)을 사용해 접수·모니터링을 오래 잡지 않음. Tailscale 지연이 최대 약 1초라 11/05에 연결 500ms·읽기 1초에서 올림 [구현 11/05]
- 실제 AI에 엔드포인트가 없으면 `app.ai.model-check-enabled=false`로 끄고, 활성 모델이 있으면 AVAILABLE로 판단
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
        { "inspectionId": "...", "inspectionNo": "INS-000001", "displayState": "REVIEW_PENDING",
          "receivedAt": "...", "thumbnailUrl": "..." }
      ]
    }
  ]
}
```

- `recent`: 부품별 최근 N건 (기본 10) [제안]. `inspectionNo`(화면 표시용 번호)는 11/11 추가 [구현 11/11, 홍승인 요청]
- `modelAvailable`: `GET /parts`와 같은 판단 (6.2) [구현 11/02]. AI가 꺼져 UNKNOWN이면 false지만 접수는 가능
- `policyActive`: 활성 모델에 ready·active 정책이 있으면 true [구현 10/19]
- `thumbnailUrl`: 썸네일을 따로 만들지 않고 원본의 서명 주소 사용, 10분 후 만료. 6.4·6.6도 같음 [구현 10/19]
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
- `size` 최대 100, 범위 밖은 `400 INVALID_PARAMETER`. 커서는 (receivedAt, id)를 Base64url로 인코딩한 값이고 `nextCursor`가 null이면 마지막 페이지 [구현 10/19]
- FAILED 건 중 이미 재검사한 건은 목록에서 제외 [제안]
- 목록 항목 선택 → `GET /inspections/{id}`로 상세 이동 [확정]

REVIEW 정렬·필터 [제안 11/23, 김도현 시안]: 기존 호출은 그대로 동작하고 아래는 선택 쿼리로만 추가
- `sort=RECEIVED|PRIORITY` (기본 `RECEIVED` = 지금과 같은 오래된 순)
  - `PRIORITY`: `predictedQuality = GOOD`이고 `reviewReason = ABOVE_THRESHOLD`인 REVIEW를 먼저, 나머지(DEFECT 예측·정책 없음·보정값 없음·수동 판정·FAILED)를 뒤에. 각 그룹 안에서는 오래된 순 유지
  - 커서는 정렬마다 따로 만들어지며, 다른 `sort`의 커서를 주면 `400 INVALID_PARAMETER`. `RECEIVED` 커서 형식은 지금과 같음
- `predictedQuality=GOOD|DEFECT`: AI 예측으로 거름 ("AI 불량 의심" = `type=REVIEW&predictedQuality=DEFECT`). 예측이 없는 FAILED·수동 판정은 이 필터를 주면 나오지 않음. 없는 값은 `400 INVALID_PARAMETER`
- 항목에 `calibratedDefectProbability`, `passThresholdApplied` 추가 (없으면 null). 목록에서 기준 대비 위치를 보여 주기 위한 값이며 앱이 상태를 다시 계산하지 않음 [승계]

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
    "source": "DEVICE",
    "retryOf": null,
    "manualOf": null,
    "followUp": null,

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
    "error": null,
    "recheck": null
  }
}
```

- AI 결과, 정책 결과, 작업자 판정을 블록으로 분리 [확정·승계]
- Grad-CAM은 원본에 히트맵을 겹친 이미지. 결함 좌표·마스크가 아님 [확정]
- `gradcamStatus` [합의 10/15 반영, 값 이름은 제안]
  - `GENERATED`: DEFECT 예측이고 Grad-CAM 생성 성공 → `images.gradcam`에 접근 정보
  - `NOT_REQUIRED`: GOOD 예측이라 생성하지 않음 → 앱은 원본과 AI 결과만 표시
  - `FAILED`: DEFECT 예측인데 생성 실패 → "판단 근거 이미지 없음" 표시. 검사는 COMPLETED 유지
  - `NO_ACTIVATION` [합의 10/28]: DEFECT 예측, Grad-CAM 계산은 성공했지만 위치별 강조 반응 없음(0맵·상수맵) → `images.gradcam = null`. 앱은 "AI 예측은 완료됐지만, 위치별 강조 반응이 없어 판단 근거 이미지를 제공하기 어렵습니다." 안내. 생성 실패(FAILED)·GOOD 미생성(NOT_REQUIRED)과 구분하며, 정상의 증거로 쓰지 않음
  - 넷 다 판정에는 영향 없음
- 이미지 접근 정보는 만료됨. 만료되면 상세를 다시 조회 [승계]. 저장소가 로컬이든 S3든 앱 쪽 계약은 같음 (TBD-01)
- `width`·`height`는 방향 보정된 표시 기준 [승계]. 원본과 Grad-CAM의 방향을 맞추는 처리 지점은 [TBD-09]
- FAILED이면 `ai`·`policy`는 null, `error`에 `{ "code", "message", "retryable" }`. `retryable`은 아직 재검사·수동 전환을 하지 않았을 때만 true [11/11]
- `source` [구현 11/11]: `DEVICE`·`ADMIN`·`RETRY`·`MANUAL`. `retryOf`는 `RETRY`일 때만 원래 FAILED ID
- `manualOf` [구현 11/11]: `MANUAL`일 때만 `{ inspectionId, inspectionNo, errorCode, errorMessage }` (원래 FAILED와 AI 실패 사유). 이때 `ai`는 null, `policy`는 `{ automationPolicyReady: false, policyVersion: null, passThreshold: null, recommendedAction: "REVIEW", reviewReason: "AI_UNAVAILABLE" }`, `images.gradcam`·`gradcamStatus`는 null
- `followUp` [구현 11/11]: FAILED 건에 재검사·수동 전환 검사가 이미 있으면 `{ inspectionId, inspectionNo, source }` (`RETRY`/`MANUAL`). 앱은 버튼을 숨기고 그 검사로 이동
- 앱은 passThreshold를 해석해 상태를 바꾸지 않고 백엔드가 준 상태를 표시 [승계]
- `recheck` [제안 11/18]: AUTO_PASS 표본 재확인(6.11)으로 뽑힌 건만 `{ stratum, samplingRate, ruleVersion, trialName, sampledAt, result, comment, recheckedBy, recheckedAt, acknowledgedBy, acknowledgedAt, acknowledgeNote }`, 아니면 null. 재확인 FAIL이어도 `judgement` 블록(시스템 PASS)은 그대로이므로 **두 블록을 함께** 표시. `acknowledgedAt`이 있으면 "확인함"(해결 완료 아님)
- `policy`에 `failThreshold`(판정 당시 자동 불량 기준, 꺼져 있었으면 null) 추가 [제안 11/23]
- `judgementRequests` [제안 11/23]: 판정 확인 요청(6.12) 목록, 최신순. 없으면 `[]`. 항목 형식은 6.12 요청 1건과 같음
- `correction` [제안 11/23]: 정정된 적이 있으면 마지막 정정 `{ requestId, correctedJudgement, correctedBy, correctedAt, note }`, 없으면 null. **`judgement` 블록(최초 판정)은 바뀌지 않으므로** 정정된 건은 "최초 판정 → 정정 판정"을 함께 표시

### 6.6 검사 이력 `GET /inspections`

쿼리: `partCode`, `displayState`, `mismatch`, `from`, `to`, `page`(0부터), `size`(기본 20)
응답: 6.4 항목 형식 + `source`, `finalJudgement`, `judgedBy`, `confirmedAt` (`source`는 11/11 추가, `MANUAL`이면 "AI 분석 없이 작업자 판정" 표시)

- 작업자도 모든 검사를 조회 가능 [제안]. 합의본 표현은 "공통 업무 범위에서 조회"
- receivedAt 최신순(같으면 id), 기간은 `from ≤ receivedAt < to`, `size` 최대 100, 없는 `partCode`는 `400 INVALID_PART_CODE` [구현 10/19]
- `mismatch`: AI 예측과 작업자 판정이 엇갈린 `REVIEW_DONE` 건만. `ANY`(둘 다)·`DEFECT_PASSED`(AI DEFECT → 작업자 PASS)·`GOOD_FAILED`(AI GOOD → 작업자 FAIL). 수동 판정은 AI 예측이 없어 제외, AUTO_PASS는 사람이 보지 않아 대상 아님. 추가 검토·재학습 후보 선별용이며 전체 오류율이 아님. 없는 값은 `400 INVALID_PARAMETER`, 빈 값은 필터 없음. `REVIEW_DONE` 외의 `displayState`와 함께 주면 빈 결과 [구현 11/18]
- 항목에 `correctedJudgement` 추가 [제안 11/23]: 정정된 건의 마지막 정정 판정, 없으면 null. `finalJudgement`·`judgedBy`는 최초 판정 그대로

### 6.7 작업자 확인 `POST /inspections/{id}/confirm`

```json
{ "finalJudgement": "FAIL", "comment": "도장 스크래치 확인",
  "screenDwellMs": 24300, "firstOpenedAt": "2026-11-19T10:01:02+09:00", "openCount": 1 }
```

- `displayState = REVIEW_PENDING`인 건만 가능
- 응답 `200`: `{ inspectionId, inspectionNo, predictedQuality, recommendedAction, finalJudgement, judgedBy, confirmedBy, confirmedAt }` (앱 판정 제출 결과 화면용) [제안]
- 같은 값 재전송은 기존 결과 반환(200), 다른 값 재제출은 `409 ALREADY_CONFIRMED`, 동시 제출 시 1건만 저장 [승계]
- 오류: `409 NOT_REVIEWABLE` (AUTO_PASS·FAILED·분석 중), `403 ACCESS_DENIED` (ADMIN·DEVICE 호출)
- `comment`는 선택, 최대 200자 [제안]
- 재전송 비교는 `finalJudgement`만 (comment는 비교하지 않음), 공백 comment는 null로 저장 [구현 10/19]
- `screenDwellMs`·`firstOpenedAt`·`openCount` [구현 11/18]: 화면 체류 시간 (선택, 셋 다 보내거나 생략). 규칙은 6.11 "화면 체류 시간"과 같음. 재전송이면 처음 값 유지. 값 오류는 `400 INVALID_PARAMETER`

### 6.7.1 일괄 FAIL `POST /inspections/confirm-batch` [제안 11/23, 김도현 시안]

작업자가 상세를 보고 불량으로 확인해 **직접 고른** REVIEW 건만 한 번에 FAIL로 확정. 판정 주체는 작업자(WORKER)라 4장 판정 규칙과 10/15 합의를 바꾸지 않음

```json
{
  "finalJudgement": "FAIL",
  "comment": "고정핀 들뜸",
  "items": [
    { "inspectionId": "...", "screenDwellMs": 8200, "firstOpenedAt": "2026-11-24T10:01:02+09:00", "openCount": 1 },
    { "inspectionId": "..." }
  ]
}
```

- `finalJudgement`는 `FAIL`만 허용 (일괄 PASS 없음). 다른 값은 `400 INVALID_PARAMETER`
- `items` 1~50건. 같은 `inspectionId`가 두 번 있거나 범위 밖이면 `400 INVALID_PARAMETER` (요청 전체 거절, 아무것도 저장 안 함)
- `comment`는 모든 건에 같이 저장 (선택, 최대 200자). 화면 체류 시간은 건별 선택 (6.7과 같은 규칙)
- **건마다 6.7과 같은 규칙으로 따로 처리**하고, 한 건이 실패해도 다른 건은 저장. 응답은 `200`이고 요청 순서대로 결과를 돌려줌

```json
{
  "data": {
    "batchId": "...",
    "results": [
      { "inspectionId": "...", "inspectionNo": "INS-000151", "result": "CONFIRMED",
        "finalJudgement": "FAIL", "judgedBy": "WORKER", "confirmedBy": "worker01", "confirmedAt": "..." },
      { "inspectionId": "...", "inspectionNo": "INS-000154", "result": "ALREADY_CONFIRMED",
        "finalJudgement": "FAIL", "judgedBy": "WORKER", "confirmedBy": "worker02", "confirmedAt": "..." }
    ]
  }
}
```

| `result` | 뜻 | 6.7 단건이면 |
|---|---|---|
| `CONFIRMED` | 이번 요청으로 FAIL 저장 | 200 |
| `ALREADY_CONFIRMED` | 이미 FAIL로 확정됨 (재전송 또는 다른 작업자가 먼저 FAIL). 처음 기록을 그대로 돌려줌 | 200 (같은 값 재전송) |
| `CONFLICT` | 이미 PASS로 확정됨. 덮어쓰지 않음 | `409 ALREADY_CONFIRMED` |
| `NOT_REVIEWABLE` | REVIEW 대기가 아님 (AUTO_PASS·FAILED·분석 중) | `409 NOT_REVIEWABLE` |
| `NOT_FOUND` | 없는 검사 | `404 INSPECTION_NOT_FOUND` |
| `ERROR` | 그 건 처리 중 예상 못 한 서버 오류(DB·잠금 등). 그 건만 롤백하고 나머지는 계속 처리, `errorCode = INTERNAL_SERVER_ERROR` [구현 11/23] | `500` |

- 성공 결과의 `errorCode`는 null [구현 11/23]. 실패 결과(`CONFLICT`·`NOT_REVIEWABLE`·`NOT_FOUND`·`ERROR`)는 `finalJudgement` 등 현재 값만 있으면 채우고 `errorCode`에 6.7과 같은 코드를 넣음
- 같은 검사가 다른 요청과 동시에 들어와도 판정은 1건만 저장 (6.7 규칙 그대로)
- `batchId`: 이 요청으로 저장된 판정 묶음. 일괄로 저장된 판정에는 같은 값이 남아 나중에 "일괄로 확정한 건"을 구분할 수 있음 (저장: `worker_confirmation.batch_id`, NULL이면 단건, 김남균 협의). 응답을 못 받은 재전송은 새 `batchId`가 생기지만 이미 저장된 건은 `ALREADY_CONFIRMED`라 판정이 두 번 기록되지 않음
- 권한: WORKER만 (`403 ACCESS_DENIED`). 앱은 제출 전 선택한 검사번호 목록을 보여 주고, 응답의 건별 결과를 표시

### 6.8 재검사 `POST /inspections/{id}/retry`

- FAILED 건만 가능. **새 inspectionId로 검사를 만들고 이전 FAILED 기록은 그대로 둠** [승계]
- 권한: WORKER·ADMIN 모두 허용 [확정 10/15]
- 저장된 원본을 다시 사용하므로 사진을 다시 올리지 않음. 새 검사의 `retryOf`에 원래 ID 기록 [제안]
- 응답 `202`: 새 검사의 `{ inspectionId, inspectionNo, status: "RECEIVED", retryOf }`
- 오류: `409 NOT_RETRYABLE` (FAILED가 아님), `409 ALREADY_RETRIED` (이미 재검사 **또는 수동 전환**함, 11/11 문구 "이미 재검사 또는 수동 판정으로 전환된 검사입니다.") [제안]
- 새 검사의 `capturedAt`·`lineCode`는 원래 검사 값을 이어 쓰고, Idempotency-Key는 받지 않음 [구현 10/19]
- 모델 확인은 접수와 같은 규칙: NOT_LOADABLE만 `422 MODEL_NOT_AVAILABLE`, UNKNOWN은 진행 (6.2) [구현 11/02]

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
- 자동 불량 [제안 11/23, 4.1]: 정책 형식에 `autoFailEnabled`(기본 false), `failThreshold`, `failValidatedMin`, `failValidatedMax`(모두 null 허용) 추가
  - **불량 기준 등록·조정** `POST /admin/policies/{id}/fail-threshold` `{ failThreshold, failValidatedMin, failValidatedMax }` (ADMIN): 기준치 조정과 같이 기존 정책을 고치지 않고 **새 버전**(`-f번호`, `active = false`)을 만듦. 0~1, 소수 6자리. `failValidatedMin ≤ failThreshold ≤ failValidatedMax`가 아니면 `400 POLICY_THRESHOLD_OUT_OF_RANGE`, `failThreshold ≤ passThreshold`이면 `400 INVALID_PARAMETER`
  - **켜고 끄기** `POST /admin/policies/{id}/auto-fail` `{ enabled }` (ADMIN): 역시 새 버전(`-a번호`, `active = false`)을 만들고, 관리자가 activate하면 적용. `failThreshold`가 없는 정책을 켜면 `409 AUTO_FAIL_NOT_CONFIGURED`
  - 켜기 전 김도현 새 자료 검증 결과를 `metrics`에 남김 (예: `metrics.autoFail = { sampleCount, normalAutoFailed, note }`). 서버는 값 형식만 검사하고 판단은 하지 않음
  - 기준치 조정(`/threshold`)으로 만든 새 버전도 자동 불량 값(켜짐 여부·기준·검증 범위)을 이어받음
  - 구현 세부 [구현 11/23]: `failThreshold`가 있으면 `failValidatedMin`·`failValidatedMax`도 필수(DB CHECK). `/threshold`로 새 `passThreshold`가 `failThreshold` 이상이 되면 `400 INVALID_PARAMETER`. 이미 같은 켜짐 상태여도 `/auto-fail`은 새 버전을 만듦
  - 이름 [구현 11/23]: `-t`·`-f`·`-a` 모두 `basedOnPolicyId`를 끝까지 따라가 원본 이름에 `-<접미어><번호>`를 붙이고, 번호는 접미어마다 따로 셈 (예: `p` → `p-f1` → `p-a1` → `p-t1` → `p-f2`). 어느 버전에서 왔는지는 `basedOnPolicyId`로 확인
- 위 숫자는 형식 예시일 뿐 실제 값이 아님. 실제 값과 범위는 AI 검증 후 제공 [확정]. 검증 전 시연용 정책은 `example-` 접두어 [승계]
- **threshold 조정**: `{ "passThreshold": 0.030 }`. `validatedMin ≤ 값 ≤ validatedMax`가 아니면 `400 POLICY_THRESHOLD_OUT_OF_RANGE`. 통과하면 기존 정책을 수정하지 않고 **새 버전을 만들고** `active = false`로 시작 [제안]
- **activate**: `ready = true`이고 활성 모델과 호환되는 정책만 가능, 아니면 `409 POLICY_NOT_READY` [승계]. 같은 부품·모델 버전의 다른 정책은 자동으로 비활성 (active 최대 1개) [승계]
- `ready`는 AI 검증 자료를 등록할 때 검증 기준 충족 여부로 결정. 자료 등록만으로 ready=true가 되거나 관리자가 임의로 지정하지 않음 [합의 10/15]. 실제 ready 기준 값과 허용 범위는 AI 평가 후 제공 [TBD-03]
- 정책은 `modelVersion`과 `calibratorVersion`이 모두 맞는 검사에만 적용 [합의 10/15]
- 모델 가중치·보정값 수정 API는 만들지 않음 [확정]
- `GET /admin/models`: 모델 버전, 부품, AI 서버 로드 가능 여부, 활성 여부 조회만 제공 [제안]

구현 세부 [구현 11/02]

- **`GET /admin/models`** 항목: `{ modelVersion, partCode, calibratorVersion, active, loadable }`. `loadable`은 확인 결과 true·false, 확인할 수 없거나 확인을 끈 경우 null
- **`GET /admin/policies`**: 쿼리 `partCode`, `active`. 최신 생성순, 페이지 없음. 없는 `partCode`는 `400 INVALID_PART_CODE`. 정책 형식에 `basedOnPolicyId`(조정 시 직전 정책 ID) 추가
- **`POST /admin/policies`** → `201` 정책 1건. 요청 `{ modelVersion, calibratorVersion, policyVersion, passThreshold, validatedMin, validatedMax, metrics }`
  - `passThreshold`·`validatedMin`·`validatedMax` 필수, 0~1, 소수 6자리로 반올림 저장. `validatedMin > validatedMax`나 범위 밖 값은 `400 INVALID_PARAMETER`, `passThreshold`가 검증 범위 밖이면 `400 POLICY_THRESHOLD_OUT_OF_RANGE`
  - `policyVersion` 최대 90자 (조정 접미어 공간). `metrics`는 선택, 객체만 허용
  - `404 MODEL_NOT_FOUND`, 같은 `policyVersion`은 `409 POLICY_VERSION_DUPLICATE`
  - **ready 판정 (TBD-03 임시)**: 요청 `calibratorVersion`이 있고 모델의 보정기 버전과 일치 + `metrics.sampleCount ≥ app.policy.min-sample-count`(기본 0). 표본 수가 없거나 숫자가 아니면 ready 아님. 보정기가 없는 모델(실제 DOOR 모델)에는 ready 정책이 만들어지지 않음
- **threshold** → `201` 새 정책. 모델·보정기·검증 범위·metrics·ready는 승계, `basedOnPolicyId`는 직전 정책. 이름은 **원본 정책 이름 + `-t번호`** (`example-door-p1` → `-t1`, `-t1`을 다시 조정해도 `-t2`). 동시 조정으로 이름이 겹치면 `409 POLICY_VERSION_DUPLICATE`
- **activate** → `200` 정책 1건. ready, 모델 active, 정책·모델 보정기 일치를 모두 만족해야 함. 이미 적용 중이면 그대로 200(`activatedAt` 유지). 같은 모델의 다른 정책은 자동 중지 (V5: 모델당 active 1개, 보정기 무관). 동시 요청은 순서대로 처리되어 active는 1개만 남음
- **deactivate** → `200` 정책 1건. 이미 중지 상태여도 200, `activatedAt`은 마지막 적용 시각으로 남음
- **계정 잠금 해제** `POST /admin/users/{loginId}/unlock` → `200` `{ loginId, locked: false, failedLoginCount: 0 }`. 잠기지 않은 계정도 200(실패 횟수만 초기화), 없는 계정은 `404 USER_NOT_FOUND` [구현 11/10, TBD-10]

### 6.9.1 후보 기준치 비교 `GET /admin/policies/{id}/simulation` [구현 11/18]

기준치를 바꾸기 전에, 이미 쌓인 검사 기록에 현재 기준치와 후보 기준치를 대입해 **판정이 바뀌는 건**과 그 건의 작업자 판정을 보여 줌. 정책·검사 기록은 바꾸지 않음

- 쿼리: `candidateThreshold`(필수, 0~1, 소수 6자리로 반올림), `from`·`to`(선택, `from ≤ receivedAt < to`). 기간이 없으면 전체 기간이라 기록이 많아지면 기간 지정 권장
- 대상: 정책과 **같은 모델·같은 보정기 버전**으로 분석이 완료된 검사 (보정기가 다르면 확률 눈금이 달라 비교하지 않음). 판정 당시 이 정책이 적용됐는지와는 무관. 수동 판정 건은 보정기 버전이 없어 제외
- `current`도 과거에 실제로 내려진 판정이 아니라 **현재 정책 기준치로 다시 계산한 값**. 다른 기준치로 판정된 기록이 섞여 있으면 실제 AUTO_PASS 건수와 다를 수 있음 (실제 판정은 검사 이력·CSV로 확인)
- 판정 규칙은 4장과 같음: DEFECT 예측은 기준치와 무관하게 REVIEW(`defectPredictedCount`), GOOD은 보정 확률 ≤ 기준치면 AUTO_PASS
- **라벨은 작업자 판정만**: 바뀌는 건마다 `WORKER_PASS`·`WORKER_FAIL`·`UNVERIFIED`. AUTO_PASS(PASS·SYSTEM)와 판정 전 REVIEW는 실제 라벨이 아니므로 `UNVERIFIED`
  - 기준 상향(`REVIEW_TO_AUTO_PASS`): 바뀌는 건은 지금 REVIEW라 작업자 판정이 있음 → `workerFail`이 후보에서 추가로 통과될 불량 (해당 기록에서 관측된 건수)
  - 기준 하향(`AUTO_PASS_TO_REVIEW`): 바뀌는 건은 지금 AUTO_PASS라 대부분 `UNVERIFIED`
  - 작업자 판정이 없고 AUTO_PASS 표본 재확인(6.11)이 끝난 건은 `RECHECK_PASS`·`RECHECK_FAIL` (`recheckPass`·`recheckFail`). 기준 하향에서 바뀌는 건 중 **표본으로 뽑혀 재확인된 건만**이라 건수를 그대로 전체 불량 수로 보면 안 됨 (가중 추정은 6.11 요약) [구현 11/18]
- 응답 `200`
  ```json
  { "data": {
      "policyId": "...", "policyVersion": "cowl-e08-demo-0163", "partCode": "COWL_COVER",
      "modelVersion": "...", "calibratorVersion": "...",
      "currentThreshold": 0.0163, "candidateThreshold": 0.0231,
      "validatedMin": 0.01, "validatedMax": 0.0163, "candidateWithinValidatedRange": false,
      "evaluatedCount": 40, "defectPredictedCount": 12,
      "recheckRuleVersion": "v1-b40-80-p100-30-10",
      "current":   { "autoPassCount": 5, "reviewCount": 35, "expectedRecheckCount": 3.4, "expectedCheckCount": 38.4 },
      "candidate": { "autoPassCount": 9, "reviewCount": 31, "expectedRecheckCount": 6.3, "expectedCheckCount": 37.3 },
      "change": { "direction": "REVIEW_TO_AUTO_PASS", "count": 4,
                  "workerPass": 3, "workerFail": 1, "recheckPass": 0, "recheckFail": 0, "unverified": 0,
                  "items": [ { "inspectionId": "...", "inspectionNo": "INS-000131",
                               "calibratedDefectProbability": 0.0228, "label": "WORKER_FAIL", "receivedAt": "..." } ],
                  "itemsTruncated": false } } }
  ```
- `items`: 바뀌는 건을 보정 확률 높은 순으로 최대 100건 (사진을 볼 순서). 건수는 `count`가 전체
- `expectedRecheckCount` [구현 11/18]: 그 기준치에서 AUTO_PASS가 되는 건마다 현재 `app.recheck.*` 구간 비율을 더한 **예상** 재확인 건수 (`recheckRuleVersion`, 예 `v1-b40-80-p100-30-10`). 기능이 꺼져 있어도 켰을 때 기준으로 계산. `expectedCheckCount = reviewCount + expectedRecheckCount` (REVIEW 확인과 재확인을 합친 예상 확인 건수). 두 업무의 소요 시간은 다를 수 있어 시간은 6.11 요약으로 따로 봄
- `candidateWithinValidatedRange`: AI가 검증한 범위 안인지. 범위 밖 후보도 비교는 가능하지만 적용(threshold 조정)은 6.9 규칙대로 거절
- 해석 주의: 건수는 이 기록에서 관측한 값이며 표본이 적으면 불확실성이 큼
- 오류: `404 POLICY_NOT_FOUND`, `candidateThreshold` 범위 밖·없음, `from`이 `to`보다 늦음, 또는 기준치·보정기 버전이 없는 정책은 `400 INVALID_PARAMETER`, ADMIN 외 `403 ACCESS_DENIED`

### 6.10 수동 판정 전환 `POST /inspections/{id}/manual` [구현 11/11, 합의 11/11 김도현·홍승인]

AI 결과를 받지 못한 FAILED 건을, 작업자가 원본 사진을 보고 직접 판정하도록 새 검사로 전환 (교수님 피드백 "AI 무응답 시 수동 판정", `docs/수동판정_결정안.md` B안)

흐름 (2단계, 판정 화면 재사용)
1. FAILED 상세에서 `POST /inspections/{failedId}/manual` (요청 본문 없음)
2. 응답의 새 `inspectionId` 상세로 이동 → 기존 **`POST /inspections/{newId}/confirm`** 으로 PASS/FAIL (6.7 그대로, comment 선택 200자)

- 권한: **WORKER만** (ADMIN·DEVICE `403 ACCESS_DENIED`). ADMIN은 상세·이력 조회
- 대상: `status=FAILED`이면 **실패 사유와 상관없이 모두** (`AI_SERVER_ERROR`·`AI_SERVER_TIMEOUT`·`AI_REQUEST_REJECTED`·`AI_RESPONSE_INVALID`·`INTERNAL_SERVER_ERROR`)
- **AI 상태를 확인하지 않음**: AI가 꺼져 있거나 상태를 알 수 없어도 가능. AI가 정상이어도 허용 (앱은 `/parts`의 `modelAvailable=true`면 재검사를 기본 버튼, 수동 판정을 보조 버튼으로)
- 원본 사진을 그대로 다시 씀 (재검사와 같음). 원본이 손상·다른 부품이라 판정할 수 없으면 작업자는 전환하지 않고 재촬영·재접수
- 원래 FAILED 기록은 바뀌지 않음. 원래 건 상세의 `followUp`에 새 검사가 표시되고 `error.retryable=false`
- 응답 `201`
  ```json
  { "data": { "inspectionId": "...", "inspectionNo": "INS-000120", "partCode": "FRAME",
              "source": "MANUAL", "status": "COMPLETED", "displayState": "REVIEW_PENDING",
              "reviewReason": "AI_UNAVAILABLE", "receivedAt": "...",
              "manualOf": "<원래 FAILED ID>", "manualOfInspectionNo": "INS-000110",
              "manualOfErrorCode": "AI_SERVER_ERROR" } }
  ```
- 새 검사 상세(6.5): `source=MANUAL`, `manualOf`에 원래 FAILED 번호·오류 코드, `ai=null`(AI 예측·확률 표시 안 함), `policy.reviewReason=AI_UNAVAILABLE`, `images.original`만 있음. 판정 후 `judgement`에 최종 판정·`judgedBy=WORKER`·판정자·판정 시각 → AI 실패 사유와 작업자 판정이 한 화면에 남음
- 앱 표시: `source=MANUAL` 또는 `reviewReason=AI_UNAVAILABLE`이면 "AI 분석 없이 작업자 판정"
- 모니터링: 전환한 FAILED는 실패 건수·대기열에서 빠지고, 새 검사는 판정 전까지 확인 필요 건수·대기열(`/monitoring/queue`)에 포함. 대기열 항목의 `predictedQuality`는 null
- 알림: 보내지 않음 (작업자가 직접 만든 검사)
- 오류
  | HTTP | 코드 | 상황 |
  |---|---|---|
  | 409 | `NOT_MANUAL_CONVERTIBLE` | FAILED가 아님 (분석 중·완료 건) |
  | 409 | `ALREADY_RETRIED` | 이미 재검사 또는 수동 전환함. 동시에 눌러도 1건만 생성 (재검사와 같은 원본 연결 칸, DB UNIQUE) |
  | 409 | `ORIGINAL_IMAGE_MISSING` | 원본 사진 기록이 없음 → 재촬영·재접수 |
  | 404 | `INSPECTION_NOT_FOUND` | 없는 검사 |
- 저장 (V6): `source=MANUAL`, `retry_of_inspection_id`=원래 FAILED, `model_id`=원래 FAILED의 모델(어떤 모델이 실패했는지), AI 결과·정책 칸은 모두 null
- 한계: AI가 응답은 하지만 모델이 없다고 하면(`NOT_LOADABLE`) 접수 자체가 `422`라 검사 기록이 없어 수동 판정 불가. AI가 응답하지 않으면 접수 후 FAILED가 되므로 가능

---

### 6.11 AUTO_PASS 표본 재확인 [제안·구현 11/18, TBD-16·17]

작업자 판정은 REVIEW 건에만 쌓여서 AUTO_PASS로 빠진 검사에서 무엇을 놓쳤는지 알 수 없다. `PASS · SYSTEM`은 실제 정상 라벨이 아니다. AUTO_PASS 건 일부를 정해진 규칙으로 뽑아 작업자가 다시 확인하고, 결과를 원래 시스템 판정과 **따로** 저장한다 (AI 정책 점검 11/18 4.3). 기준치·범위·보정기는 자동으로 바꾸지 않는다

공동시험 [합의 11/18 김도현·홍승인]
- 부품별 AUTO_PASS 기준치와 구간 경계(0.4·0.8)는 유지하고 **100·30·10%로 수집**. 같은 기록으로 50·30·10%였을 때도 비교 (요약 API의 `compare`)
- REVIEW와 재확인을 합친 업무량, 대기 시간, 화면 체류 시간, 발견 불량을 함께 봄. 장기 적용 비율은 시험 후 결정 (TBD-16)

표본 추출 (백엔드 자동)
- AUTO_PASS가 저장된 **뒤 별도 단계**에서 결정. 추출이 실패해도 AUTO_PASS 결과에는 영향 없음
- AUTO_PASS마다 결정을 1행 기록: 뽑힌 건 `sampled = true`, 뽑히지 않은 건도 `sampled = false`로 남김. 그래서 **미선정과 저장 실패를 구분**할 수 있음 (행이 없으면 결정 전·저장 실패·기능 꺼짐)
- 구간: `r = calibratedDefectProbability ÷ 판정 당시 passThreshold` (0 ≤ r ≤ 1). 부품마다 기준치가 달라도 같은 규칙

  | stratum | 조건 | 기본 비율 (`app.recheck.*`, TBD-16) |
  |---|---|---|
  | `NEAR` | r ≥ 0.8 | 1.0 |
  | `MID` | 0.4 ≤ r < 0.8 | 0.3 |
  | `LOW` | r < 0.4 | 0.1 |

- 낮은 점수 구간도 일부 뽑음 (기준 근처만 보면 전체 통과 건을 대표하지 못함)
- 추출 여부는 검사 ID의 SHA-256으로 정한 0~1 값(`drawValue`)이 비율보다 작은지로 결정. 같은 검사면 항상 같은 값이라 재현 가능하고, 사람이 고른 건이 섞이지 않음. 비율을 낮춘 경우(예: NEAR 50%)에 뽑혔을 건은 지금 비율에서 뽑힌 건에 항상 포함되므로 같은 기록에서 계산 가능 (높인 경우는 계산 불가)
- **추출 규칙 기록** [합의·구현 11/18 김도현]: 규칙(구간 경계 2개·비율 3개·시험 이름)은 `recheck_rule`에 1행으로 남김
  - `ruleVersion`: 값으로 자동 생성, 순서 고정 `v1-b{MID 경계%}-{NEAR 경계%}-p{NEAR%}-{MID%}-{LOW%}` (예 `v1-b40-80-p100-30-10`). 추출 해시나 경계 포함 규칙(r ≥ 경계)이 바뀌면 `v1`을 올림
  - `trialName`(선택, `app.recheck.trial-name`, 60자): 같은 설정으로 여러 번 시험할 때 회차 구분 (예 `공동시험 1차`). 버전과 시험 이름이 같으면 같은 규칙
  - **AUTO_PASS로 판정할 때 그때 규칙을 검사에 연결**(`inspection.recheck_rule_id`, 판정과 같은 트랜잭션). 기능이 꺼져 있었으면 연결 없음
  - 결정 행에는 규칙, `r`, `drawValue`, 이 구간 비율(`samplingRate`)을 남김. 집계는 규칙(버전+시험 이름)별로 따로 함. V8로 기록된 결정은 규칙이 없어 `UNRECORDED`로 묶음
- **기본 꺼 둠** (`app.recheck.enabled=false`). 꺼져 있으면 판정에 규칙을 연결하지 않고 재처리도 하지 않음
- 재처리: 결정 행이 없는 AUTO_PASS를 5분마다 다시 결정 (완료 후 1분~1일 사이 건, 1회 100건). **지금 설정이 아니라 판정 때 검사에 연결된 규칙으로 결정**하므로 실행 중 설정이 바뀌어도 처음 결정과 같음. 연결된 규칙이 없는 건은 결정하지 않고 요약에서 결정 누락으로 셈 [합의·구현 11/18 김도현]. 동시에 처리돼도 `inspection_id` UNIQUE로 1건만 남음. `app.recheck.sweep-enabled=false`면 재처리 안 함
- 문제가 보여 사람이 임의로 고른 건은 표본에 넣지 않음 (필요하면 다음 단계에서 별도 구분)

목록 `GET /rechecks`
- 쿼리: `status`(`PENDING` 기본 / `DONE`), `result`(`PASS`/`FAIL`, DONE에서만), `acknowledged`(`true`/`false`, DONE에서만), `partCode`, `page`(0부터), `size`(기본 20, 최대 100). 없는 `partCode`는 `400 INVALID_PART_CODE`, PENDING에 `result`·`acknowledged`를 주면 `400 INVALID_PARAMETER`
- 확인 안 된 FAIL만: `status=DONE&result=FAIL&acknowledged=false`
- 응답: `{ items: [ { inspectionId, inspectionNo, partCode, receivedAt, stratum, sampledAt, result, recheckedAt, acknowledgedBy, acknowledgedAt } ], page, size, totalElements, totalPages }`, 뽑힌 순서(먼저 뽑힌 건부터)
- `/monitoring/queue`(REVIEW·FAILED)와 **섞지 않음**. 작업량을 REVIEW 확인과 재확인으로 따로 세기 위함
- 권한 WORKER, ADMIN

결과 `POST /inspections/{id}/recheck`
```json
{ "result": "FAIL", "comment": "고정핀 들뜸",
  "screenDwellMs": 18250, "firstOpenedAt": "2026-11-19T10:02:11+09:00", "openCount": 2 }
```
- 권한 **WORKER만** (6.7과 같음). 대상은 표본으로 뽑힌 AUTO_PASS 건
- 화면 체류 시간 3개 필드는 6.7과 같은 규칙 (아래 "화면 체류 시간")
- 응답 `200`: `{ inspectionId, inspectionNo, finalJudgement: "PASS", judgedBy: "SYSTEM", recheck: { ... } }` (원래 판정과 재확인 결과를 함께)
- 같은 값 재전송 200(기존 결과, 체류 시간은 처음 값 유지), 다른 값 `409 ALREADY_RECHECKED`, 동시 제출 시 1건만 기록. `comment` 선택 200자, 공백은 null
- 오류: `409 NOT_RECHECKABLE`(표본이 아님: 뽑히지 않은 AUTO_PASS·REVIEW·FAILED), `404 INSPECTION_NOT_FOUND`, 체류 시간 값 오류 `400 INVALID_PARAMETER`, WORKER 외 `403 ACCESS_DENIED`
- 알림: 보내지 않음 (TBD-17)

재확인 FAIL 후속 처리 [합의 11/18 홍승인·김도현, 1차]
- 원래 판정 `PASS · SYSTEM`은 유지하고 재확인 결과는 따로 기록. 상세 화면에서 `judgement` 블록과 `recheck` 블록을 **함께** 표시
- 앱: 재확인 완료 목록에서 FAIL을 붉은색으로 구분하고, 관리자에게 추가 확인이 필요하다는 안내 표시
- 관리자 **확인함** `POST /admin/rechecks/{inspectionId}/acknowledge` (ADMIN)
  ```json
  { "note": "라인 담당자에게 전달" }
  ```
  - 재확인 결과가 **FAIL인 건만**. `note` 선택 200자, 본문 생략 가능
  - "확인함"은 관리자가 FAIL을 봤다는 기록이며 **문제 해결 완료가 아님**. 해결 여부·조치 내용 기록은 다음 단계 (TBD-17)
  - 응답 `200`: 재확인 응답과 같은 형식 (`recheck.acknowledgedBy`·`acknowledgedAt`·`acknowledgeNote` 채워짐)
  - 이미 확인함이면 200(처음 기록 그대로, 메모도 바뀌지 않음), 동시 요청 시 1건만 기록. 늦은 요청도 먼저 기록된 확인 정보(`acknowledgedBy`·`acknowledgedAt`·`acknowledgeNote`)를 담아 200 [11/18 리뷰 반영]
  - 오류: `409 NOT_ACKNOWLEDGEABLE`(표본이 아니거나 재확인 전이거나 PASS), `404 INSPECTION_NOT_FOUND`, ADMIN 외 `403 ACCESS_DENIED`
- 푸시 알림·자동 후속 조치는 없음 (TBD-17)

화면 체류 시간 [합의 11/18 홍승인·김도현]
- REVIEW 확인(6.7)과 재확인 제출에 같은 선택 필드 3개. 셋 다 보내거나 셋 다 생략 (일부만 보내면 `400 INVALID_PARAMETER`)
  - `screenDwellMs`: 상세 화면이 실제로 앞에 보이고 앱이 활성인 시간의 합 (0 ~ 86,400,000). 백그라운드·다른 화면으로 가면 멈추고, 돌아오면 이어서 셈
  - `firstOpenedAt`: 이 검사의 상세 화면을 처음 연 시각 (기기 시계, 오프셋 포함 ISO-8601)
  - `openCount`: 처음 열 때 1, 나갔다가 다시 열 때마다 +1 (1 ~ 1,000). 서버 갱신·백그라운드 복귀는 세지 않음
- 앱은 제출이 실패하면 측정값을 지우지 않고, 정상 제출된 경우에만 최종 기록됨
- 제출하지 않고 나간 경우는 기록하지 않음 → 집계는 **제출된 건만**의 체류 시간 (요약에 명시)
- 실제 작업 시간과 차이가 있을 수 있음 (화면을 띄워 둔 채 다른 일을 한 경우 등). 대기 시간은 서버 시각으로 따로 계산

요약 `GET /admin/rechecks/summary` (ADMIN) [구현 11/18]
- 쿼리: `partCode`, `from`·`to`(선택, `from ≤ receivedAt < to`), `compareNearRate`·`compareMidRate`·`compareLowRate`(선택, 셋 다 주거나 생략, 0~1)
- 대상: 기간 안의 AUTO_PASS(`PASS · SYSTEM`, 보정 확률·기준치 있음). 기간이 없으면 전체를 읽어 계산하므로 시험 기간을 지정해 조회 권장 (6.9.1과 같음)
- 판정 때 규칙 기록이 실패하면(DB 오류) AUTO_PASS는 그대로 두고 규칙 없이 남김 → `undecidedWithoutRuleCount`에 셈
- 응답 `200`
  ```json
  { "data": {
      "partCode": null, "from": null, "to": null,
      "autoPassCount": 120, "decidedCount": 116, "undecidedCount": 4, "undecidedWithoutRuleCount": 1,
      "rules": [ {
        "ruleVersion": "v1-b40-80-p100-30-10", "trialName": "공동시험 1차",
        "partCode": "DOOR", "policyVersion": "door-e02-demo-0092",
        "modelVersion": "door-swin-tiny-e02-28a2dd1cb40b-dev", "calibratorVersion": "door-e02-temperature-30962f5cac45-demo",
        "nearRatio": 0.8, "midRatio": 0.4, "nearRate": 1.0, "midRate": 0.3, "lowRate": 0.1,
        "autoPassCount": 119, "decidedCount": 116, "undecidedCount": 3,
        "sampledCount": 40, "pendingCount": 6, "passCount": 32, "failCount": 2,
        "completionRate": 0.85, "partial": true,
        "strata": [ { "stratum": "NEAR", "autoPassCount": 21, "decidedCount": 20, "undecidedCount": 1,
                      "sampledCount": 20, "completedCount": 18, "pendingCount": 2, "completionRate": 0.9,
                      "passCount": 17, "failCount": 1, "failRateAmongCompleted": 0.0556 } ],
        "estimatedDefectRateInAutoPass": 0.021,
        "compare": { "nearRate": 0.5, "midRate": 0.3, "lowRate": 0.1, "computable": true,
                     "sampledCount": 30, "unverifiedCount": 4, "passCount": 25, "failCount": 1,
                     "partial": true, "estimatedDefectRateInAutoPass": 0.018 } } ],
      "waits": { "review": { "count": 35, "pendingCount": 4, "averageMs": 41000, "medianMs": 26000 },
                 "recheck": { "count": 34, "pendingCount": 6, "averageMs": 380000, "medianMs": 120000 } },
      "dwell": { "review": { "count": 30, "averageMs": 15000, "medianMs": 11000, "averageOpenCount": 1.2 },
                 "recheck": { "count": 28, "averageMs": 9000, "medianMs": 7000, "averageOpenCount": 1.1 } } } }
  ```
- **`rules[]` 한 항목 = 추출 규칙 + 부품·정책·모델·보정기 버전이 모두 같은 AUTO_PASS** [11/18 리뷰 반영]. 같은 규칙이어도 조회 기간 중 정책(기준치)·모델·보정기가 바뀌면 항목을 나눠 불량률을 따로 계산하고 합치지 않음. 화면도 항목마다 따로 표시
- 항목별·구간별로 `autoPassCount`(그 조합으로 판정된 AUTO_PASS) = `decidedCount` + `undecidedCount`(결정 누락). 결정 누락 건도 판정 당시 규칙으로 구간을 정해 그 구간에 셈
- `undecidedWithoutRuleCount`: 판정 당시 규칙도 결정도 없는 AUTO_PASS (기능 꺼짐 등). 어느 규칙에도 넣지 않음
- **대기(`pendingCount`)는 정상·불량 어느 쪽으로도 세지 않음**. `failRateAmongCompleted = fail ÷ (pass + fail)`, 완료 건이 없으면 null
- `estimatedDefectRateInAutoPass` [합의 11/18 김도현]: 구간별 `failRateAmongCompleted`에 **구간 AUTO_PASS 건수 ÷ 전체 AUTO_PASS 건수**를 곱해 합산 (추출 비율 100·30·10%는 뽑는 비율이고 가중치가 아님). AUTO_PASS가 0건인 구간은 빼고, AUTO_PASS가 있는데 완료가 0건인 구간이 있으면 null
- `completionRate` [합의 11/18 김도현]: `completedCount ÷ sampledCount` (구간별·규칙 전체). 뽑힌 건이 없으면 null
- `partial` [합의 11/18 김도현, 기준 확인 11/18]: 선정된 검사 중 재확인 대기(`pendingCount` > 0)가 1건 이상이거나 추출 결정 누락(`undecidedCount` > 0)이 1건 이상이면 true. 목록이 뽑힌 순서라 먼저 뽑힌 건만 완료된 상태일 수 있어 추정이 치우칠 수 있음. 가상 비교의 `partial`은 미확인(`unverifiedCount` > 0)이나 결정 누락이 남으면 true (계산 불가면 null)
- **화면 표시** [합의 11/18 김도현]
  - `estimatedDefectRateInAutoPass`는 **"AUTO_PASS 추정 불량률"**로 표시 (전체 불량률·정책 누락률이 아님)
  - 구간(NEAR·MID·LOW)마다 **"완료 {completedCount}/{sampledCount}건 ({completionRate})"**를 함께 표시. 선정 0건이면 `completionRate`가 null이므로 **"완료 0/0건 (—)"**
  - AUTO_PASS가 있었지만 재확인 완료가 0건인 구간은 `failRateAmongCompleted`가 null → 그 구간 추정값은 빈칸 (전체 추정도 null)
  - `partial: true`면 **"일부만 완료되어 결과가 치우칠 수 있습니다"** 안내. 추정값이 null이면 "완료된 재확인이 없는 구간이 있어 추정하지 않음"
  - 가상 비교는 "가상 비교 (50·30·10%)"처럼 비율과 함께 표시하고 실제 수집 결과와 섞지 않음
- `compare` (**가상 비교**, 화면에도 가상 비교로 표시): 같은 기록에서 `drawValue < 비교 비율`인 건만 다시 셈. 그중 실제 재확인 결과가 있는 건만 `passCount`·`failCount`, 결과가 없는 건은 `unverifiedCount`. 비교 비율이 실제 비율보다 큰 구간이 있거나 `UNRECORDED`면 `computable: false`, 숫자는 null
- `waits.review`: 기간 안의 REVIEW 건 `completedAt → 작업자 confirmedAt`, `waits.recheck`: `sampledAt → recheckedAt`. 둘 다 **완료된 건만** 평균·중앙값을 내고, 아직 대기 중인 건은 `pendingCount`로 따로 셈
- `dwell`: 화면 체류 시간을 보낸 제출 건만 (미제출 이탈은 기록 없음)
- 오류: 없는 `partCode` `400 INVALID_PART_CODE`, `from`이 `to`보다 늦음·비교 비율 일부만·범위 밖 `400 INVALID_PARAMETER`, ADMIN 외 `403 ACCESS_DENIED`

해석
- 재확인으로 직접 추정하는 것은 **AUTO_PASS 중 실제 불량 비율**(통과된 검사에 불량이 얼마나 섞였는지)
- **전체 실제 불량 중 AUTO_PASS로 빠진 비율**(정책의 불량 누락)은 REVIEW 작업자 판정까지 합쳐야 하므로 별도 (다음 단계)
- 정책·모델·보정기 버전이나 추출 규칙이 다른 검사는 합치지 않음. 요약은 이 조합별로 `rules[]` 항목을 나눔 (부품도 정책에 따라 갈림)
- 건수가 적으면 불확실성이 큼. 신뢰구간 표시 방법은 TBD-16

### 6.12 판정 확인 요청·정정 [제안 11/23, 김도현 시안]

시스템이 판정한 건(`judgedBy = SYSTEM`, 지금은 AUTO_PASS)을 작업자가 실물·추가 사진으로 다르게 확인했을 때 근거를 남기고, 관리자가 **유지** 또는 **정정**함. 최초 판정과 정책 실적은 바꾸지 않고 정정은 별도 기록으로 남김

- 대상: `judgedBy = SYSTEM`인 검사만. 없는 검사는 `404 INSPECTION_NOT_FOUND`. 작업자 판정(REVIEW·수동 판정) 건은 `409 NOT_REQUESTABLE`. 자동 불량(TBD-18)을 도입하면 같은 흐름을 씀
- 표본 재확인(6.11)과는 별도 기록. 재확인 FAIL이 나온 건도 정정이 필요하면 이 요청을 따로 올림. 집계는 같은 검사를 두 번 세지 않도록 TBD-19에서 정함

**요청** `POST /inspections/{id}/judgement-requests` (WORKER)

```json
{ "claimedJudgement": "FAIL", "area": "고정핀", "reason": "실물 확인 결과 고정핀이 접촉면에서 들떠 있음" }
```

- `claimedJudgement`: `PASS`·`FAIL` 중 **현재 판정(정정됐으면 정정 판정)과 다른 값**. 같으면 `400 INVALID_PARAMETER`
- `reason` 필수 1~500자, `area` 선택 최대 100자. 근거 사진 첨부는 다음 단계 (TBD-19)
- 응답 `201`: 요청 1건
- 검사 순서: 판정 값(400) → 대기 요청(409) [구현 11/23]. 검사당 **처리 대기 요청은 1건**. 대기 중에 같은 작업자가 같은 `claimedJudgement`로 다시 보내면 기존 요청 `200`, 그 밖에는 `409 REQUEST_ALREADY_OPEN`. 처리된 뒤에는 새 요청 가능

요청 1건 형식

```json
{
  "requestId": "...",
  "inspectionId": "...",
  "inspectionNo": "INS-000143",
  "partCode": "FRAME",
  "originalJudgement": "PASS",
  "originalJudgedBy": "SYSTEM",
  "currentJudgement": "PASS",
  "claimedJudgement": "FAIL",
  "area": "헤밍부",
  "reason": "...",
  "requestedBy": "worker01",
  "requestedAt": "...",
  "status": "OPEN",
  "resolvedBy": null,
  "resolvedAt": null,
  "resolveNote": null
}
```

- `originalJudgement`·`originalJudgedBy`: 검사의 최초 판정 (`judgement` 블록 값, `originalJudgedBy`는 저장하지 않고 검사에서 읽음). `currentJudgement`: 요청 당시 현재 판정(앞선 정정이 있으면 그 값)
- `status`: `OPEN`(대기) · `KEPT`(현재 판정 유지) · `CORRECTED`(정정)

**목록** `GET /admin/judgement-requests` (ADMIN)
- 쿼리: `status=OPEN|RESOLVED|ALL` (기본 `OPEN`), `partCode`, `page`, `size`(기본 20, 최대 100). `RESOLVED` = `KEPT`+`CORRECTED`
- 정렬: `OPEN`은 오래된 요청부터, 그 밖에는 최근 처리·요청부터

**처리** `POST /admin/judgement-requests/{requestId}/resolve` (ADMIN)

```json
{ "decision": "CORRECT", "note": "실물 사진 확인, 고정핀 들뜸 맞음" }
```

- `decision`: `KEEP`(유지) · `CORRECT`(요청한 판정으로 정정). `note` 필수 1~500자
- 응답 `200`: `{ request: 요청 1건, correction: 검사의 correction(6.5) 또는 null }` [구현 11/23]
- 이미 처리된 요청에 같은 `decision`이면 처음 기록 그대로 `200`, 다른 `decision`이면 `409 REQUEST_ALREADY_RESOLVED`. 동시 처리는 1건만 저장
- 정정해도 `inspection.final_judgement`·`judged_by`(최초 판정)는 바꾸지 않음. AUTO_PASS는 `PASS·SYSTEM`이라는 V5 CHECK와, 정책 실적을 최초 경로로 세는 규칙을 지키기 위함. 현재 판정 = 마지막 `CORRECTED` 요청의 판정, 없으면 최초 판정

저장 [제안, 김남균 협의] `judgement_request`: id, inspection_id(FK), requested_by(FK users), requested_at, original_judgement, current_judgement, claimed_judgement, area, reason, status, resolved_by(FK users), resolved_at, resolve_note
- CHECK 후보: `claimed_judgement <> current_judgement`, 상태별 처리자·시각·메모 짝 (`OPEN`이면 셋 다 NULL, 아니면 셋 다 있음). NULL 비교는 `IS NOT NULL`을 함께 검사
- 검사당 대기 1건: `open_key = IF(status = 'OPEN', inspection_id, NULL)` 생성 컬럼 UNIQUE (V9 `trial_key`와 같은 방식)
- 테이블 간 규칙(대상이 `judged_by = SYSTEM`, 요청자 WORKER, 처리자 ADMIN)은 점검 SQL로 확인
- 일괄 FAIL 묶음: `worker_confirmation.batch_id` CHAR(36) NULL (6.7.1)

### 6.13 관리자 날짜별 이력·기준 상세 [제안 11/23, 합의 11/23 김도현 범위 변경, TBD-18]

**날짜별 이력** `GET /admin/automation/daily?partCode=COWL_COVER&from=2026-11-20&to=2026-11-24` (ADMIN)
- `partCode` 필수, `from`·`to`는 KST 날짜(`from ≤ 날짜 < to`), 최대 92일. 응답은 최신 날짜부터
- **날짜는 KST(Asia/Seoul) 고정**: 검사 `receivedAt`의 KST 날짜. 서버·DB 시간대와 무관. 수동 전환 검사는 새 REVIEW 검사가 생긴 날짜 [합의 11/23 김도현]
- 한 날짜 안에서 판정 당시 정책·모델·보정기 조합별로 행을 나눔(NULL도 한 값). 정책이 없어 REVIEW가 된 건과 수동 전환·FAILED 건은 정책 없는 행이며, 같은 날짜·모델·보정기면 한 행에 함께 들어감. 같은 날짜 안은 정책 버전·모델·보정기 순, 정책 없는 행이 마지막. 정책 없는 행의 `autoFailEnabled`는 false. 분석 중(RECEIVED·ANALYZING)은 세지 않음 [구현 11/23]

```json
{
  "data": [
    {
      "date": "2026-11-24",
      "policyId": "...", "policyVersion": "cowl-e08-demo-0163-f1-a1",
      "modelVersion": "...", "calibratorVersion": "...",
      "passThreshold": 0.0163, "failThreshold": 0.9966, "autoFailEnabled": true,
      "total": 8, "autoPass": 2, "autoFail": 2,
      "review": { "done": 0, "total": 4 },
      "manual": { "done": 0, "total": 0 },
      "failed": 0,
      "confirmedOpposite": { "autoPassThenFail": 0, "autoFailThenPass": 0, "resolvedRequests": 0 },
      "openRequests": 0
    }
  ]
}
```

- `total = autoPass + autoFail + review.total`. **`review`에는 수동 전환이 포함**되고 `manual`은 그중 수동 전환만 (REVIEW의 세부 건수). 화면은 "REVIEW 3/4 · 수동 전환 1/1"처럼 함께 표시 [합의 11/23 김도현·홍승인]
- AI의 REVIEW 비율은 수동 전환과 FAILED를 빼고 계산: `(review.total − manual.total) ÷ (total − manual.total)` (FAILED는 원래 total에 없음)
- `done`: 그 배정 건 중 **조회 시점까지** 작업자 판정이 끝난 수. 다음 날 판정해도 원래 날짜 행에 반영
- `failed`: 분석 실패(FAILED) 건수. `total`에 넣지 않는 장애 기록
- `confirmedOpposite`: 판정 확인 요청(6.12) 중 처리된 것만. `autoPassThenFail`·`autoFailThenPass`는 `CORRECTED` 건을 검사 ID당 1건으로 셈, `resolvedRequests`는 처리된 요청이 있는 검사 수(`KEPT` 포함). `resolvedRequests = 0`이면 앱은 "확인 자료 없음", 0보다 크면 "확인 n건 중 m건" [TBD-19]. 대기 요청은 `openRequests`로 따로
- 표본 재확인(6.11) 결과는 넣지 않음. 재확인 요약에서 따로 봄

**기준 상세** `GET /admin/automation/daily/detail?partCode&date&policyId&band=0.05` (ADMIN)
- 날짜 행 하나(같은 날짜·정책)의 기준 주변 REVIEW를 두 구간으로 나눔. `band`(기본 0.05, 0.001~0.5)는 기준에서 떨어진 정도(확률 차)
  - 통과 기준 위: GOOD 예측 REVIEW 중 `passThreshold < 확률 ≤ passThreshold + band`
  - 불량 기준 아래: DEFECT 예측 REVIEW 중 `failThreshold − band ≤ 확률 < failThreshold`. 정책에 `failThreshold`가 없으면 이 구간은 null
- 응답 `{ date, partCode, policyId, policyVersion, modelVersion, calibratorVersion, passThreshold, failThreshold, autoFailEnabled, band, passBand, failBand, reference }` [구현 11/23]
- 구간마다 `{ from, to, total, pass, fail, pending, items: [{ inspectionId, inspectionNo, calibratedDefectProbability, finalJudgement, correctedJudgement }] }`. `pass + fail + pending = total`. items는 확률 오름차순, 구간 경계는 소수 오차 없이 계산
- 기준 라벨·실물 확인 결과는 서버에 저장하는 곳이 없어 `reference: null`("자료 없음") [TBD-20]
- 같은 날짜 행과 같은 정책 조건만 씀 (다른 버전 점수가 섞이지 않음)

오류: 없는 `partCode` `400 INVALID_PART_CODE`, 날짜 형식·범위·`band` 오류 `400 INVALID_PARAMETER`, 없는 `policyId`·다른 부품의 정책 `404 POLICY_NOT_FOUND`

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

`inspectionItemCode`는 유지. 세 부품 모두 `UNIFIED` (TBD-04, 11/17 V7)

### 7.2 정상 응답

실제 DOOR 모델 버전 [11/03 갱신]: 재학습 2회차 `door-swin-tiny-e02-28a2dd1cb40b-dev` (이전 10/28 `door-swin-tiny-e20-8d042c7bfab2`. 보정기 미준비 → `calibratedDefectProbability`·`calibratorVersion` null, 정책 없음 → 분석 성공 건은 REVIEW). 개발 중 기본 활성 모델은 Mock `mock-door-swin-t-v1`

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
| `gradcam` | N | **DEFECT 예측 건만 생성**. GOOD 예측이거나 생성 오류면 null [합의 10/15]. 형식은 아래 표 [합의 10/28] |
| `inferenceTimeMs` | Y | AI handler 진입부터 응답 JSON 직렬화 직전까지의 정수 ms (이미지 읽기·전처리·추론·Grad-CAM 생성 포함, 모델 최초 로드·직렬화·전송 제외) [합의 10/28, AI 확인] |

`gradcam` 객체 [합의 10/28]

| 필드 | 값 | 규칙 |
|---|---|---|
| `targetClass` | `DEFECT` | 항상 DEFECT |
| `status` | `GENERATED` / `NO_ACTIVATION` | 10/28 추가. 없으면 이미지 유무로 판단(이전 형식 호환) |
| `mapType` | `ZERO_MAP` / `CONSTANT_MAP` | `NO_ACTIVATION`일 때만. 백엔드는 `ai_response_json`에만 보관 |
| `format` | `png` / `jpeg` | 대소문자 무시, `jpg`도 jpeg로 인정. 실제 이미지 형식과 같아야 함. `NO_ACTIVATION`이면 null |
| `imageBase64` | base64 문자열 | 원본(방향 보정 후)과 같은 크기의 표시용 이미지. `NO_ACTIVATION`이면 null |

```json
// 정상 생성
"gradcam": { "targetClass": "DEFECT", "status": "GENERATED", "format": "png", "imageBase64": "..." }
// 0맵·상수맵
"gradcam": { "targetClass": "DEFECT", "status": "NO_ACTIVATION", "mapType": "ZERO_MAP", "format": null, "imageBase64": null }
// 생성 오류
"gradcam": null
```

백엔드 처리 (DEFECT 예측일 때) [합의 10/28]

| AI 응답 | `gradcamStatus` | 이미지 저장 |
|---|---|---|
| `gradcam` null | `FAILED` | 없음 |
| `status: NO_ACTIVATION` | `NO_ACTIVATION` | 없음 |
| `status: GENERATED`(또는 없음) + 유효한 png·jpeg | `GENERATED` | 저장 (`image/png`·`image/jpeg`) |
| 그 외 (알 수 없는 status, targetClass ≠ DEFECT, 지원하지 않는 format, 디코딩 실패, 선언과 실제 형식 불일치) | `FAILED` | 없음 |

- 어느 경우도 검사를 FAILED로 만들지 않음. 분류 결과·REVIEW는 그대로 [합의 10/15 승계]
- 응답이 큼: 실제 DEFECT 샘플 15.5MB(base64 약 1,546만 자). 백엔드는 AI 응답 파싱의 문자열 한도를 5,000만 자로 설정 (`app.ai.max-response-string-chars`, Jackson 기본 2,000만 자) [합의 10/28]

- Grad-CAM 전달: 응답 안에 base64로 포함 [합의 10/15], 형식은 PNG 또는 JPEG [합의 10/28]. 용량 문제가 생기면 multipart로 변경
- GOOD 예측이면 응답과 관계없이 `gradcamStatus = NOT_REQUIRED`. DEFECT 예측이면 위 표대로 정함. 어느 쪽도 검사를 FAILED로 만들지 않음 [합의 10/15·10/28]
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
- 실제 AI 확인 [11/04, 김도현·이승규]: 503 `INFERENCE_FAILED` → 재시도 1회 후 `AI_SERVER_ERROR`, 422 `IMAGE_ORIGIN_NOT_ALLOWED` → `AI_REQUEST_REJECTED`(재시도 없음), 타임아웃 → `AI_SERVER_TIMEOUT` 후 상태 불변, AI 중지 → `AI_SERVER_ERROR`·modelAvailable=false, 복구 후 재검사 COMPLETED. 409 `MODEL_VERSION_MISMATCH`는 AI 단독으로 확인 (통합 점검표 B7~B10, E2)
- AI는 허용된 출처의 이미지 주소만 내려받음. 백엔드 `PUBLIC_BASE_URL`은 AI 쪽에 등록된 주소(현재 Mac Tailscale 주소의 8080)와 같아야 하며, 다르면 422 `IMAGE_ORIGIN_NOT_ALLOWED`

### 7.4 로드 가능 모델 `GET {AI}/internal/v1/models` [확인 11/04]

실제 AI 서버도 Mock과 같은 형식으로 응답함을 확인 (11/04, e02 `loadable=true`, `calibratorVersion=null`). 해석 코드 `AiModelListParser`는 수정 없음. 판단 규칙은 6.2

```json
{ "data": [ { "modelVersion": "...", "partCode": "DOOR", "calibratorVersion": null, "loadable": true } ] }
```

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
| `AUTO_FAILED` [제안 11/23 김도현] | COMPLETED + AUTO_FAIL | 등록된 WORKER·ADMIN 기기 전체. 제목 "자동 불량"으로 REVIEW 알림과 구분, 누르면 검사 상세(`inspectionId`)로 이동. 재판정은 요구하지 않고 오판이 의심될 때만 판정 확인 요청(6.12). 분석 결과 저장 때 검사당 한 번만 발송되어 중복 없음. 설비 연동·즉시 제거는 범위 밖 |

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
- `type`: `REVIEW_REQUIRED` · `ANALYSIS_FAILED` · `AUTO_FAILED`(제목 "자동 불량", 본문 "<부품> <검사번호> 자동 불량으로 판정됐습니다.") [제안 11/23]. 앱은 `type`으로 REVIEW 알림과 구분해 표시
- 기기 토큰 등록: 로그인 직후 `POST /notifications/devices` `{ "token": "ExponentPushToken[...]", "platform": "ANDROID" | "IOS" }`
- 알림 기록 테이블은 두지 않음. 확인 필요 목록은 검사 기록에서 조회 [제안, DB 주간보고의 조건부 Notification 테이블은 미생성]

### 8.4 구현 세부 [구현 11/02]

- **등록** `POST /notifications/devices` → `204`. 토큰은 `ExponentPushToken[...]` 또는 `ExpoPushToken[...]`, 아니면 `400 INVALID_DEVICE_TOKEN`. 같은 토큰이 있으면 사용자·플랫폼·최근 확인 시각을 갱신 (행 1개)
- **해제** `DELETE /notifications/devices/{token}` → `204`. 본인 토큰만 지워지고, 없거나 다른 사람 토큰이면 아무 일도 하지 않고 204
  - **토큰의 `[ ]`는 경로에서 인코딩 필수**. 그대로 보내면 Tomcat이 400으로 거절함 (확인 11/02). 앱은 `encodeURIComponent(token)` 사용
- **로그아웃** `POST /auth/logout`에 선택 필드 `deviceToken`을 보내면 같은 규칙으로 해제
- **발송**: 결과 저장 커밋 후 전용 스레드에서 Expo Push API로 100개씩 발송. 실패는 로그만 남기고 분석 결과에 영향 없음, 재시도 없음. 제목 `확인 필요`·`분석 실패`, 본문 `DOOR INS-000006 작업자 확인이 필요합니다.` 형식
- **설정**: `app.push.enabled` 기본 false면 로그만 남김
- **만료 토큰**: 발송 응답 티켓의 `DeviceNotRegistered`만 삭제. **receipt 조회는 미구현**이므로 Apple·Google이 나중에 알려 주는 만료는 삭제되지 않음. 실제 기기 수신은 미확인

- **실서버 앱 시험** [확인 11/05, 홍승인·이승규]: 로그인, Access Token 만료 후 refresh(이전 리프레시 토큰 폐기), 모니터링 부품별 요약·확인 필요 목록 순서 확인. 기기 토큰 등록·푸시 수신은 앱에 등록 기능이 없어 미확인 (통합 점검표 A12~A14)
---

## 9. 저장 구조 변경안 (김남균 협의)

현재 백엔드 코드의 V1 스키마와 개정본3 8.1 속성 기준 변경. V1은 수정하지 않고 Flyway `V3__monitoring_gradcam.sql`로 반영. 김남균 DB 설계 v2(`01_schema.sql`)와 맞춰 작성 [제안]

김남균 동의 사항 [합의 10/15]: `inspection_no` 추가, 원본·Grad-CAM 구분 저장, `judged_by`와 최종 판정 일관성, 재검사 연결, 정책 조정 시 새 버전·기존 기준치 보존, `storage_uri`에 상대 키 저장, 과거 결과 재계산 제외

| 테이블 | 변경 |
|---|---|
| `part` | 그대로. 라인 마스터 테이블은 만들지 않음, partCode가 모니터링 단위 [제안] |
| `inspection_item` | 유지. 모델이 정상·불량 전체를 분류하므로 항목 코드는 세 부품 모두 `UNIFIED` (TBD-04 확정 11/17, V7) |
| `inspection` | `inspection_no`(UNIQUE, NOT NULL, 표시용 번호 `INS-000006`) 추가 · `user_id` → nullable, `source`(DEVICE/ADMIN) 추가 · `status`에 RECEIVED 추가 · `review_reason`, `judged_by`, `pass_threshold_applied`(스냅숏), `gradcam_status`(GENERATED·NOT_REQUIRED·FAILED·NO_ACTIVATION [합의 10/28]), `calibrator_version`, `received_at`, `retry_of_inspection_id` 추가 · **`line_code`(nullable), `captured_at` 추가 (9.1)** · 개정본3 속성 중 V1에 없는 `client_request_id`, `ai_response_json`, `error_detail`, `trace_id` 추가 [승계] · `patch_inspection_supported`는 신규 기록에서 미사용 |
| `image_storage` | `storage_uri`는 저장소 상대 키 [합의 10/15] · `image_type`(ORIGINAL/GRADCAM) 추가, `inspection_id` UNIQUE → (`inspection_id`, `image_type`) UNIQUE · `exif_orientation` 추가 [승계, V1에 없음] |
| `automation_policy` | `target_miss_rate` → nullable (과거 기록 보존), `validated_min`·`validated_max`·`calibrator_version`·`activated_at` 추가. `metrics_json`은 AI 평가 근거로 계속 사용 [승계]. 조정 시 행 수정 대신 새 행 |
| `defect_detection` | 신규 기록 중단, 테이블은 유지 (과거 기록 보존) [확정] |
| `ai_model` | `patch_inspection_supported` 신규 미사용. `calibrator_version` 추가 |
| `worker_confirmation` | `comment` 추가. 그 외 그대로 |
| `recalculation_run`·`recalculation_result` | 제외 [합의 10/15, TBD-15 해소] |
| **신규** `device_token` | id, user_id, token(UNIQUE), platform, created_at, last_seen_at |
| **신규** `auto_pass_recheck` (V8) [제안 11/18] | AUTO_PASS마다 추출 결정 1행. id, inspection_id(UNIQUE), sampled(뽑힘 여부), stratum(NEAR/MID/LOW), sampling_rate(0 ≤ rate ≤ 1, 뽑힌 건은 0 초과), sampled_at(결정 시각), result(PASS/FAIL, null), comment, rechecked_by, rechecked_at. CHECK: 뽑히지 않은 건은 result 없음, 결과·확인자·확인 시각은 셋 다 있거나 셋 다 없음. 테이블 간 규칙(대상이 AUTO_PASS·SYSTEM, 재확인이 있어도 `inspection.final_judgement`는 PASS)은 점검 SQL로 확인 (김남균 협의) |
| **신규** `recheck_rule` (V9) [구현 11/18] | 추출 규칙 1건 = 1행. id, rule_version, trial_name(선택), near_ratio·mid_ratio·near_rate·mid_rate·low_rate, created_at. (rule_version, 시험 이름) UNIQUE (NULL은 빈 문자열로 묶는 생성 컬럼 trial_key) |
| `inspection` 추가 (V9) [구현 11/18] | recheck_rule_id(FK, NULL 허용): AUTO_PASS 판정 당시 규칙. AUTO_PASS일 때만 값 (CHECK). 재처리가 이 규칙을 씀 |
| `auto_pass_recheck` 추가 (V9) [구현 11/18] | 결정 규칙: rule_id(FK), ratio(r), draw_value (V8 행은 NULL, 셋은 함께 있거나 함께 없음) · 확인함: acknowledged_by(FK users), acknowledged_at, acknowledge_note (재확인 FAIL에만, 확인자·시각 짝) · 화면 체류 시간: screen_dwell_ms, first_opened_at, open_count (셋 다 있거나 없음, 재확인 결과가 있을 때만) |
| `worker_confirmation` 추가 (V9) [구현 11/18] | screen_dwell_ms, first_opened_at, open_count (선택, 셋 다 있거나 없음) |

적용 현황 [합의 10/28]
- Flyway V1~V5 적용. V3 인증, V4 모니터링·비동기·Grad-CAM·정책 버전(위 표), **V5 무결성 제약**(김남균 작성, 이승규 수정: `gradcam_status`에 `NO_ACTIVATION` 추가, FAILED면 `predicted_quality` NULL)
- V5 내용: 복합 FK 2(검사 부품–검사항목, 정책 모델–검사항목), 검사항목당 active 모델 1개·모델당 active 정책 1개(생성 컬럼 UNIQUE), 허용값·확률 범위 CHECK, 상태별 값 규칙(RECEIVED·ANALYZING·COMPLETED·FAILED), AUTO_PASS 조건 강화(GOOD 예측·정책·보정 확률 ≤ 기준치), REVIEW 사유와 값 일관성, Grad-CAM 상태(GOOD → NOT_REQUIRED, DEFECT → GENERATED·FAILED·NO_ACTIVATION), 보정 확률·보정기 버전 짝, 정책 ready 시 기준치·검증 범위·보정기 필수
- CHECK로 막을 수 없는 테이블 간 규칙 12개는 점검 SQL(`V5_integrity_checks.sql`)로 확인
- 개발 시드 V5_1: 실제 DOOR 모델 `door-swin-tiny-e20-8d042c7bfab2`를 비활성으로 등록 (Mock 모델과 동시 active 불가)
- 개발 시드 V5_2 [11/03]: 재학습 2회차 `door-swin-tiny-e02-28a2dd1cb40b-dev`를 비활성으로 등록. checksum은 가중치 전체 sha256
- 이미 적용된 마이그레이션은 수정하지 않고 다음 버전으로 추가

제약·인덱스
- 복합 FK 유지: 검사의 부품–검사항목, 정책의 모델–검사항목 일치를 DB에서 보장 [승계]
- `(user_id, client_request_id)` UNIQUE, null 허용 [승계]
- 상태 조합 CHECK: AUTO_PASS면 final_judgement=PASS·judged_by=SYSTEM, FAILED면 recommended_action·final_judgement null 등. NULL 비교가 통과되지 않도록 `IS NOT NULL`을 함께 검사 [김남균 DB 설계 반영]
- `final_judgement`와 `worker_confirmation`은 한 트랜잭션으로 저장 [합의 10/15]
- `inspection (part_id, received_at)`: 부품별 최근 목록 [제안]
- `inspection (status, recommended_action, final_judgement, received_at)`: 확인 필요 목록 [제안]
- `inspection (line_code, received_at)`: 라인별 통계를 실제로 만들 때 추가 (지금은 만들지 않음)

### 9.1 향후 통계 대비

통계 화면·API는 이번 필수 범위에서 제외 [확정]. 앱의 통계 화면은 로컬 Mock 시연용이며 서버 통계 API는 만들지 않음 [제안 11/10, 팀 확인] 대신 나중에 추가할 때 과거 기록부터 바로 집계할 수 있도록 **필요한 값은 지금부터 저장**해 둡니다. 통계 전용 컬럼은 따로 만들지 않고, 아래처럼 기존 기록에서 계산합니다.

| 향후 통계 | 계산 근거 (저장 필드) | 비고 |
|---|---|---|
| 확정 불량률 FAIL/(PASS+FAIL) | `final_judgement` | REVIEW 대기·FAILED는 분모에서 제외 [승계] |
| AUTO_PASS·REVIEW 비율, FAILED 건수 | `status`, `recommended_action` | 분석 성공 건을 분모로 [승계] |
| REVIEW 사유별 건수 | `review_reason` | 정책 미적용으로 REVIEW가 된 비율 확인용 |
| AI 예측과 작업자 판정 일치율 | `predicted_quality` + `worker_confirmation.final_judgement` | **REVIEW 건 기준 일치율**. AUTO_PASS는 작업자 확인이 없어 제외되므로 모델 전체 정확도로 표현하지 않음 |
| 라인별 불량 빈도 | `line_code` | 값이 들어오기 시작한 시점 이후만 집계 가능 |
| 시간대·기간별 추이 | `captured_at`, `received_at` | |
| 정책 버전별 자동화율 | `policy_id`, `pass_threshold_applied` | 기준 변경 전후 비교 |
| 작업자 확인 대기 시간 | `completed_at` → `confirmed_at` | 6.11 요약 `waits.review` |
| 화면 체류 시간 | `screen_dwell_ms`·`open_count` (V9) | 제출된 건만 [11/18] |

- 불량 **유형별** 통계는 불가: 현재 AI가 정상·불량 2분류만 반환하므로 유형 정보가 없음

---

## 10. 오류 코드

개정본3 5.7 오류 코드표 유지 [승계] + 아래 변경

| 구분 | HTTP | 코드 | 상황 |
|---|---|---|---|
| 추가 | 400 | `POLICY_THRESHOLD_OUT_OF_RANGE` | 검증 범위 밖 passThreshold |
| 추가 | 404 | `POLICY_NOT_FOUND` | 정책 없음 |
| 추가 | 404 | `MODEL_NOT_FOUND` | 정책 등록 시 모델 버전 없음 [구현 11/02] |
| 추가 | 404 | `USER_NOT_FOUND` | 잠금 해제 대상 계정 없음 [구현 11/10] |
| 추가 | 409 | `POLICY_VERSION_DUPLICATE` | 같은 policyVersion이 이미 있음 [구현 11/02] |
| 추가 | 404 | `IMAGE_NOT_AVAILABLE` | Grad-CAM 없음·이미지 유실 |
| 추가 | 409 | `NOT_RETRYABLE` | FAILED가 아닌 건 재검사 |
| 추가 | 409 | `ALREADY_RETRIED` | 이미 재검사 또는 수동 전환한 FAILED 건 (11/11 문구 변경) |
| 추가 | 409 | `NOT_MANUAL_CONVERTIBLE` | FAILED가 아닌 건 수동 전환 [구현 11/11] |
| 추가 | 409 | `ORIGINAL_IMAGE_MISSING` | 원본 사진 기록이 없어 수동 전환 불가 [구현 11/11] |
| 추가 | 409 | `NOT_RECHECKABLE` | 표본 재확인 대상이 아닌 검사 [제안 11/18] |
| 추가 | 409 | `ALREADY_RECHECKED` | 다른 결과로 이미 재확인된 검사 [제안 11/18] |
| 추가 | 409 | `NOT_ACKNOWLEDGEABLE` | 재확인 FAIL이 아닌 건 관리자 확인함 [구현 11/18] |
| 추가 | 409 | `NOT_REQUESTABLE` | 시스템 판정이 아닌 검사에 판정 확인 요청 [제안 11/23] |
| 추가 | 409 | `REQUEST_ALREADY_OPEN` | 같은 검사에 처리 대기 요청이 이미 있음 [제안 11/23] |
| 추가 | 409 | `REQUEST_ALREADY_RESOLVED` | 다른 결정으로 이미 처리된 요청 [제안 11/23] |
| 추가 | 404 | `REQUEST_NOT_FOUND` | 없는 판정 확인 요청 [제안 11/23] |
| 추가 | 409 | `AUTO_FAIL_NOT_CONFIGURED` | 불량 기준 없이 자동 불량을 켬 [제안 11/23] |
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
| TBD-01 | 배포 환경·이미지 저장소·타임아웃 | 유지 | 개발은 로컬 저장소·Mock AI. 계약은 "만료되는 접근 정보"로만 기술. 11/04 실측: 단건 DEFECT 약 3초·GOOD 0.3~1.2초. AI가 한 건씩 처리해 동시 2건이면 inferenceTimeMs 최대 8.9초 → 10초에 여유 약 1초. **동시 호출 1개, 타임아웃 10초 유지로 결정** [합의 11/04 김도현]: 5건 기준 AI 왕복 최대 4.4초, 전체 처리는 16.0초 → 20.0초로 늘어남 (통합 점검표 B11) 11/05 단건 DEFECT 6.8~7.9초(분류·CAM 인코딩 약 0.5초, 나머지 다운로드·전처리·CAM 생성 구간, 네트워크 지연 의심) → 원인 확인 필요 11/09 원인은 Mac→DGX 네트워크(다운로드 6~9.5초, INS-000097 DGX 처리 약 12.1초)로 확정 → **실행 타임아웃 20초(시연용), 동시 호출 1 유지** [합의 11/09 김도현] 11/11 프레임(8774)·카울커버(8778) 통합 모델은 별도 AI 서버라 **부품별 AI 주소**(`app.ai.part-base-urls`)를 추가. 7장 요청·응답 규격은 같음(8774 응답 형식 확인) | 이승규·김도현·김남균 |
| TBD-02 | 목표 미검출률 지정 방식 | **폐지** | 합의본에서 passThreshold 조정 방식으로 대체 | — |
| TBD-03 | ready 판정 기준 값·최소 표본 수 | 일부 확정 | 설정 주체는 확정(검증 자료 등록 시 기준 충족 여부로 결정). 기준 값은 AI 평가 후 제공. 임시 구현: 보정기 일치 + `app.policy.min-sample-count`(기본 0) (6.9) | 김도현 |
| TBD-04 | 검사항목 코드 이름 | 확정 (11/17) | 테이블 유지, 세 부품 모두 `UNIFIED`(통합 불량). 도어도 스크래치·외관 손상을 한 모델로 분류(김도현). V7에서 도어 `SCRATCH` → `UNIFIED`, 기존 검사·모델·정책은 id 연결이라 영향 없음 | 김남균·김도현 |
| TBD-05 | AI 응답 세부·오류 본문·Grad-CAM 전달 | **해소** | base64 PNG·JPEG [합의 10/28], DEFECT 예측만 생성, 오류는 공통 형식 (7장) | — |
| TBD-06 | predictedQuality와 정책 판정의 충돌 처리 | **해소** | DEFECT 예측은 항상 REVIEW, GOOD 예측만 AUTO_PASS 후보 (4장) | — |
| TBD-07 | rawDefectProbability 명칭 | 유지 | 현재 명칭 유지 | 전체 |
| TBD-08 | 업로드 형식·용량·해상도 | 유지 | JPEG·PNG, 20MB, 최소 해상도 검사 없음 | 이승규·김도현 |
| TBD-09 | EXIF 방향 보정 처리 지점 | 확장 | 원본과 Grad-CAM의 방향 일치까지 포함 | 이승규·김도현·홍승인 |
| TBD-10 | 로그인 실패 잠금 기준 | **해소** | 5회 실패 잠금, 관리자 해제 API `POST /admin/users/{loginId}/unlock` [구현 11/10] | — |
| TBD-11 | 시연·지원 부품 범위 | 일부 확정 | 시연·초기 연동은 도어. 최종 목표 약 4개 부품, 추가 부품과 시점은 AI가 추후 공유. 모델 없는 부품은 미지원 표시, 등록 정보 추가로 확장하는 구조 유지 | 김도현 |
| TBD-12 | Idempotency-Key 적용 여부 | 갱신 | 적용 주체가 앱에서 입력 프로그램으로 바뀜 | 이승규 |
| TBD-13 | 입력 프로그램 인증 | **해소** | DEVICE 역할 계정 로그인 → JWT | — |
| TBD-14 | iOS 종료·백그라운드 푸시 포함 여부 | 일부 확정 | RN + Expo 확정. 앱 실행 중 폴링 필수, Android 푸시 권장, iOS 푸시는 Apple Developer 계정 여부에 따라 결정 (8.1). 11/05 기준 앱 푸시 토큰 등록 미구현, 실행 방식(Expo Go 또는 개발용 빌드) 결정 필요 11/10 기준 앱 푸시 미구현 → 시연은 앱 실행 중 폴링(5초)으로 진행 [제안 11/10] | 전체 |
| TBD-15 | 과거 결과 재계산 설계 유지 여부 | **해소** | 제외 | — |
| TBD-16 | 표본 재확인 구간 경계(0.4·0.8)·비율(1.0·0.3·0.1), 불확실성 표시 방법 | 공동시험값 확정 (11/18) | **공동시험은 경계 0.4·0.8, 100·30·10%로 수집하고 50·30·10%를 같은 기록으로 비교** [합의 11/18 김도현]. 장기 적용값은 시험 후 결정. 규칙은 `v1-b40-80-p100-30-10` 형식으로 자동 생성하고 시험 이름은 선택, 판정 당시 규칙을 검사에 남겨 재처리도 그 규칙으로(V9). 전체 불량률은 구간 AUTO_PASS 건수 비중으로 가중 [합의 11/18 김도현]. 기본 꺼 둠. 신뢰구간 표시는 다음 단계 (6.11) | 김도현 |
| TBD-17 | 재확인 FAIL 시 알림·후속 조치 | 1차 합의 (11/18) | 원래 PASS·SYSTEM 유지, 상세에서 두 결과 함께 표시, 완료 목록 붉은색 + 관리자 안내, 관리자 "확인함"(해결 완료 아님) [합의 11/18 홍승인·김도현]. 푸시·자동 조치·해결 상태 기록은 팀 논의 후 (6.11) | 홍승인·전체 |
| TBD-18 | 자동 불량(AUTO_FAIL)·관리자 날짜별 집계·기준 상세 | 범위 변경 합의 (11/23) | 10/14 개발계획서 제외 항목(자동 FAIL, 통계·관리자 분석 화면)을 **범위 변경으로 진행** [합의 11/23 김도현]. 근거: 1차 공동시험에서 작업자가 PASS한 불량 3건 중 INS-000146·149가 제안 기준이면 자동 불량 대상(151은 REVIEW, 검사 기준 표시로 보완). AUTO_FAIL은 부품 정책별 **배포 기본 꺼짐**. 독립 검증 자료가 확보되지 않아(김도현 11/23) **기존 내부 평가로 정한 부품별 기준을 고정하고 공동시험 대상 부품만 켜서** 동작·작업량 감소·정상 자동 불량 사례를 확인한 뒤 실제 적용을 합의 [합의 11/23 김도현·홍승인]. 공동시험은 기능·작업량 확인이며 **독립 검증으로 해석하지 않음**. 한계 문구: "자동 불량 기준은 기존 내부 평가 자료로 정했다. 프레임·도어는 같은 평가 자료로 기준을 조정해 독립 검증이 아니며, 카울커버는 기준 선정에 쓰지 않은 분리 평가로 확인했다. 공동시험은 기능과 작업량 감소 확인용이며 정상 자동 불량 비율을 추정하지 않는다." 실제 적용 판단 기준(예: 시험에서 정상 자동 불량 1건이면 그 부품은 꺼짐 유지)은 시험 전에 정함. 초안 11/23: 3.2·4.1·6.9·6.13·8.2, 저장은 V13 (정책 `auto_fail_enabled`·`fail_threshold`·`fail_validated_min/max`, 검사 `fail_threshold_applied`, V5 CHECK 교체). 날짜별 집계 원칙 [합의 11/23 김도현]: 수동 전환(`AI_UNAVAILABLE`)은 작업자에게 배정된 REVIEW라 작업량에 포함하고 따로 표시 (예: REVIEW 3/4 · 수동 전환 1/1). AI의 REVIEW 비율 등 AI 성능 계산에서는 수동 전환을 제외. 원래 FAILED는 날짜표 검사 건수에서 빼되 장애 기록으로 남김. 수동 전환 검사는 새 REVIEW 검사가 생성된 KST 날짜에 귀속 | 김도현·홍승인·김남균 |
| TBD-19 | 판정 확인 요청의 근거 사진, 재확인과의 집계 관계 | 제안 (11/23) | 1단계는 글(부위·사유)만 받고 사진 첨부는 다음 단계. "자동 통과 후 불량 확인" 집계는 `CORRECTED` 요청 기준 검사 ID당 1건으로 세고, 표본 재확인 FAIL은 재확인 요약(6.11)에 따로 표시해 같은 검사를 두 번 세지 않음. **AUTO_FAIL 표본 재확인은 이번에 추가하지 않음** [합의 11/23 김도현]. 확인 요청만으로는 발견된 사례만 기록되고 전체 정상 오판 건수·비율은 알 수 없으며, 요청 0건이 오판 0건을 뜻하지 않음 → 신규 자료 검증과 기본 꺼짐으로 대응. 기존 재확인 구조는 재사용할 수 있으나 대상 조건·DB 제약·API·화면 변경이 필요한 후속 확장. 보고서 문구: "자동 불량의 정상 오판은 작업자 확인 요청과 관리자 정정을 통해 확인된 사례만 집계한다. 전수 확인이나 표본 검증을 수행하지 않으므로, 이 집계로 전체 오판율을 추정할 수 없다. 자동 불량 표본 재확인은 후속 확장 대상으로 둔다." | 김도현·홍승인 |
| TBD-20 | 기준 상세의 기준 라벨·실물 확인 결과 출처 | 제안 (11/23) | 서버에 라벨 저장 기능이 없어 이번에는 `reference: null`(자료 없음). 라벨 자료를 넣는 방식(파일 등록·검사 ID 매핑)은 김도현과 결정 | 김도현 |
| — | Grad-CAM 0맵·상수맵 처리 | **해소** [합의 10/28] | `gradcamStatus = NO_ACTIVATION`, 이미지 없음, 분류·REVIEW 유지 (6.5, 7.2) | — |
| — | `inferenceTimeMs` 측정 범위 | **해소** [합의 10/28] | AI handler 진입~응답 직렬화 직전, 모델 최초 로드 제외 (7.2) | — |
