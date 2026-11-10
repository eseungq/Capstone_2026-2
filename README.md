# AI 기반 자동차 부품 품질검사 플랫폼

캡스톤디자인 2026-2 · 3조 김이홍

공정에서 촬영한 부품 사진을 AI가 분석하고, 기준을 만족한 건만 자동 통과시키고 나머지는 작업자가 앱에서 확인해 최종 판정하는 시스템입니다.

## 팀 구성

| 파트 | 담당 | 폴더 | 하는 일 |
|---|---|---|---|
| 백엔드 API | 이승규 | [`backend/`](backend/) | 사진 접수, AI 호출, 자동 통과 판정, 검사 기록·작업자 확인·재검사, 관리자 정책, 알림 |
| AI | 김도현 | [`ai/`](ai/) | 불량 분류 모델, 확률 보정, Grad-CAM, 추론 서버, 정책 검증 자료 |
| 모바일 앱 | 홍승인 | [`mobile/`](mobile/) | 작업자·관리자 앱 (모니터링, 상세, 판정, 재검사, 정책 화면) |
| DB | 김남균 | [`db/`](db/) | 저장 구조 설계, 제약·조회 검증 |

## 시스템 구성

```mermaid
flowchart LR
    CAM["사진 입력 프로그램<br/>(공정 촬영 모사)"] -- "사진 접수" --> BE["백엔드 API<br/>Spring Boot"]
    BE -- "추론 요청" --> AI["AI 추론 서버"]
    AI -- "예측·보정 확률·Grad-CAM" --> BE
    BE <--> DB[("MySQL")]
    APP["모바일 앱<br/>작업자·관리자"] -- "조회·판정·재검사" --> BE
    BE -. "푸시 알림" .-> APP
```

검사 흐름

1. 입력 프로그램이 사진을 올리면 백엔드가 원본을 저장하고 바로 접수 번호를 돌려줍니다 (분석은 비동기)
2. 백엔드가 AI 서버에 분석을 요청하고, 응답과 활성 정책으로 **자동 통과(AUTO_PASS)** 또는 **작업자 확인(REVIEW)** 을 정합니다
3. REVIEW 건은 작업자가 사진과 판단 근거(Grad-CAM)를 보고 PASS·FAIL을 확정합니다. REVIEW·분석 실패 알림은 백엔드 발송까지 구현됐고 앱 푸시 등록·수신은 미구현입니다
4. 분석에 실패한 건은 같은 사진으로 재검사합니다 (원래 기록은 그대로 두고 새 검사 생성). FAILED 직접 수동 판정은 방식 미결정으로 아직 지원하지 않습니다

자세한 규칙은 [docs/백엔드_API계약_v4.md](docs/백엔드_API계약_v4.md)를 기준으로 합니다.

## 폴더 구조

```
.
├── backend/   백엔드 API (Spring Boot 3.5, Java 17, MySQL 8.4) + 개발용 Mock AI
├── ai/        AI 추론 서버·모델
├── mobile/    모바일 앱 (React Native, Expo)
├── db/        DB 설계 SQL·ERD
└── docs/      공통 기준 문서 (API 계약 등)
```

각 폴더의 README에 실행 방법을 적습니다.

## 통합 실행 순서

개발용은 PC 한 대에서 Mock AI로, 실제 연결은 Tailscale로 Mac(백엔드)·DGX(AI)·iPhone(앱)을 묶어 실행합니다.

| 순서 | 무엇 | 방법 |
|---|---|---|
| 1 | MySQL | `backend/`에서 `docker compose up -d` (기존 `inspection-mysql` 컨테이너가 있으면 `docker start inspection-mysql`) |
| 2 | AI 서버 | 실제 서버는 [`ai/`](ai/) 안내 (DGX, 포트 8771), 없으면 [`backend/mock-ai`](backend/mock-ai/) (포트 8090) |
| 3 | 백엔드 | `backend/`에서 `./gradlew bootRun` (포트 8080, Swagger: `/swagger-ui.html`). 실제 AI는 `APP_AI_BASEURL`·`PUBLIC_BASE_URL` 지정 |
| 4 | 앱 | [`mobile/`](mobile/) 안내. 백엔드 주소는 `localhost`가 아니라 PC의 Tailscale 또는 내부 IP |

명령과 테스트 계정은 [backend/README.md](backend/README.md)에 있습니다.

## 진행 현황

