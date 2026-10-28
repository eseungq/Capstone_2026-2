-- V5: 데이터 무결성 제약 보강 (김남균 DB, 2026-10-28)
-- 기준: API 계약 v4 3·4·6·9장, 명세서 4.3 개정 문안(10/28), V1·V3·V4 스키마
-- 대상: MySQL 8.0.19 이상 (DROP CHECK 사용). 백엔드 docker compose의 MySQL 8.4 기준
--
-- 적용 전 반드시 V5_precheck.sql을 실행해 위반 행이 0건인지 확인할 것.
--   MySQL DDL은 트랜잭션으로 묶이지 않아, 중간에 실패하면 앞 문장만 적용된 채 Flyway가 실패 처리한다.
--   개발 DB에 위반 행이 있으면 docker compose down -v로 초기화하는 쪽이 간단하다.
--
-- 상태: MySQL 8.0.46에서 V1~V4·seed-dev 위에 적용, 위반 테스트 26건 거부 확인 (10/28 이승규)
-- 10/28 수정(이승규): gradcam_status에 NO_ACTIVATION 추가, FAILED면 predicted_quality NULL
-- [확인 필요] 표시는 백엔드 저장 방식과 맞는지 이승규 팀원 확인이 필요한 제약

-- =====================================================================
-- 1) 복합 FK: 검사의 부품–검사항목, 정책의 모델–검사항목 일치 (계약 9장 "복합 FK 유지")
-- =====================================================================
ALTER TABLE inspection_item
    ADD CONSTRAINT uq_item_id_part UNIQUE (id, part_id);

ALTER TABLE ai_model
    ADD CONSTRAINT uq_model_id_item UNIQUE (id, item_id);

ALTER TABLE inspection
    ADD CONSTRAINT fk_insp_item_part FOREIGN KEY (item_id, part_id) REFERENCES inspection_item (id, part_id);

ALTER TABLE automation_policy
    ADD CONSTRAINT fk_policy_model_item FOREIGN KEY (model_id, item_id) REFERENCES ai_model (id, item_id);

-- =====================================================================
-- 2) active 유일성: 지금은 서비스에서만 보장 → DB에서도 보장
--    비활성 행은 생성 컬럼이 NULL이라 UNIQUE에 걸리지 않음
-- =====================================================================
ALTER TABLE ai_model
    ADD COLUMN active_item_key CHAR(36)
        GENERATED ALWAYS AS (CASE WHEN active = TRUE THEN item_id ELSE NULL END) STORED,
    ADD CONSTRAINT uq_model_active_item UNIQUE (active_item_key);          -- 검사항목당 active 모델 1개

ALTER TABLE automation_policy
    ADD COLUMN active_model_key CHAR(36)
        GENERATED ALWAYS AS (CASE WHEN active = TRUE THEN model_id ELSE NULL END) STORED,
    ADD CONSTRAINT uq_policy_active_model UNIQUE (active_model_key);       -- 모델당 active 정책 1개

-- =====================================================================
-- 3) inspection: 허용값·값 범위
-- =====================================================================
ALTER TABLE inspection
    ADD CONSTRAINT chk_insp_values CHECK (
            (predicted_quality IS NULL OR predicted_quality IN ('GOOD', 'DEFECT'))
        AND (recommended_action IS NULL OR recommended_action IN ('AUTO_PASS', 'REVIEW'))
        AND (final_judgement IS NULL OR final_judgement IN ('PASS', 'FAIL'))
        AND (judged_by IS NULL OR judged_by IN ('SYSTEM', 'WORKER'))
        AND (review_reason IS NULL OR review_reason IN
                ('DEFECT_PREDICTED', 'NO_ACTIVE_POLICY', 'CALIBRATION_UNAVAILABLE', 'ABOVE_THRESHOLD'))
        AND (gradcam_status IS NULL OR gradcam_status IN ('GENERATED', 'NOT_REQUIRED', 'FAILED', 'NO_ACTIVATION'))
        AND source IN ('DEVICE', 'ADMIN', 'RETRY')),
    ADD CONSTRAINT chk_insp_prob_range CHECK (
            (raw_defect_probability IS NULL OR (raw_defect_probability >= 0 AND raw_defect_probability <= 1))
        AND (calibrated_defect_probability IS NULL
             OR (calibrated_defect_probability >= 0 AND calibrated_defect_probability <= 1))
        AND (pass_threshold_applied IS NULL OR (pass_threshold_applied >= 0 AND pass_threshold_applied <= 1)));

