# db · DB 설계

담당: 김남균

실제 서버에 적용되는 스키마는 백엔드의 Flyway 마이그레이션입니다: [backend/src/main/resources/db/migration](../backend/src/main/resources/db/migration) (V1~V5 적용됨).
설계를 바꿀 때는 **이미 적용된 V1~V5는 수정하지 않고** 다음 버전(V6~) 파일로 추가합니다. 이 폴더의 SQL은 Flyway에 넣지 않습니다.

저장 구조 기준: 계약 v4 9장 · 명세서 4.3 개정 문안(11/05)

## 파일

| 파일 | 내용 | 실행 결과가 정상이면 |
|---|---|---|
| `01_schema.sql` | V1→V2→V3→V4→V5 적용 결과를 CREATE TABLE 한 파일로 합친 **비교용** 전체 스키마 (시드 데이터 제외) | 실행하지 않음 (읽기용) |
| `02_write_paths.sql` | 저장 흐름 예시: 접수 → 분석 → 완료(AUTO_PASS·REVIEW·DEFECT) / 실패 → 작업자 확인 → 재검사 → 기준 조정 → 재시작 정리. 마지막에 ROLLBACK | 오류 없이 끝남, 데이터 남지 않음 |
| `03_negative_tests.sql` | 제약 위반 테스트 28건 (`-- EXPECT ERROR:` 문장). 마지막에 ROLLBACK | 28건 모두 오류 (3819·1062·1452) |
| `04_integrity_checks.sql` | CHECK로 못 막는 테이블 간 규칙 12개 (작업자 확인 누락, 원본 이미지 누락, Grad-CAM 상태와 이미지 불일치, 재검사 연결 등) | 12개 모두 0건 |
| `erd/ERD_v5.png` | ERD (Flyway V1~V5 기준) | — |
| `docs/명세서_4.3_개정문안_1105.*` | 명세서 4.3 데이터베이스 요구사항 개정 문안 (FR-DB-05 NO_ACTIVATION 반영) | — |

## 실행 방법 (MySQL Workbench)

1. 개발 DB에 접속 (접속 정보는 팀 내부 공유, 레포에 적지 않음)
2. `04_integrity_checks.sql`: 그대로 실행 → 결과 탭 12개가 모두 빈 결과면 정상
3. `03_negative_tests.sql`: Workbench 설정에서 "오류 시 중지"를 끄고 전체 실행 → `EXPECT ERROR` 28건이 모두 오류면 정상. 마지막 ROLLBACK으로 테스트 행은 남지 않음
   - 공유 DB에서 돌릴 때는 한 번에 끝까지 실행할 것 (중간에 멈추면 연결을 끊어 되돌림)

## 저장 규칙 요약

- 상태: RECEIVED → ANALYZING → COMPLETED(AUTO_PASS / REVIEW) 또는 FAILED. FAILED는 이후 변경 없음, 예측값 저장 안 함
- AUTO_PASS: GOOD 예측 + 준비·적용된 정책 + 보정 확률 ≤ 판정 당시 기준치(`pass_threshold_applied`)
- REVIEW 사유 우선순위: DEFECT_PREDICTED > NO_ACTIVE_POLICY > CALIBRATION_UNAVAILABLE > ABOVE_THRESHOLD
- Grad-CAM 상태: GOOD → NOT_REQUIRED, DEFECT → GENERATED(이미지 행 있음)·FAILED·NO_ACTIVATION(이미지 행 없음)
- 재검사: 원래 FAILED 행은 그대로 두고 새 검사 행(source = RETRY), FAILED 1건당 1회
- 기준 조정: 정책 행을 수정하지 않고 새 버전(`based_on_policy_id`)
- 시연용 모델·정책은 `mock-`·`example-` 접두어 (실제 검증 값 아님)

## 남은 확인

- 검사항목 코드 `SCRATCH` → `APPEARANCE` 변경 여부 (TBD-04, 김도현 확인 후 백엔드 시드와 함께 변경)
