# backend · 백엔드 API

담당: 이승규 · 기준 문서: [백엔드 API 계약 v4](../docs/백엔드_API계약_v4.md)

현재 구현 범위 (8주차)
- 인증: 로그인·토큰 재발급·로그아웃, 역할(WORKER·ADMIN·DEVICE)별 접근 제어, 로그인 5회 실패 잠금
- 사진 접수(비동기): `POST /api/v1/inspections` → 202, 스레드 풀(2개)에서 AI 호출·응답 검증·정책 적용
- 검사 상세: `GET /api/v1/inspections/{id}` (AI·정책·판정·이미지 블록, 만료되는 이미지 주소)
- 검사 이력: `GET /api/v1/inspections` (부품·displayState·기간 필터, 페이지)
- 모니터링: `GET /api/v1/monitoring/parts` (부품별 요약), `GET /api/v1/monitoring/queue` (확인 필요 목록, 커서)
- 작업자 확인: `POST /api/v1/inspections/{id}/confirm` (WORKER만)
- 재검사: `POST /api/v1/inspections/{id}/retry` (FAILED만, 새 검사 생성)
- Mock AI 서버 (`mock-ai/`, Python)

아직 없음: 관리자 정책 API, 기기 토큰·Expo 푸시 발송, `GET /parts`의 정책 적용·AI 모델 로드 여부

## 실행 방법

필요한 것: JDK 17~24 (Gradle 8.14는 JDK 25 이상에서 실행되지 않음), Docker, Python 3.10 이상

아래 명령은 모두 `backend/` 폴더에서 실행합니다.

```bash
docker compose up -d                 # MySQL 8.4 (DB/계정/비밀번호: inspection)
./gradlew build                      # 컴파일 + 단위 테스트
./gradlew bootRun                    # Flyway가 V1~V5와 개발용 시드(db/seed-dev) 적용

# 다른 터미널에서 Mock AI
cd mock-ai
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --port 8090
```

- Swagger UI: http://localhost:8080/swagger-ui.html (오른쪽 위 Authorize에 Access Token 입력)
- 이미 V1·V2만 적용된 DB에서도 그대로 실행하면 V3 이후가 추가 적용된다
- V5(무결성 제약)는 기존 행이 제약을 어기면 적용 중간에 실패한다. 오래된 개발 DB라면 먼저 김남균 `V5_precheck.sql`로 위반 0건을 확인하고, 위반이 있으면 `docker compose down -v`로 초기화

## 테스트 계정 (개발용, `src/main/resources/db/seed-dev`)

| 계정 | 비밀번호 | 역할 |
|---|---|---|
| worker01 | Worker1234! | WORKER |
| admin01 | Admin1234! | ADMIN |
| device-door | Device1234! | DEVICE (사진 입력 프로그램) |

시드에는 Mock 모델 `mock-door-swin-t-v1`(보정기 `mock-cal-v1`, active)과 예시 정책 `example-door-p1`(passThreshold 0.05, 검증 범위 0.02~0.08, ready·active)도 들어 있다. 실제 검증 값이 아니다.
실제 DOOR 모델 `door-swin-tiny-e20-8d042c7bfab2`(보정기 없음, 정책 없음)도 **비활성**으로 등록되어 있다 (아래 "실제 AI 연결").
**운영 배포 시 `spring.flyway.locations`에서 `classpath:db/seed-dev`를 빼야 한다.**

## 동작 확인 (curl)

```bash
# 1) 로그인 (DEVICE)
DEV=$(curl -s -X POST localhost:8080/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"loginId":"device-door","password":"Device1234!"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["accessToken"])')

# 2) 사진 접수 → 202, inspectionId 반환
curl -s -X POST localhost:8080/api/v1/inspections -H "Authorization: Bearer $DEV" \
  -F image=@sample.jpg -F partCode=DOOR

# 3) 작업자 로그인 후 상세 조회 (분석 중이면 displayState=ANALYZING, 1초 뒤 다시 조회)
WK=$(curl -s -X POST localhost:8080/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"loginId":"worker01","password":"Worker1234!"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["accessToken"])')
curl -s localhost:8080/api/v1/inspections/<inspectionId> -H "Authorization: Bearer $WK"
```

| 확인 | 기대 결과 |
|---|---|
| 토큰 없이 `GET /api/v1/parts` | 401 `AUTH_TOKEN_INVALID` |
| WORKER 토큰으로 `POST /api/v1/inspections` | 403 `ACCESS_DENIED` |
| 비밀번호 5회 틀림 | 5번째부터 423 `AUTH_ACCOUNT_LOCKED` |
| 같은 `Idempotency-Key`·같은 사진 재전송 | 200, 기존 inspectionId |
| 같은 키·다른 사진 | 422 `IDEMPOTENCY_KEY_MISMATCH` |
| Mock 시나리오별 결과 | `mock-ai/README.md` 표 참고 (AUTO_PASS, REVIEW 사유별, Grad-CAM GENERATED·FAILED·NO_ACTIVATION·JPEG, FAILED 오류별) |
| 이미지 주소 | 상세의 `images.original.url`을 브라우저로 열면 원본 표시, 10분 뒤 404 |

