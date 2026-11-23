-- V14: 자동 불량 AUTO_FAIL 검사 쪽 (계약 4.1·6.9, V13 다음)
--   - 판정 당시 불량 기준 스냅숏 (자동 불량이 꺼져 있었으면 NULL), recommended_action에 AUTO_FAIL 허용
--   - CHECK는 결과가 NULL이면 통과하므로 비교 앞에 IS NOT NULL을 둔다 (V5 규칙과 같음)
--
-- 기존 CHECK 삭제와 새 CHECK 추가를 ALTER TABLE 한 문장으로 묶음 (V10과 같은 방식, 김남균 #47 리뷰)
--   - 실패하면 inspection은 V13 그대로(컬럼 추가·CHECK 교체 모두 안 됨). 원인을 고치고 flyway repair 후 다시 적용
--   - 이 버전만 실패한 상태에서는 recommended_action에 AUTO_FAIL을 넣을 수 없어, 정책에서 자동 불량을 켜도
--     판정 저장이 CHECK로 막힘 → V14를 적용하기 전에는 자동 불량을 켜지 말 것 (기본 꺼짐)
--
-- V4~V10의 inspection CHECK 중 AUTO_FAIL 행(COMPLETED·DEFECT·FAIL·SYSTEM·사유 없음·정책 있음)과 충돌하는 것은
-- 허용값 목록 chk_insp_values뿐이라 그것만 교체. 나머지는 그대로 성립
--   chk_insp_failed·chk_insp_completed_v6·chk_insp_judged_by(_null)·chk_insp_gradcam: 값이 채워져 있어 통과
--   chk_insp_auto_pass·chk_insp_review·chk_insp_recheck_rule: AUTO_PASS·REVIEW 전용이라 해당 없음 (재확인 규칙은 AUTO_PASS만)
--   chk_insp_reason_review_only·chk_insp_reason_defect: 사유 NULL이고 REVIEW가 아니라 통과
--   chk_insp_policy_snapshot·chk_insp_policy_ready_snapshot: 정책·통과 기준 스냅숏을 함께 기록하므로 통과
--   chk_insp_manual: 수동 판정 건은 REVIEW만이라 AUTO_FAIL이 될 수 없음

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
