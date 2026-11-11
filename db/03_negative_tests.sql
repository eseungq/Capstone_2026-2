-- V5 제약 위반 테스트: "-- EXPECT ERROR:" 아래 문장은 모두 거부되어야 정상.
-- 실행: V1~V5 적용된 DB에서 Workbench "오류 시 중지"를 끄고 전체 실행 (또는 mysql --force).
-- 11/05: N27(FAILED 예측값)·N28(GOOD+NO_ACTIVATION) 추가, DEFECT+NO_ACTIVATION 정상 행 추가
-- 11/11: V6 수동 판정 반영. N10 제약 이름 v6로 변경, 정상 수동 판정 행 추가, N29~N33 추가 (33건)
-- 테스트용 행은 v5t- 접두어로 따로 만들고, 마지막 ROLLBACK으로 모두 지운다. 기존 데이터는 건드리지 않는다.
-- 예상 오류: 3819(CHECK 위반), 1062(중복), 1452(외래키). [ ] 안은 걸려야 하는 제약 이름 (|는 그중 하나)

START TRANSACTION;

-- ---------------- 테스트용 기준 데이터 (이 문장들은 성공해야 함) ----------------
INSERT INTO users (id, login_id, password_hash, role, failed_login_count, locked, created_at) VALUES
 ('v5t-user-worker', 'v5t-worker', 'x', 'WORKER', 0, FALSE, '2026-10-28 10:00:00'),
 ('v5t-user-device', 'v5t-device', 'x', 'DEVICE', 0, FALSE, '2026-10-28 10:00:00');
INSERT INTO part (id, part_code, name) VALUES
 ('v5t-part-a', 'V5TEST-A', 'V5 테스트 부품 A'),
 ('v5t-part-b', 'V5TEST-B', 'V5 테스트 부품 B');
INSERT INTO inspection_item (id, part_id, item_code, name) VALUES
 ('v5t-item-a', 'v5t-part-a', 'APPEARANCE', '테스트 A'),
 ('v5t-item-b', 'v5t-part-b', 'APPEARANCE', '테스트 B');
INSERT INTO ai_model (id, item_id, model_version, pipeline_config_json, checksum, metrics_json,
                      patch_inspection_supported, active, calibrator_version, created_at) VALUES
 ('v5t-model-a', 'v5t-item-a', 'v5t-model-a', '{}', 'x', NULL, FALSE, TRUE, 'v5t-cal', '2026-10-28 10:00:00');
INSERT INTO automation_policy (id, model_id, item_id, calibrator_version, policy_version, target_miss_rate,
                               pass_threshold, validated_min, validated_max, metrics_json, ready, active,
                               created_at, activated_at) VALUES
 ('v5t-policy-a', 'v5t-model-a', 'v5t-item-a', 'v5t-cal', 'v5t-policy-a', NULL,
  0.050000, 0.020000, 0.080000, '{}', TRUE, TRUE, '2026-10-28 10:00:00', '2026-10-28 10:00:00');
-- 정상 FAILED 검사 1건 (재검사 테스트용)
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, model_id, status,
                        automation_policy_ready, error_code, received_at, completed_at) VALUES
 ('v5t-insp-failed', 'V5T-000001', 'v5t-user-device', 'DEVICE', 'v5t-part-a', 'v5t-item-a', 'v5t-model-a',
  'FAILED', FALSE, 'AI_SERVER_TIMEOUT', '2026-10-28 10:01:00', '2026-10-28 10:01:10');
-- 정상 DEFECT + NO_ACTIVATION 검사 1건 (10/28 합의: 강조 반응 없음은 허용, 이미지 행 없음)
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, model_id, policy_id, status, predicted_quality,
  raw_defect_probability, calibrated_defect_probability, calibrator_version, automation_policy_ready, pass_threshold_applied,
  recommended_action, review_reason, gradcam_status, received_at, completed_at)
VALUES ('v5t-insp-noact', 'V5T-000002', 'v5t-user-device', 'DEVICE', 'v5t-part-a', 'v5t-item-a', 'v5t-model-a', 'v5t-policy-a',
  'COMPLETED', 'DEFECT', 0.700000, 0.600000, 'v5t-cal', TRUE, 0.050000, 'REVIEW', 'DEFECT_PREDICTED', 'NO_ACTIVATION',
  '2026-10-28 10:01:20', '2026-10-28 10:01:22');