-- =====================================================================
-- 4) inspection: 상태별 값 규칙
--    CHECK는 결과가 NULL이면 통과하므로 비교 앞에 IS NOT NULL을 둔다
-- =====================================================================
ALTER TABLE inspection
    -- 접수·분석 중: 예측·판정·완료 시각·Grad-CAM 상태 없음
    ADD CONSTRAINT chk_insp_pending CHECK (status NOT IN ('RECEIVED', 'ANALYZING') OR (
            predicted_quality IS NULL AND raw_defect_probability IS NULL
        AND recommended_action IS NULL AND final_judgement IS NULL AND judged_by IS NULL
        AND review_reason IS NULL AND gradcam_status IS NULL AND completed_at IS NULL)),
    -- 분석 완료: 보정 전 점수·완료 시각·Grad-CAM 상태 필수, 오류 없음
    ADD CONSTRAINT chk_insp_completed_v5 CHECK (status <> 'COMPLETED' OR (
            raw_defect_probability IS NOT NULL AND completed_at IS NOT NULL
        AND gradcam_status IS NOT NULL AND error_code IS NULL)),
    -- 분석 실패: 오류 코드·확정 시각 필수, 예측·판정 관련 값 없음
    --   (백엔드 확인 10/28: 실패 시 completed_at 기록함, AI 응답 검증 실패 시 predicted_quality 저장 안 함)
    ADD CONSTRAINT chk_insp_failed_v5 CHECK (status <> 'FAILED' OR (
            error_code IS NOT NULL AND completed_at IS NOT NULL AND predicted_quality IS NULL
        AND judged_by IS NULL AND review_reason IS NULL AND gradcam_status IS NULL));

-- =====================================================================
-- 5) inspection: AUTO_PASS 조건 강화 (V4 제약을 교체)
--    V4는 final = PASS, judged_by = SYSTEM만 검사. DEFECT 예측 AUTO_PASS를 막지 못함
-- =====================================================================
ALTER TABLE inspection DROP CHECK chk_insp_auto_pass;

ALTER TABLE inspection
    ADD CONSTRAINT chk_insp_auto_pass CHECK (recommended_action IS NULL OR recommended_action <> 'AUTO_PASS' OR (
            predicted_quality IS NOT NULL AND predicted_quality = 'GOOD'
        AND automation_policy_ready = TRUE AND policy_id IS NOT NULL
        AND calibrated_defect_probability IS NOT NULL AND pass_threshold_applied IS NOT NULL
        AND calibrated_defect_probability <= pass_threshold_applied
        AND final_judgement IS NOT NULL AND final_judgement = 'PASS'
        AND judged_by IS NOT NULL AND judged_by = 'SYSTEM'
        AND review_reason IS NULL));

-- =====================================================================
-- 6) inspection: REVIEW 사유와 값의 일관성 (계약 4장 우선순위)
-- =====================================================================
ALTER TABLE inspection
    -- 사유는 REVIEW일 때만
    ADD CONSTRAINT chk_insp_reason_review_only CHECK (review_reason IS NULL
        OR (recommended_action IS NOT NULL AND recommended_action = 'REVIEW')),
    -- DEFECT 예측 REVIEW는 사유가 DEFECT_PREDICTED (우선순위 1), 반대로 DEFECT_PREDICTED는 DEFECT 예측
    ADD CONSTRAINT chk_insp_reason_defect CHECK (
            (recommended_action IS NULL OR recommended_action <> 'REVIEW'
             OR predicted_quality IS NULL OR predicted_quality <> 'DEFECT'
             OR (review_reason IS NOT NULL AND review_reason = 'DEFECT_PREDICTED'))
        AND (review_reason IS NULL OR review_reason <> 'DEFECT_PREDICTED'
             OR (predicted_quality IS NOT NULL AND predicted_quality = 'DEFECT'))),
    -- NO_ACTIVE_POLICY → 정책 준비 안 됨
    ADD CONSTRAINT chk_insp_reason_no_policy CHECK (review_reason IS NULL OR review_reason <> 'NO_ACTIVE_POLICY'
        OR automation_policy_ready = FALSE),
    -- CALIBRATION_UNAVAILABLE → 보정 확률 없음
    ADD CONSTRAINT chk_insp_reason_calibration CHECK (review_reason IS NULL OR review_reason <> 'CALIBRATION_UNAVAILABLE'
        OR calibrated_defect_probability IS NULL),
    -- ABOVE_THRESHOLD → 준비된 정책, 보정 확률 > 기준치
    ADD CONSTRAINT chk_insp_reason_above CHECK (review_reason IS NULL OR review_reason <> 'ABOVE_THRESHOLD' OR (
            automation_policy_ready = TRUE
        AND calibrated_defect_probability IS NOT NULL AND pass_threshold_applied IS NOT NULL
        AND calibrated_defect_probability > pass_threshold_applied));