| 파트 | 현재 상태 (11/10) |
|---|---|
| 백엔드 | 인증(로그인 5회 실패 잠금·관리자 해제·토큰 회전)·사진 접수(비동기)·AI 연동·검사 상세/이력·모니터링·작업자 판정·재검사·관리자 정책·기기 토큰/Expo 푸시 발송 구현. DB V5 무결성 제약 적용. 11/10 테스트 97건 통과(접수 검증·잠금 해제·토큰 회전 통합 테스트 추가), Backend·Mobile CI 구성. AI 읽기 타임아웃은 시연용 20초, 동시 호출 1개. 수동 판정은 [결정안](docs/수동판정_결정안.md) 작성·팀 결정 대기, 통계 API는 합의본상 범위 제외(앱 통계 화면은 시연용 Mock) |
| AI | e02 모델(`door-swin-tiny-e02-28a2dd1cb40b-dev`) 실제 연결 시험 완료(11/04), 20초 타임아웃 적용 후 GOOD·DEFECT 재확인(11/09). 운영 보정기 미제공(`releaseReady=false`)으로 분석 완료 건은 REVIEW 유지. 30%는 사후 비교한 시연 기준이며 실서버 AUTO_PASS에 적용하지 않음. 자세한 내용은 [ai/README.md](ai/README.md), [ai/VALIDATION.md](ai/VALIDATION.md) |
| 모바일 앱 | 로그인·토큰 재발급·모니터링·상세·판정·재검사·이력 연동 코드 main 반영(PR #4·#6·#7·#8). iPhone 실서버 이력 필터/페이지·원본/Grad-CAM·역할별 UI 확인(11/10). 실제 판정/재검사 POST·409·이미지 URL 만료는 미검증. PR #9는 Draft 미병합: 폴링 반복 성공·20→40건 더 보기/접기·상세 이동 확인, 신규 검사 관측 시간 미측정. 통계·정책 화면은 Mock, 푸시 토큰 등록은 미구현 |
| DB | V1~V5 비교용 스키마·저장 흐름·제약 위반 시험 28건·무결성 점검 12개·ERD 업로드. 11/05 실제 DB 무결성 12개 모두 위반 0건. PR #11로 판정 기록 구분·시연 범위의 명세서 개정 문안 반영. 실제 스키마는 백엔드 Flyway 기준. 검사항목 코드 변경(TBD-04)은 미확정. 자세한 내용은 [db/README.md](db/README.md) |

연결 시험 결과는 [docs/통합_점검표.md](docs/통합_점검표.md)에 기록합니다. 시연 순서와 장애 대비는 [docs/시연_절차서.md](docs/시연_절차서.md)(초안)를 따릅니다.

- 열린 PR: [#9 모니터링 관측·더 보기](https://github.com/eseungq/Capstone_2026-2/pull/9)(Draft), [#12 도어 30→35% 독립 Mock 시연](https://github.com/eseungq/Capstone_2026-2/pull/12)(Draft 해제·승인 기록 있음, 미병합). PR #12의 iPhone Mock 저장·적용·기존 기록 보존은 확인됐으며 WORKER 화면 제한·회귀 확인은 남아 있습니다.
- 11/10 시험 준비 확인: 백엔드 로컬/Tailscale HTTP 200·WORKER/DEVICE 로그인 정상, DOOR 확인 필요 63건·분석 실패 19건. 도어 AI 8771은 연결 거부·`modelAvailable=false`여서 신규 접수는 실행하지 않았습니다. 팀 전달로 DGX는 카울커버 학습 중이며 당일 20시 이후 사용 가능 예정입니다. 학습과 도어 서버 중단의 인과관계는 미확인이고, 재가동 확인 후 앱 준비 시점을 맞춰 1건을 접수합니다.

각 파트 담당자가 직접 갱신합니다.

## 협업 규칙

- **main에 직접 push하지 않습니다.** 파트별 브랜치에서 작업하고 Pull Request로 합칩니다
  - 브랜치 이름: `backend/작업명`, `ai/작업명`, `mobile/작업명`, `db/작업명`
- 다른 파트 폴더를 고쳐야 하면 그 파트 담당자에게 먼저 알리고 PR 리뷰를 받습니다
- API 형식·상태 값·판정 규칙을 바꿀 때는 `docs/`의 계약 문서를 먼저 고칩니다
- 커밋 메시지는 한국어로 짧게, 한 커밋에는 한 가지 변경만
- **공개 저장소입니다.** 비밀번호·토큰·`.env`, 실제 공정 사진, 개인정보, 큰 모델 파일은 올리지 않습니다
