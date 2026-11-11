-- V6: AI 없이 작업자 수동 판정 (docs/수동판정_결정안.md B안, 11/11 팀 합의)
-- FAILED 원본은 그대로 두고, 원본 사진을 재사용한 새 검사(source = MANUAL)를 만들어 기존 작업자 확인으로 판정
--   - 원본 연결은 재검사와 같은 retry_of_inspection_id (UNIQUE) → FAILED 1건당 재검사 또는 수동 전환 중 1건만
--   - 새 검사: status COMPLETED, recommended_action REVIEW, review_reason AI_UNAVAILABLE, AI 결과·정책 값 없음
-- CHECK는 결과가 NULL이면 통과하므로 비교 앞에 IS NOT NULL을 둔다 (V5 규칙과 같음)

-- 1) 허용값: source에 MANUAL, review_reason에 AI_UNAVAILABLE 추가
ALTER TABLE inspection DROP CHECK chk_insp_values;
ALTER TABLE inspection
    ADD CONSTRAINT chk_insp_values CHECK (
            (predicted_quality IS NULL OR predicted_quality IN ('GOOD', 'DEFECT'))
        AND (recommended_action IS NULL OR recommended_action IN ('AUTO_PASS', 'REVIEW'))
        AND (final_judgement IS NULL OR final_judgement IN ('PASS', 'FAIL'))
        AND (judged_by IS NULL OR judged_by IN ('SYSTEM', 'WORKER'))
        AND (review_reason IS NULL OR review_reason IN
                ('DEFECT_PREDICTED', 'NO_ACTIVE_POLICY', 'CALIBRATION_UNAVAILABLE', 'ABOVE_THRESHOLD', 'AI_UNAVAILABLE'))
        AND (gradcam_status IS NULL OR gradcam_status IN ('GENERATED', 'NOT_REQUIRED', 'FAILED', 'NO_ACTIVATION'))
        AND source IN ('DEVICE', 'ADMIN', 'RETRY', 'MANUAL'));

-- 2) 분석 완료 규칙: AI 결과 필수는 MANUAL이 아닐 때만 (V4 chk_insp_completed + V5 chk_insp_completed_v5 통합)
ALTER TABLE inspection DROP CHECK chk_insp_completed;
ALTER TABLE inspection DROP CHECK chk_insp_completed_v5;
ALTER TABLE inspection
    ADD CONSTRAINT chk_insp_completed_v6 CHECK (status <> 'COMPLETED' OR (
            recommended_action IS NOT NULL AND completed_at IS NOT NULL AND error_code IS NULL
        AND (source = 'MANUAL' OR (
                predicted_quality IS NOT NULL AND raw_defect_probability IS NOT NULL
            AND gradcam_status IS NOT NULL))));

-- 3) 수동 판정 건의 모양
ALTER TABLE inspection
    -- MANUAL: 완료·REVIEW·AI_UNAVAILABLE, 원본 FAILED 연결 필수, AI 결과·정책 값 없음
    ADD CONSTRAINT chk_insp_manual CHECK (source <> 'MANUAL' OR (
            status = 'COMPLETED' AND retry_of_inspection_id IS NOT NULL
        AND recommended_action IS NOT NULL AND recommended_action = 'REVIEW'
        AND review_reason IS NOT NULL AND review_reason = 'AI_UNAVAILABLE'
        AND predicted_quality IS NULL AND raw_defect_probability IS NULL
        AND calibrated_defect_probability IS NULL AND calibrator_version IS NULL
        AND gradcam_status IS NULL AND inference_time_ms IS NULL
        AND policy_id IS NULL AND automation_policy_ready = FALSE AND pass_threshold_applied IS NULL)),
    -- AI_UNAVAILABLE 사유는 수동 판정 건에만
    ADD CONSTRAINT chk_insp_reason_ai_unavailable CHECK (review_reason IS NULL
        OR review_reason <> 'AI_UNAVAILABLE' OR source = 'MANUAL');