-- =====================================================================
-- 7) inspection: 판정 주체·Grad-CAM·보정기·정책 스냅숏
-- =====================================================================
ALTER TABLE inspection
    -- 최종 판정이 없으면 판정 주체도 없음 (V4 chk_insp_judged_by의 반대 방향)
    ADD CONSTRAINT chk_insp_judged_by_null CHECK (judged_by IS NULL OR final_judgement IS NOT NULL),
    -- Grad-CAM 상태: GOOD 예측은 NOT_REQUIRED, DEFECT 예측은 GENERATED·FAILED·NO_ACTIVATION
    -- NO_ACTIVATION: 계산 성공·위치별 강조 반응 없음(0맵·상수맵), 이미지 행 없음 (10/28 AI·모바일·DB 합의)
    ADD CONSTRAINT chk_insp_gradcam CHECK (gradcam_status IS NULL OR (predicted_quality IS NOT NULL AND (
            (predicted_quality = 'GOOD' AND gradcam_status = 'NOT_REQUIRED')
         OR (predicted_quality = 'DEFECT' AND gradcam_status IN ('GENERATED', 'FAILED', 'NO_ACTIVATION'))))),
    -- 분석 완료 건: 보정 확률과 보정기 버전은 함께 있거나 함께 없음 (계약 7.2)
    ADD CONSTRAINT chk_insp_calibrator_pair CHECK (status <> 'COMPLETED'
        OR (calibrated_defect_probability IS NULL AND calibrator_version IS NULL)
        OR (calibrated_defect_probability IS NOT NULL AND calibrator_version IS NOT NULL)),
    -- 정책 준비 안 됨 → 적용 정책·기준치 스냅숏 없음
    ADD CONSTRAINT chk_insp_policy_snapshot CHECK (automation_policy_ready = TRUE
        OR (policy_id IS NULL AND pass_threshold_applied IS NULL)),
    -- 분석 완료 + 정책 준비됨 → 적용 정책·기준치 스냅숏 필수  [확인 필요: DEFECT 예측일 때도 정책을 기록하는지]
    ADD CONSTRAINT chk_insp_policy_ready_snapshot CHECK (status <> 'COMPLETED' OR automation_policy_ready = FALSE
        OR (policy_id IS NOT NULL AND pass_threshold_applied IS NOT NULL));

-- =====================================================================
-- 8) automation_policy: 값 범위·ready·active
-- =====================================================================
ALTER TABLE automation_policy
    ADD CONSTRAINT chk_policy_prob_range CHECK (
            (pass_threshold IS NULL OR (pass_threshold >= 0 AND pass_threshold <= 1))
        AND (validated_min IS NULL OR (validated_min >= 0 AND validated_min <= 1))
        AND (validated_max IS NULL OR (validated_max >= 0 AND validated_max <= 1))
        AND (target_miss_rate IS NULL OR (target_miss_rate >= 0 AND target_miss_rate <= 1))),
    ADD CONSTRAINT chk_policy_valid_order CHECK (validated_min IS NULL OR validated_max IS NULL
        OR validated_min <= validated_max),
    -- ready 정책은 기준치·검증 범위·보정기 버전이 모두 있어야 함 (명세서 8.1 "ready 시 NOT NULL")
    ADD CONSTRAINT chk_policy_ready_values CHECK (ready = FALSE OR (
            pass_threshold IS NOT NULL AND validated_min IS NOT NULL AND validated_max IS NOT NULL
        AND calibrator_version IS NOT NULL)),
    -- 적용 중이면 적용 시작 시각 필수
    ADD CONSTRAINT chk_policy_active_at CHECK (active = FALSE OR activated_at IS NOT NULL);

-- =====================================================================
-- 9) 나머지 테이블: 허용값·값 범위
-- =====================================================================
ALTER TABLE worker_confirmation
    ADD CONSTRAINT chk_confirm_judgement CHECK (final_judgement IN ('PASS', 'FAIL'));

ALTER TABLE image_storage
    ADD CONSTRAINT chk_image_size CHECK (width > 0 AND height > 0 AND size_bytes > 0),
    ADD CONSTRAINT chk_image_exif CHECK (exif_orientation IS NULL OR (exif_orientation >= 1 AND exif_orientation <= 8));