-- 정상 수동 판정 1건 (V6): 두 번째 FAILED → MANUAL 전환. AI 결과·정책 값 없이 완료
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, model_id, status,
                        automation_policy_ready, error_code, received_at, completed_at) VALUES
 ('v5t-insp-failed2', 'V5T-000003', 'v5t-user-device', 'DEVICE', 'v5t-part-a', 'v5t-item-a', 'v5t-model-a',
  'FAILED', FALSE, 'AI_SERVER_ERROR', '2026-10-28 10:01:30', '2026-10-28 10:01:31');
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, model_id, status,
                        automation_policy_ready, recommended_action, review_reason, retry_of_inspection_id,
                        received_at, completed_at) VALUES
 ('v5t-insp-manual', 'V5T-000004', 'v5t-user-worker', 'MANUAL', 'v5t-part-a', 'v5t-item-a', 'v5t-model-a',
  'COMPLETED', FALSE, 'REVIEW', 'AI_UNAVAILABLE', 'v5t-insp-failed2', '2026-10-28 10:01:40', '2026-10-28 10:01:40');

-- ---------------- 거부되어야 하는 문장 ----------------

-- EXPECT ERROR: N01 DEFECT 예측인데 AUTO_PASS [chk_insp_auto_pass]
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, model_id, policy_id, status, predicted_quality,
  raw_defect_probability, calibrated_defect_probability, calibrator_version, automation_policy_ready, pass_threshold_applied,
  recommended_action, final_judgement, judged_by, gradcam_status, received_at, completed_at)
VALUES ('v5t-n01', 'V5T-N01', 'v5t-user-device', 'DEVICE', 'v5t-part-a', 'v5t-item-a', 'v5t-model-a', 'v5t-policy-a', 'COMPLETED', 'DEFECT',
  0.600000, 0.010000, 'v5t-cal', TRUE, 0.050000, 'AUTO_PASS', 'PASS', 'SYSTEM', 'GENERATED', '2026-10-28 10:02:00', '2026-10-28 10:02:02');

-- EXPECT ERROR: N02 AUTO_PASS인데 보정 확률이 기준치 초과 [chk_insp_auto_pass]
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, model_id, policy_id, status, predicted_quality,
  raw_defect_probability, calibrated_defect_probability, calibrator_version, automation_policy_ready, pass_threshold_applied,
  recommended_action, final_judgement, judged_by, gradcam_status, received_at, completed_at)
VALUES ('v5t-n02', 'V5T-N02', 'v5t-user-device', 'DEVICE', 'v5t-part-a', 'v5t-item-a', 'v5t-model-a', 'v5t-policy-a', 'COMPLETED', 'GOOD',
  0.200000, 0.090000, 'v5t-cal', TRUE, 0.050000, 'AUTO_PASS', 'PASS', 'SYSTEM', 'NOT_REQUIRED', '2026-10-28 10:02:00', '2026-10-28 10:02:02');

-- EXPECT ERROR: N03 AUTO_PASS인데 정책 준비 안 됨 [chk_insp_auto_pass]
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, model_id, status, predicted_quality,
  raw_defect_probability, calibrated_defect_probability, calibrator_version, automation_policy_ready,
  recommended_action, final_judgement, judged_by, gradcam_status, received_at, completed_at)
VALUES ('v5t-n03', 'V5T-N03', 'v5t-user-device', 'DEVICE', 'v5t-part-a', 'v5t-item-a', 'v5t-model-a', 'COMPLETED', 'GOOD',
  0.020000, 0.010000, 'v5t-cal', FALSE, 'AUTO_PASS', 'PASS', 'SYSTEM', 'NOT_REQUIRED', '2026-10-28 10:02:00', '2026-10-28 10:02:02');

-- EXPECT ERROR: N04 DEFECT 예측 REVIEW인데 사유가 DEFECT_PREDICTED가 아님 [chk_insp_reason_defect]
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, model_id, policy_id, status, predicted_quality,
  raw_defect_probability, calibrated_defect_probability, calibrator_version, automation_policy_ready, pass_threshold_applied,
  recommended_action, review_reason, gradcam_status, received_at, completed_at)
VALUES ('v5t-n04', 'V5T-N04', 'v5t-user-device', 'DEVICE', 'v5t-part-a', 'v5t-item-a', 'v5t-model-a', 'v5t-policy-a', 'COMPLETED', 'DEFECT',
  0.900000, 0.800000, 'v5t-cal', TRUE, 0.050000, 'REVIEW', 'ABOVE_THRESHOLD', 'GENERATED', '2026-10-28 10:02:00', '2026-10-28 10:02:02');

