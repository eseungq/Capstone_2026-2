-- V13: 자동 불량 AUTO_FAIL (계약 4.1·6.9, TBD-18 범위 변경 합의 11/23)
--   - 정책: 자동 불량 켜짐 여부·불량 기준·검증 범위. 기존 정책은 모두 꺼짐(FALSE)·기준 NULL로 시작해 소급하지 않음
--   - 검사: 판정 당시 불량 기준 스냅숏 (자동 불량이 꺼져 있었으면 NULL)
--   - CHECK는 결과가 NULL이면 통과하므로 비교 앞에 IS NOT NULL을 둔다 (V5 규칙과 같음)
--
-- 테이블마다 기존 CHECK 삭제와 새 CHECK 추가를 ALTER TABLE 한 문장으로 묶음 (V10과 같은 방식, 김남균 #47 리뷰)
--   - 한 문장이면 ADD가 실패해도 그 테이블은 V12 그대로 (MySQL 8 원자적 DDL)
--   - 두 테이블은 문장이 달라, 두 번째(inspection)가 실패하면 automation_policy만 바뀐 상태로 남음.
--     새 컬럼은 기본값이 있어 기존 동작에 영향이 없고, 원인을 고친 뒤 flyway repair 후 다시 적용
--
-- V4~V10의 inspection CHECK 중 AUTO_FAIL 행(COMPLETED·DEFECT·FAIL·SYSTEM·사유 없음·정책 있음)과 충돌하는 것은
-- 허용값 목록 chk_insp_values뿐이라 그것만 교체. 나머지는 그대로 성립
--   chk_insp_failed·chk_insp_completed_v6·chk_insp_judged_by(_null)·chk_insp_gradcam: 값이 채워져 있어 통과
--   chk_insp_auto_pass·chk_insp_review·chk_insp_recheck_rule: AUTO_PASS·REVIEW 전용이라 해당 없음 (재확인 규칙은 AUTO_PASS만)
--   chk_insp_reason_review_only·chk_insp_reason_defect: 사유 NULL이고 REVIEW가 아니라 통과
--   chk_insp_policy_snapshot·chk_insp_policy_ready_snapshot: 정책·통과 기준 스냅숏을 함께 기록하므로 통과
--   chk_insp_manual: 수동 판정 건은 REVIEW만이라 AUTO_FAIL이 될 수 없음

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

-- inspection
--   chk_insp_values: recommended_action에 AUTO_FAIL 추가 (나머지는 V6 그대로)
--   chk_insp_auto_fail: AUTO_FAIL은 DEFECT 예측·준비된 정책·보정 확률 ≥ 불량 기준 스냅숏·FAIL·SYSTEM·사유 없음
--   chk_insp_fail_threshold: 불량 기준 스냅숏은 0~1이고 정책이 적용된 건에만. NULL은 어디서나 허용
--     (자동 불량을 켠 정책으로 판정한 AUTO_PASS·REVIEW도 스냅숏을 남김. 꺼져 있었으면 NULL)
ALTER TABLE inspection
    ADD COLUMN fail_threshold_applied DECIMAL(7, 6) NULL AFTER pass_threshold_applied,      -- 판정 당시 불량 기준 스냅숏
    DROP CHECK chk_insp_values,
    ADD CONSTRAINT chk_insp_values CHECK (
            (predicted_quality IS NULL OR predicted_quality IN ('GOOD', 'DEFECT'))
        AND (recommended_action IS NULL OR recommended_action IN ('AUTO_PASS', 'AUTO_FAIL', 'REVIEW'))
        AND (final_judgement IS NULL OR final_judgement IN ('PASS', 'FAIL'))
        AND (judged_by IS NULL OR judged_by IN ('SYSTEM', 'WORKER'))
        AND (review_reason IS NULL OR review_reason IN
                ('DEFECT_PREDICTED', 'NO_ACTIVE_POLICY', 'CALIBRATION_UNAVAILABLE', 'ABOVE_THRESHOLD', 'AI_UNAVAILABLE'))
        AND (gradcam_status IS NULL OR gradcam_status IN ('GENERATED', 'NOT_REQUIRED', 'FAILED', 'NO_ACTIVATION'))
        AND source IN ('DEVICE', 'ADMIN', 'RETRY', 'MANUAL')),
    ADD CONSTRAINT chk_insp_auto_fail CHECK (recommended_action IS NULL OR recommended_action <> 'AUTO_FAIL' OR (
            predicted_quality IS NOT NULL AND predicted_quality = 'DEFECT'
        AND automation_policy_ready = TRUE AND policy_id IS NOT NULL
        AND calibrated_defect_probability IS NOT NULL AND fail_threshold_applied IS NOT NULL
        AND calibrated_defect_probability >= fail_threshold_applied
        AND final_judgement IS NOT NULL AND final_judgement = 'FAIL'
        AND judged_by IS NOT NULL AND judged_by = 'SYSTEM'
        AND review_reason IS NULL)),
    ADD CONSTRAINT chk_insp_fail_threshold CHECK (fail_threshold_applied IS NULL OR (
            fail_threshold_applied >= 0 AND fail_threshold_applied <= 1
        AND automation_policy_ready = TRUE AND policy_id IS NOT NULL));
