-- V13: 자동 불량 AUTO_FAIL 정책 쪽 (계약 4.1·6.9, TBD-18 범위 변경 합의 11/23)
--   - 자동 불량 켜짐 여부·불량 기준·검증 범위. 기존 정책은 모두 꺼짐(FALSE)·기준 NULL로 시작해 소급하지 않음
--   - 검사 쪽(판정 당시 불량 기준 스냅숏, AUTO_FAIL 허용)은 V14
--   - CHECK는 결과가 NULL이면 통과하므로 비교 앞에 IS NOT NULL을 둔다 (V5 규칙과 같음)
--
-- 버전 하나 = ALTER TABLE 한 문장 (#52 리뷰)
--   - MySQL은 DDL마다 자동 커밋이라 한 버전에 ALTER가 둘이면 두 번째가 실패했을 때 첫 번째만 남고,
--     flyway repair 후 다시 돌리면 첫 번째의 ADD COLUMN이 "이미 있음"으로 막힘
--   - 한 문장(MySQL 8 원자적 DDL)이면 실패해도 이 테이블은 V12 그대로라, 원인을 고치고
--     flyway repair로 실패 기록을 지운 뒤 다시 적용하면 됨. V14가 실패해도 V13은 성공으로 남고 V14만 다시 적용
--   - 새 컬럼은 기본값이 있어 V14 적용 전에도 기존 동작에 영향 없음 (자동 불량은 모두 꺼짐)

-- automation_policy
--   chk_policy_fail_range: 세 값 모두 0~1
--   chk_policy_fail_valid_order: 검증 범위 min ≤ max
--   chk_policy_fail_threshold_range: 불량 기준이 있으면 검증 범위도 있고 그 안 (API는 셋을 함께 받음)
--   chk_policy_fail_above_pass: 불량 기준 > 통과 기준 (같으면 한 확률이 자동 통과·자동 불량 둘 다 될 수 있음)
--   chk_policy_auto_fail_configured: 켜려면 불량 기준 필수 (API 409 AUTO_FAIL_NOT_CONFIGURED)
ALTER TABLE automation_policy
    ADD COLUMN auto_fail_enabled  BOOLEAN       NOT NULL DEFAULT FALSE AFTER validated_max, -- 자동 불량 켜짐
    ADD COLUMN fail_threshold     DECIMAL(7, 6) NULL AFTER auto_fail_enabled,                -- 보정 확률 ≥ 이 값이면 AUTO_FAIL
    ADD COLUMN fail_validated_min DECIMAL(7, 6) NULL AFTER fail_threshold,                   -- AI가 검증한 불량 기준 범위
    ADD COLUMN fail_validated_max DECIMAL(7, 6) NULL AFTER fail_validated_min,
    ADD CONSTRAINT chk_policy_fail_range CHECK (
            (fail_threshold IS NULL OR (fail_threshold >= 0 AND fail_threshold <= 1))
        AND (fail_validated_min IS NULL OR (fail_validated_min >= 0 AND fail_validated_min <= 1))
        AND (fail_validated_max IS NULL OR (fail_validated_max >= 0 AND fail_validated_max <= 1))),
    ADD CONSTRAINT chk_policy_fail_valid_order CHECK (fail_validated_min IS NULL OR fail_validated_max IS NULL
        OR fail_validated_min <= fail_validated_max),
    ADD CONSTRAINT chk_policy_fail_threshold_range CHECK (fail_threshold IS NULL OR (
            fail_validated_min IS NOT NULL AND fail_validated_max IS NOT NULL
        AND fail_threshold >= fail_validated_min AND fail_threshold <= fail_validated_max)),
    ADD CONSTRAINT chk_policy_fail_above_pass CHECK (fail_threshold IS NULL OR pass_threshold IS NULL
        OR fail_threshold > pass_threshold),
    ADD CONSTRAINT chk_policy_auto_fail_configured CHECK (auto_fail_enabled = FALSE OR fail_threshold IS NOT NULL);