-- EXPECT ERROR: N05 NO_ACTIVE_POLICY인데 정책 준비됨 [chk_insp_reason_no_policy]
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, model_id, policy_id, status, predicted_quality,
  raw_defect_probability, calibrated_defect_probability, calibrator_version, automation_policy_ready, pass_threshold_applied,
  recommended_action, review_reason, gradcam_status, received_at, completed_at)
VALUES ('v5t-n05', 'V5T-N05', 'v5t-user-device', 'DEVICE', 'v5t-part-a', 'v5t-item-a', 'v5t-model-a', 'v5t-policy-a', 'COMPLETED', 'GOOD',
  0.100000, 0.090000, 'v5t-cal', TRUE, 0.050000, 'REVIEW', 'NO_ACTIVE_POLICY', 'NOT_REQUIRED', '2026-10-28 10:02:00', '2026-10-28 10:02:02');

-- EXPECT ERROR: N06 ABOVE_THRESHOLD인데 보정 확률이 기준치 이하 [chk_insp_reason_above]
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, model_id, policy_id, status, predicted_quality,
  raw_defect_probability, calibrated_defect_probability, calibrator_version, automation_policy_ready, pass_threshold_applied,
  recommended_action, review_reason, gradcam_status, received_at, completed_at)
VALUES ('v5t-n06', 'V5T-N06', 'v5t-user-device', 'DEVICE', 'v5t-part-a', 'v5t-item-a', 'v5t-model-a', 'v5t-policy-a', 'COMPLETED', 'GOOD',
  0.030000, 0.020000, 'v5t-cal', TRUE, 0.050000, 'REVIEW', 'ABOVE_THRESHOLD', 'NOT_REQUIRED', '2026-10-28 10:02:00', '2026-10-28 10:02:02');

-- EXPECT ERROR: N07 CALIBRATION_UNAVAILABLE인데 보정 확률이 있음 [chk_insp_reason_calibration]
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, model_id, status, predicted_quality,
  raw_defect_probability, calibrated_defect_probability, calibrator_version, automation_policy_ready,
  recommended_action, review_reason, gradcam_status, received_at, completed_at)
VALUES ('v5t-n07', 'V5T-N07', 'v5t-user-device', 'DEVICE', 'v5t-part-a', 'v5t-item-a', 'v5t-model-a', 'COMPLETED', 'GOOD',
  0.100000, 0.090000, 'v5t-cal', FALSE, 'REVIEW', 'CALIBRATION_UNAVAILABLE', 'NOT_REQUIRED', '2026-10-28 10:02:00', '2026-10-28 10:02:02');

-- EXPECT ERROR: N08 AUTO_PASS인데 REVIEW 사유가 있음 [chk_insp_auto_pass|chk_insp_reason_review_only|chk_insp_reason_above]
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, model_id, policy_id, status, predicted_quality,
  raw_defect_probability, calibrated_defect_probability, calibrator_version, automation_policy_ready, pass_threshold_applied,
  recommended_action, review_reason, final_judgement, judged_by, gradcam_status, received_at, completed_at)
VALUES ('v5t-n08', 'V5T-N08', 'v5t-user-device', 'DEVICE', 'v5t-part-a', 'v5t-item-a', 'v5t-model-a', 'v5t-policy-a', 'COMPLETED', 'GOOD',
  0.020000, 0.010000, 'v5t-cal', TRUE, 0.050000, 'AUTO_PASS', 'ABOVE_THRESHOLD', 'PASS', 'SYSTEM', 'NOT_REQUIRED', '2026-10-28 10:02:00', '2026-10-28 10:02:02');

-- EXPECT ERROR: N09 GOOD 예측인데 Grad-CAM 상태가 GENERATED [chk_insp_gradcam]
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, model_id, status, predicted_quality,
  raw_defect_probability, automation_policy_ready, recommended_action, review_reason, gradcam_status, received_at, completed_at)
VALUES ('v5t-n09', 'V5T-N09', 'v5t-user-device', 'DEVICE', 'v5t-part-a', 'v5t-item-a', 'v5t-model-a', 'COMPLETED', 'GOOD',
  0.100000, FALSE, 'REVIEW', 'NO_ACTIVE_POLICY', 'GENERATED', '2026-10-28 10:02:00', '2026-10-28 10:02:02');

-- EXPECT ERROR: N10 분석 완료인데 Grad-CAM 상태 없음 [chk_insp_completed_v6]
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, model_id, status, predicted_quality,
  raw_defect_probability, automation_policy_ready, recommended_action, review_reason, received_at, completed_at)
