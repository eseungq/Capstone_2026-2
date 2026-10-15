# inspection-backend (3조 김이홍 · 백엔드 API)

AI 기반 자동차 부품 품질검사 플랫폼의 백엔드. 기준 문서는 **백엔드 API 계약 v4** (`04_6주차_방향수정/백엔드_API계약_v4_초안_1015.md`).

현재 구현 범위 (7주차)
- 인증: 로그인·토큰 재발급·로그아웃, 역할(WORKER·ADMIN·DEVICE)별 접근 제어, 로그인 5회 실패 잠금
- 사진 접수(비동기): `POST /api/v1/inspections` → 202, 스레드 풀(2개)에서 AI 호출·응답 검증·정책 적용
- 검사 상세: `GET /api/v1/inspections/{id}` (AI·정책·판정·이미지 블록, 만료되는 이미지 주소)
- Mock AI 서버 (`mock-ai/`, Python)

아직 없음: 모니터링·확인 필요 목록, 작업자 확인(confirm), 재검사(retry), 관리자 정책 API, Expo 푸시 발송

## 실행 방법

필요한 것: JDK 17 또는 21, Docker, Python 3.10 이상

```bash
docker compose up -d                 # MySQL 8.4 (DB/계정/비밀번호: inspection)
./gradlew build                      # 컴파일 + 단위 테스트
./gradlew bootRun                    # Flyway가 V1~V4와 개발용 시드(db/seed-dev) 적용

# 다른 터미널에서 Mock AI
cd mock-ai
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --port 8090
```

- Swagger UI: http://localhost:8080/swagger-ui.html (오른쪽 위 Authorize에 Access Token 입력)
- 이미 V1·V2만 적용된 DB에서도 그대로 실행하면 V3·V4가 추가 적용된다

## 테스트 계정 (개발용, `src/main/resources/db/seed-dev`)

| 계정 | 비밀번호 | 역할 |
|---|---|---|
| worker01 | Worker1234! | WORKER |
| admin01 | Admin1234! | ADMIN |
| device-door | Device1234! | DEVICE (사진 입력 프로그램) |

시드에는 Mock 모델 `mock-door-swin-t-v1`(보정기 `mock-cal-v1`)과 예시 정책 `example-door-p1`(passThreshold 0.05, 검증 범위 0.02~0.08, ready·active)도 들어 있다. 실제 검증 값이 아니다.
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
| Mock 시나리오별 결과 | `mock-ai/README.md` 표 참고 (AUTO_PASS, REVIEW 사유별, FAILED 오류별) |
| 이미지 주소 | 상세의 `images.original.url`을 브라우저로 열면 원본 표시, 10분 뒤 404 |

응답 헤더 `X-Trace-Id`와 서버 로그의 `[traceId]`가 같으면 추적 ID 연결이 정상이다. 분석 로그도 접수 요청과 같은 traceId로 남는다.

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
resources/db/migration   V1 스키마, V2 부품, V3 인증, V4 모니터링·비동기·Grad-CAM
resources/db/seed-dev    개발용 계정·Mock 모델·예시 정책
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