응답 헤더 `X-Trace-Id`와 서버 로그의 `[traceId]`가 같으면 추적 ID 연결이 정상이다. 분석 로그도 접수 요청과 같은 traceId로 남는다.

## 실제 AI 연결

계약 v4 7장 규격의 실제 AI 서버로 바꾸는 방법. 모델 버전은 `door-swin-tiny-e20-8d042c7bfab2` (보정기 미준비, 정책 없음 → 분석 성공 건은 모두 REVIEW가 정상: GOOD은 `NO_ACTIVE_POLICY`, DEFECT는 `DEFECT_PREDICTED`).

1. 활성 모델 전환 (검사항목당 active 모델은 1개, V5 제약). 순서대로 실행
   ```sql
   UPDATE ai_model SET active = FALSE WHERE model_version = 'mock-door-swin-t-v1';
   UPDATE ai_model SET active = TRUE  WHERE model_version = 'door-swin-tiny-e20-8d042c7bfab2';
   ```
   Mock 모델에 걸린 예시 정책 `example-door-p1`은 그대로 두면 "비활성 모델의 active 정책"으로 무결성 점검(I12)에 걸린다. 함께 중지하고, Mock으로 돌아올 때 다시 켠다
   ```sql
   UPDATE automation_policy SET active = FALSE WHERE policy_version = 'example-door-p1';
   ```
   Mock으로 되돌리기: 위 두 모델의 TRUE·FALSE를 바꿔(실제 모델 FALSE를 먼저) 실행하고 `example-door-p1`을 `active = TRUE`로
2. 백엔드를 AI 서버 주소와 함께 실행. AI 서버가 원본 사진을 내려받을 수 있도록 `PUBLIC_BASE_URL`은 **AI 서버에서 접근 가능한 이 PC의 주소**로
   ```bash
   APP_AI_BASEURL=http://<AI서버주소>:<포트> PUBLIC_BASE_URL=http://<이 PC 내부 IP>:8080 ./gradlew bootRun
   ```
   실제 추론이 오래 걸리면 `APP_AI_READTIMEOUTMS`(기본 10000)도 함께 조정
3. 확인: `GET {AI}/internal/v1/models`에 위 모델 버전이 있는지, 접수 후 상세의 `ai.modelVersion`

- 실제 DEFECT 응답은 Grad-CAM base64가 약 1,546만 자(15.5MB)로 크다. AI 응답 파싱 문자열 한도는 `app.ai.max-response-string-chars`(기본 5,000만 자, Jackson 기본 2,000만 자)
- 실제 응답 원문 3종 회귀 테스트: `src/test/resources/ai-samples/` (15MB `02_DEFECT.json`은 저장소에 올리지 않음. 파일이 없으면 해당 테스트는 건너뜀)

## 구조

```
auth/                로그인·재발급·로그아웃, JWT 필터, 401·403 공통 오류 응답
ai/                  AI 클라이언트, 요청·응답 형식, 응답 계약 검증
inspection/          접수(InspectionIntakeService), 비동기 분석(AnalysisDispatcher → InspectionAnalysisService),
                     정책 판정(PolicyEvaluator), 결과 저장(AnalysisResultWriter), 상세 조회, 재시작 정리
storage/             로컬 이미지 저장, 서명된 만료 주소, 이미지 제공 API
config/              AppProperties(app.*), Security, 분석 스레드 풀, Swagger
common/              공통 응답·오류, traceId, 시각 변환
domain/              엔티티·리포지토리
resources/db/migration   V1 스키마, V2 부품, V3 인증, V4 모니터링·비동기·Grad-CAM, V5 무결성 제약(김남균)
resources/db/seed-dev    개발용 계정·Mock 모델·예시 정책, 실제 DOOR 모델(비활성)
mock-ai/             Mock AI 추론 서버 (FastAPI)
```

## 미확정(TBD) 값 위치

모두 `application.yml`의 `app.*`에 있으며 코드 수정 없이 바꿀 수 있다.

| 설정 | TBD |
|---|---|
| `app.upload.*` 허용 형식·용량·최소 해상도 | TBD-08 |
| `app.ai.base-url`, `read-timeout-ms`, `retry-count` | TBD-01 |
| `app.storage.type`(local), `public-base-url` | TBD-01 |
| `app.auth.login-lock-threshold` | TBD-10 |
| `app.inspection.analysis-pool-size` | 실측 후 조정 |
| 검사항목 코드 `SCRATCH` (V2 시드) | TBD-04 |

## 문제 해결

- `Public Key Retrieval is not allowed` 오류: 데이터소스 URL 끝에 `&allowPublicKeyRetrieval=true` 추가 (로컬 개발에서만)
- Flyway 체크섬 오류: 이미 적용된 마이그레이션 파일을 수정한 경우. 개발 중이면 `docker compose down -v`로 DB 볼륨을 지우고 다시 실행
- 분석이 계속 ANALYZING: Mock AI 서버가 켜져 있는지, `app.ai.base-url` 확인. 서버를 재시작하면 ANALYZING 건은 FAILED로 정리됨
- Mock AI가 이미지를 못 읽음(422 → FAILED `AI_REQUEST_REJECTED`): `app.storage.public-base-url`이 Mock AI에서 접근 가능한 주소인지 확인