VALUES ('v5t-n10', 'V5T-N10', 'v5t-user-device', 'DEVICE', 'v5t-part-a', 'v5t-item-a', 'v5t-model-a', 'COMPLETED', 'GOOD',
  0.100000, FALSE, 'REVIEW', 'NO_ACTIVE_POLICY', '2026-10-28 10:02:00', '2026-10-28 10:02:02');

-- EXPECT ERROR: N11 보정 확률은 있는데 보정기 버전 없음 [chk_insp_calibrator_pair]
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, model_id, status, predicted_quality,
  raw_defect_probability, calibrated_defect_probability, automation_policy_ready, recommended_action, review_reason,
  gradcam_status, received_at, completed_at)
VALUES ('v5t-n11', 'V5T-N11', 'v5t-user-device', 'DEVICE', 'v5t-part-a', 'v5t-item-a', 'v5t-model-a', 'COMPLETED', 'GOOD',
  0.100000, 0.090000, FALSE, 'REVIEW', 'NO_ACTIVE_POLICY', 'NOT_REQUIRED', '2026-10-28 10:02:00', '2026-10-28 10:02:02');

-- EXPECT ERROR: N12 분석 중인데 예측값이 있음 [chk_insp_pending]
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, model_id, status, predicted_quality,
  automation_policy_ready, received_at)
VALUES ('v5t-n12', 'V5T-N12', 'v5t-user-device', 'DEVICE', 'v5t-part-a', 'v5t-item-a', 'v5t-model-a', 'ANALYZING', 'GOOD',
  FALSE, '2026-10-28 10:02:00');

-- EXPECT ERROR: N13 분석 실패인데 오류 코드 없음 [chk_insp_failed_v5]
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, model_id, status, automation_policy_ready,
  received_at, completed_at)
VALUES ('v5t-n13', 'V5T-N13', 'v5t-user-device', 'DEVICE', 'v5t-part-a', 'v5t-item-a', 'v5t-model-a', 'FAILED', FALSE,
  '2026-10-28 10:02:00', '2026-10-28 10:02:10');

-- EXPECT ERROR: N14 판정 주체만 있고 최종 판정 없음 [chk_insp_judged_by_null]
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, model_id, status, predicted_quality,
  raw_defect_probability, automation_policy_ready, recommended_action, review_reason, judged_by, gradcam_status,
  received_at, completed_at)
VALUES ('v5t-n14', 'V5T-N14', 'v5t-user-device', 'DEVICE', 'v5t-part-a', 'v5t-item-a', 'v5t-model-a', 'COMPLETED', 'GOOD',
  0.100000, FALSE, 'REVIEW', 'NO_ACTIVE_POLICY', 'WORKER', 'NOT_REQUIRED', '2026-10-28 10:02:00', '2026-10-28 10:02:02');

-- EXPECT ERROR: N15 정의되지 않은 접수 경로(source) [chk_insp_values]
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, model_id, status, automation_policy_ready, received_at)
VALUES ('v5t-n15', 'V5T-N15', 'v5t-user-device', 'APP', 'v5t-part-a', 'v5t-item-a', 'v5t-model-a', 'RECEIVED', FALSE, '2026-10-28 10:02:00');

-- EXPECT ERROR: N16 확률 범위 밖 (1.5) [chk_insp_prob_range]
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, model_id, status, predicted_quality,
  raw_defect_probability, automation_policy_ready, recommended_action, review_reason, gradcam_status, received_at, completed_at)
VALUES ('v5t-n16', 'V5T-N16', 'v5t-user-device', 'DEVICE', 'v5t-part-a', 'v5t-item-a', 'v5t-model-a', 'COMPLETED', 'DEFECT',
  1.500000, FALSE, 'REVIEW', 'DEFECT_PREDICTED', 'FAILED', '2026-10-28 10:02:00', '2026-10-28 10:02:02');

-- EXPECT ERROR: N17 부품과 검사항목이 서로 맞지 않음 (복합 FK) [fk_insp_item_part]
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, model_id, status, automation_policy_ready, received_at)
VALUES ('v5t-n17', 'V5T-N17', 'v5t-user-device', 'DEVICE', 'v5t-part-b', 'v5t-item-a', 'v5t-model-a', 'RECEIVED', FALSE, '2026-10-28 10:02:00');

