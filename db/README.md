# db · DB 설계

담당: 김남균

실제 서버에 적용되는 스키마는 백엔드의 Flyway 마이그레이션입니다: [backend/src/main/resources/db/migration](../backend/src/main/resources/db/migration) (V1~V10 적용됨, V11·V12는 PR #50·#51).
설계를 바꿀 때는 **이미 적용된 마이그레이션은 수정하지 않고** 다음 버전 파일로 추가합니다. 이 폴더의 SQL은 Flyway에 넣지 않습니다.

저장 구조 기준: 계약 v4 9장(11/18 갱신) · 명세서 4.3 개정 문안(11/11) · [수동 판정 결정안](../docs/수동판정_결정안.md)

## 파일

| 파일 | 내용 | 실행 결과가 정상이면 |
|---|---|---|
| `01_schema.sql` | V1~V10 적용 결과를 CREATE TABLE 한 파일로 합친 **비교용** 전체 스키마 (시드 데이터 제외) | 실행하지 않음 (읽기용) |
| `02_write_paths.sql` | 저장 흐름 예시: 접수 → 분석 → 완료(AUTO_PASS·REVIEW·DEFECT) → 표본 재확인(추출·재확인·확인함) / 실패 → 작업자 확인 → 재검사 → 수동 판정 → 기준 조정 → 재시작 정리. 마지막에 ROLLBACK | 오류 없이 끝남, 데이터 남지 않음 |
| `03_negative_tests.sql` | 제약 위반 테스트 49건 (`-- EXPECT ERROR:` 문장, N29~N33은 V6 수동 판정, N34~N43은 V8·V9 표본 재확인, N44~N49는 V10). 마지막에 ROLLBACK | 49건 모두 오류 (3819·1062·1452) |
| `04_integrity_checks.sql` | CHECK로 못 막는 테이블 간 규칙 29개 (작업자 확인 누락, 원본 이미지 누락, Grad-CAM 상태와 이미지 불일치, 재검사·수동 판정 연결 등. I13·I14는 수동 판정, I15~I22는 표본 재확인, I23~I29는 일괄 FAIL·판정 확인 요청으로 V11·V12 적용 후 실행) + 참고 X1(재확인 결정 누락) | I1~I29 모두 0건 (X1은 참고) |
| `erd/ERD_v9.png` | ERD (Flyway V1~V9 기준, 표본 재확인 테이블 포함. V10은 CHECK만 바뀌어 그림 같음) | — |
| `docs/명세서_4.3_개정문안_1111.*` | 명세서 4.3 데이터베이스 요구사항 개정 문안 (판정 기록 3단계, 시연 정책 30%, NO_ACTIVATION, 수동 판정 MANUAL·AI_UNAVAILABLE) | — |

## 실행 방법 (MySQL Workbench)

1. 개발 DB에 접속 (접속 정보는 팀 내부 공유, 레포에 적지 않음)
2. `04_integrity_checks.sql`: 그대로 실행 → I1~I29 결과 탭이 모두 빈 결과면 정상 (V11·V12 적용 전 DB에서는 I23~I29가 테이블·컬럼 없음 오류). 마지막 X1은 재처리 대기 건 확인용이라 행이 있어도 오류 아님
3. `03_negative_tests.sql`: Workbench 설정에서 "오류 시 중지"를 끄고 전체 실행 → `EXPECT ERROR` 49건이 모두 오류면 정상. 마지막 ROLLBACK으로 테스트 행은 남지 않음
   - 공유 DB에서는 팀과 시간을 맞춰 한 번에 끝까지 실행할 것 (중간에 멈추면 연결을 끊어 되돌림)

> 명세서 4.3은 아직 11/11(V6) 기준입니다. 표본 재확인(V8·V9)은 계약상 [제안] 단계라 팀 확정 후 반영합니다.

## 저장 규칙 요약

- 상태: RECEIVED → ANALYZING → COMPLETED(AUTO_PASS / REVIEW) 또는 FAILED. FAILED는 이후 변경 없음, 예측값 저장 안 함
- AUTO_PASS: GOOD 예측 + 모델·보정기 버전이 맞는 준비·적용(ready·active) 정책 + 보정 확률 ≤ 판정 당시 기준치(`pass_threshold_applied`). 최종 판정은 PASS, 판정 주체 SYSTEM
- REVIEW 사유 우선순위: DEFECT_PREDICTED > NO_ACTIVE_POLICY > CALIBRATION_UNAVAILABLE > ABOVE_THRESHOLD. `AI_UNAVAILABLE`은 수동 판정 건 전용
- Grad-CAM 상태: GOOD → NOT_REQUIRED, DEFECT → GENERATED(이미지 행 있음)·FAILED·NO_ACTIVATION(이미지 행 없음)
- 재검사·수동 판정: 원래 FAILED 행은 그대로 두고 새 검사 행을 만들어 `retry_of_inspection_id`로 연결, 원본 이미지는 같은 저장 위치 참조. FAILED 1건당 재검사 또는 수동 전환 중 1건만
  - 재검사(`source = RETRY`): 접수부터 다시 분석
  - 수동 판정(`source = MANUAL`, V6): 바로 COMPLETED·REVIEW·`AI_UNAVAILABLE`, AI 결과·정책 값 없음, 부품·검사항목·모델은 원래 FAILED와 같음. 작업자가 기존 확인으로 판정
- 기준 조정: 정책 행을 수정하지 않고 검증 범위 안에서 새 버전(`based_on_policy_id`)
- 판정 기록은 AI 예측 / 정책 결과 / 최종 판정으로 구분 저장, 앞 단계 값은 바꾸지 않음
- 판정 확인 요청(V12, 계약 6.12): 시스템 판정 건만, 요청 WORKER·처리 ADMIN, 검사당 대기 1건. 정정해도 검사의 최초 판정은 바꾸지 않음(현재 판정 = 마지막 CORRECTED 요청). 일괄 FAIL(V11)은 batch_id로 구분
- 표본 재확인(V8·V9): AUTO_PASS마다 추출 결정 1행(뽑히지 않아도 기록), 판정 당시 규칙을 검사에 연결(`recheck_rule_id`), 재확인은 WORKER·확인함은 ADMIN·FAIL만. 원래 판정(PASS·SYSTEM)은 바꾸지 않음. 집계는 계약 6.11(구간 AUTO_PASS 비중으로 가중)
- 시연용 모델·정책은 `mock-`·`example-` 접두어 (실제 검증 값 아님)
- 도어 e02 시연 기준(보정 확률 30% 이하 AUTO_PASS)은 시연 범위로만 기록, 운영 활성 정책 등록 보류

## 남은 확인

- V12 적용 후: 01_schema·위반 테스트·ERD에 judgement_request·batch_id 반영 예정
- 표본 재확인 장기 비율·불확실성 표시 (TBD-16), 재확인 FAIL 후속 조치 (TBD-17)
- 검사항목 코드는 11/17 `UNIFIED`로 확정·V7 적용 (TBD-04 해소)