-- EXPECT ERROR: N18 정책의 모델과 검사항목이 서로 맞지 않음 (복합 FK) [fk_policy_model_item]
INSERT INTO automation_policy (id, model_id, item_id, calibrator_version, policy_version, pass_threshold, validated_min,
  validated_max, metrics_json, ready, active, created_at)
VALUES ('v5t-n18', 'v5t-model-a', 'v5t-item-b', 'v5t-cal', 'v5t-n18', 0.05, 0.02, 0.08, '{}', TRUE, FALSE, '2026-10-28 10:02:00');

-- EXPECT ERROR: N19 같은 모델에 적용 중인 정책 2개 [uq_policy_active_model]
INSERT INTO automation_policy (id, model_id, item_id, calibrator_version, policy_version, pass_threshold, validated_min,
  validated_max, metrics_json, ready, active, created_at, activated_at)
VALUES ('v5t-n19', 'v5t-model-a', 'v5t-item-a', 'v5t-cal', 'v5t-n19', 0.04, 0.02, 0.08, '{}', TRUE, TRUE, '2026-10-28 10:02:00', '2026-10-28 10:02:00');

-- EXPECT ERROR: N20 같은 검사항목에 활성 모델 2개 [uq_model_active_item]
INSERT INTO ai_model (id, item_id, model_version, pipeline_config_json, checksum, patch_inspection_supported, active, created_at)
VALUES ('v5t-n20', 'v5t-item-a', 'v5t-n20', '{}', 'x', FALSE, TRUE, '2026-10-28 10:02:00');

-- EXPECT ERROR: N21 ready 정책인데 검증 범위 없음 [chk_policy_ready_values]
INSERT INTO automation_policy (id, model_id, item_id, calibrator_version, policy_version, pass_threshold, metrics_json,
  ready, active, created_at)
VALUES ('v5t-n21', 'v5t-model-a', 'v5t-item-a', 'v5t-cal', 'v5t-n21', 0.05, '{}', TRUE, FALSE, '2026-10-28 10:02:00');

-- EXPECT ERROR: N22 검증 범위 순서가 뒤집힘 (min > max) [chk_policy_valid_order]
INSERT INTO automation_policy (id, model_id, item_id, calibrator_version, policy_version, metrics_json, validated_min,
  validated_max, ready, active, created_at)
VALUES ('v5t-n22', 'v5t-model-a', 'v5t-item-a', 'v5t-cal', 'v5t-n22', '{}', 0.08, 0.02, FALSE, FALSE, '2026-10-28 10:02:00');

-- EXPECT ERROR: N23 적용 중인데 적용 시작 시각 없음 [chk_policy_active_at]
UPDATE automation_policy SET activated_at = NULL WHERE id = 'v5t-policy-a';

-- EXPECT ERROR: N24 같은 FAILED 검사를 두 번 재검사 (V4 UNIQUE 확인) [uq_insp_retry_of]
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, model_id, status, automation_policy_ready,
  retry_of_inspection_id, received_at)
VALUES ('v5t-n24a', 'V5T-N24A', 'v5t-user-worker', 'RETRY', 'v5t-part-a', 'v5t-item-a', 'v5t-model-a', 'RECEIVED', FALSE,
  'v5t-insp-failed', '2026-10-28 10:03:00'),
       ('v5t-n24b', 'V5T-N24B', 'v5t-user-worker', 'RETRY', 'v5t-part-a', 'v5t-item-a', 'v5t-model-a', 'RECEIVED', FALSE,
  'v5t-insp-failed', '2026-10-28 10:03:01');

-- EXPECT ERROR: N25 작업자 확인 판정값이 PASS·FAIL이 아님 [chk_confirm_judgement]
INSERT INTO worker_confirmation (id, inspection_id, worker_id, final_judgement, confirmed_at)
VALUES ('v5t-n25', 'v5t-insp-failed', 'v5t-user-worker', 'OK', '2026-10-28 10:04:00');

-- EXPECT ERROR: N26 이미지 크기 0 [chk_image_size]
INSERT INTO image_storage (id, inspection_id, image_type, storage_uri, content_type, size_bytes, width, height, checksum, created_at)
VALUES ('v5t-n26', 'v5t-insp-failed', 'ORIGINAL', 'original/v5t.jpg', 'image/jpeg', 100, 0, 3024, 'x', '2026-10-28 10:04:00');

-- EXPECT ERROR: N27 분석 실패인데 예측값이 있음 (10/28 백엔드 확인: AI_RESPONSE_INVALID도 저장 안 함) [chk_insp_failed_v5]
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, model_id, status, predicted_quality,
  automation_policy_ready, error_code, received_at, completed_at)
VALUES ('v5t-n27', 'V5T-N27', 'v5t-user-device', 'DEVICE', 'v5t-part-a', 'v5t-item-a', 'v5t-model-a', 'FAILED', 'GOOD',
  FALSE, 'AI_RESPONSE_INVALID', '2026-10-28 10:05:00', '2026-10-28 10:05:02');

-- EXPECT ERROR: N28 GOOD 예측인데 Grad-CAM 상태가 NO_ACTIVATION [chk_insp_gradcam]
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, model_id, status, predicted_quality,
  raw_defect_probability, automation_policy_ready, recommended_action, review_reason, gradcam_status, received_at, completed_at)
VALUES ('v5t-n28', 'V5T-N28', 'v5t-user-device', 'DEVICE', 'v5t-part-a', 'v5t-item-a', 'v5t-model-a', 'COMPLETED', 'GOOD',
  0.100000, FALSE, 'REVIEW', 'NO_ACTIVE_POLICY', 'NO_ACTIVATION', '2026-10-28 10:05:00', '2026-10-28 10:05:02');

-- ---------------- V6 수동 판정 (11/11) ----------------

-- EXPECT ERROR: N29 수동 판정 건에 AI 예측값이 있음 [chk_insp_manual]
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, model_id, status, predicted_quality,
  automation_policy_ready, recommended_action, review_reason, retry_of_inspection_id, received_at, completed_at)
VALUES ('v5t-n29', 'V5T-N29', 'v5t-user-worker', 'MANUAL', 'v5t-part-a', 'v5t-item-a', 'v5t-model-a', 'COMPLETED', 'GOOD',
  FALSE, 'REVIEW', 'AI_UNAVAILABLE', 'v5t-insp-failed', '2026-10-28 10:06:00', '2026-10-28 10:06:00');

-- EXPECT ERROR: N30 수동 판정 건에 원본 FAILED 연결 없음 [chk_insp_manual]
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, model_id, status,
  automation_policy_ready, recommended_action, review_reason, received_at, completed_at)
VALUES ('v5t-n30', 'V5T-N30', 'v5t-user-worker', 'MANUAL', 'v5t-part-a', 'v5t-item-a', 'v5t-model-a', 'COMPLETED',
  FALSE, 'REVIEW', 'AI_UNAVAILABLE', '2026-10-28 10:06:00', '2026-10-28 10:06:00');

-- EXPECT ERROR: N31 일반 검사(DEVICE)에 AI_UNAVAILABLE 사유 [chk_insp_reason_ai_unavailable]
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, model_id, status, predicted_quality,
  raw_defect_probability, automation_policy_ready, recommended_action, review_reason, gradcam_status, received_at, completed_at)
VALUES ('v5t-n31', 'V5T-N31', 'v5t-user-device', 'DEVICE', 'v5t-part-a', 'v5t-item-a', 'v5t-model-a', 'COMPLETED', 'GOOD',
  0.100000, FALSE, 'REVIEW', 'AI_UNAVAILABLE', 'NOT_REQUIRED', '2026-10-28 10:06:00', '2026-10-28 10:06:02');

-- EXPECT ERROR: N32 수동 전환한 FAILED를 다시 재검사 (재검사·수동 중 1건만) [uq_insp_retry_of]
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, model_id, status, automation_policy_ready,
  retry_of_inspection_id, received_at)
VALUES ('v5t-n32', 'V5T-N32', 'v5t-user-worker', 'RETRY', 'v5t-part-a', 'v5t-item-a', 'v5t-model-a', 'RECEIVED', FALSE,
  'v5t-insp-failed2', '2026-10-28 10:06:00');

-- EXPECT ERROR: N33 일반 검사(DEVICE)가 AI 예측 없이 완료 (V4 규칙이 V6 통합 후에도 유지되는지) [chk_insp_completed_v6]
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, model_id, status,
  automation_policy_ready, recommended_action, review_reason, received_at, completed_at)
VALUES ('v5t-n33', 'V5T-N33', 'v5t-user-device', 'DEVICE', 'v5t-part-a', 'v5t-item-a', 'v5t-model-a', 'COMPLETED',
  FALSE, 'REVIEW', 'NO_ACTIVE_POLICY', '2026-10-28 10:06:00', '2026-10-28 10:06:02');

-- ---------------- 정리 ----------------
ROLLBACK;
