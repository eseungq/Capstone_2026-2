-- 저장 흐름 예시 (구 03_write_paths v4판, 11/11 V6 수동 판정 W8-2, 11/20 V7~V9 표본 재확인 W3-2~W3-4 추가): 백엔드가 실행할 저장 쿼리 순서 예시 (V1~V9 명칭 기준, 김남균 DB, 2026-10-28)
-- 계약 v4 5장 처리 흐름을 SQL로 옮긴 것. 백엔드(JPA) 구현의 기준 순서로 참고하고, 그대로 쓸 필요는 없다.
--
-- 전제: V1~V9 + 개발 시드(V2 부품 DOOR, V3_1 계정, V4_1 mock 모델·example 정책 등) 적용된 개발 DB
--       (로컬 설치 스크립트 00_local_setup.sql 상태: 도어 활성 모델 Mock, 적용 정책 example-door-p1)
-- 값: 모두 예시 값. 검사 ID는 example-wp- 접두어, 이미지 키는 example/ 경로. 실제 검증 값 아님
-- 실행: 전체를 한 번에 실행하면 마지막 ROLLBACK으로 모두 되돌린다 (흐름 확인용).
--       결과를 남기고 싶으면 마지막 줄을 COMMIT으로 바꾼다.
-- 상태: 작성 완료 · MySQL 실행 미확인 (같은 순서를 SQLite 대체 실행으로 확인)

-- Workbench 안전 갱신 모드는 키 없는 UPDATE(W11)를 막으므로 이 세션에서만 끈다
SET SQL_SAFE_UPDATES = 0;

START TRANSACTION;

-- 공통으로 쓰는 ID (코드로 찾음)
SELECT id INTO @part_id   FROM part WHERE part_code = 'DOOR';
SELECT id INTO @item_id   FROM inspection_item WHERE part_id = @part_id AND item_code = 'UNIFIED';   -- V7 (TBD-04 확정)
SELECT id INTO @device_id FROM users WHERE login_id = 'device-door';
SELECT id INTO @worker_id FROM users WHERE login_id = 'worker01';
SELECT id INTO @admin_id  FROM users WHERE login_id = 'admin01';
SELECT id, calibrator_version INTO @model_id, @model_cal FROM ai_model WHERE item_id = @item_id AND active = TRUE;

-- =====================================================================
-- W1. 접수 (POST /inspections → 202): 번호 발급 + 검사 + 원본 이미지를 한 트랜잭션
--     원본 파일은 저장소에 먼저 쓰고, 이 트랜잭션이 실패하면 백엔드가 파일을 지운다
-- =====================================================================
SELECT last_val INTO @seq FROM inspection_no_seq WHERE name = 'INSPECTION' FOR UPDATE;   -- 행 잠금
UPDATE inspection_no_seq SET last_val = last_val + 1 WHERE name = 'INSPECTION';
SET @no1 = CONCAT('INS-', LPAD(@seq + 1, 6, '0'));

INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, line_code, model_id, status,
                        automation_policy_ready, client_request_id, trace_id, received_at, captured_at)
VALUES ('example-wp-0001', @no1, @device_id, 'DEVICE', @part_id, @item_id, 'LINE-A', @model_id, 'RECEIVED',
        FALSE, 'example-idem-0001', 'exampletrace0001', '2026-10-28 09:00:00', '2026-10-28 08:59:58');

INSERT INTO image_storage (id, inspection_id, image_type, storage_uri, content_type, size_bytes, width, height,
                           checksum, exif_orientation, created_at)
VALUES ('example-wp-img-0001', 'example-wp-0001', 'ORIGINAL', 'example/original/2026/10/28/example-wp-0001.jpg',
        'image/jpeg', 2400000, 4032, 3024, REPEAT('a', 64), 1, '2026-10-28 09:00:00');

-- 같은 Idempotency-Key 재전송: 새로 만들지 않고 기존 검사를 찾아 그대로 응답 (uq_insp_client_request가 최종 방어)
SELECT id, inspection_no, status FROM inspection
WHERE user_id = @device_id AND client_request_id = 'example-idem-0001';

-- =====================================================================
-- W2. 분석 시작: 직전 상태를 조건으로 건다. 영향 행 0이면 다른 스레드가 이미 처리한 것 → 중단
-- =====================================================================
UPDATE inspection SET status = 'ANALYZING', started_at = '2026-10-28 09:00:01'
WHERE id = 'example-wp-0001' AND status = 'RECEIVED';

-- =====================================================================
-- W3. 분석 완료 – AUTO_PASS (GOOD, 준비된 정책, 보정 확률 ≤ 기준치)
--     보정 확률은 적용 기준치의 60%로 둔다 (어느 정책이 적용돼 있어도 AUTO_PASS가 되도록)
--     표본 재확인 기능이 켜져 있으면 판정과 같은 트랜잭션에서 그때 규칙을 recheck_rule_id로 연결 (V9)
--     정책은 판정 시점에 조회하고, 기준치는 스냅숏으로 함께 저장
-- =====================================================================
SELECT id, pass_threshold INTO @policy_id, @threshold
FROM automation_policy
WHERE model_id = @model_id AND active = TRUE AND ready = TRUE AND calibrator_version = @model_cal;

-- 규칙은 값(경계·비율)과 시험 이름이 같으면 같은 행을 쓴다. 예시는 실제 시험과 섞이지 않게 시험 이름을 따로 둠
INSERT INTO recheck_rule (id, rule_version, trial_name, near_ratio, mid_ratio, near_rate, mid_rate, low_rate, created_at)
VALUES ('example-wp-rule-1', 'v1-b40-80-p100-30-10', 'example 흐름 확인', 0.800000, 0.400000, 1.000000, 0.300000, 0.100000,
        '2026-10-28 09:00:00');

UPDATE inspection SET
    status = 'COMPLETED', predicted_quality = 'GOOD',
    raw_defect_probability = 0.040000, calibrated_defect_probability = ROUND(@threshold * 0.6, 6), calibrator_version = @model_cal,
    automation_policy_ready = TRUE, policy_id = @policy_id, pass_threshold_applied = @threshold,
    recommended_action = 'AUTO_PASS', review_reason = NULL,
    final_judgement = 'PASS', judged_by = 'SYSTEM', recheck_rule_id = 'example-wp-rule-1',
    gradcam_status = 'NOT_REQUIRED', inference_time_ms = 850,
    ai_response_json = JSON_OBJECT('note', 'example'), completed_at = '2026-10-28 09:00:02'
WHERE id = 'example-wp-0001' AND status = 'ANALYZING';

-- =====================================================================
-- W3-2. 표본 추출 결정 (V8·V9, 계약 6.11): AUTO_PASS 저장 뒤 별도 단계. 뽑히지 않아도 1행 기록
--       r = 보정 확률 ÷ 판정 당시 기준치 → r ≥ 0.8 NEAR, ≥ 0.4 MID, 나머지 LOW → 구간 비율
--       draw_value는 백엔드가 검사 ID의 SHA-256으로 정하는 0~1 값. 여기서는 예시 값 0.120000
--       시스템 판정(PASS·SYSTEM)은 바꾸지 않는다
-- =====================================================================
INSERT INTO auto_pass_recheck (id, inspection_id, sampled, stratum, sampling_rate, sampled_at, rule_id, ratio, draw_value)
SELECT 'example-wp-recheck-0001', i.id,
       (s.rate > 0 AND 0.120000 < s.rate), s.stratum, s.rate, '2026-10-28 09:00:03', k.id, s.r, 0.120000
FROM inspection i
JOIN recheck_rule k ON k.id = i.recheck_rule_id
JOIN (SELECT i2.id AS insp_id,
             i2.calibrated_defect_probability / i2.pass_threshold_applied AS r,
             CASE WHEN i2.calibrated_defect_probability / i2.pass_threshold_applied + 0.000000001 >= k2.near_ratio THEN 'NEAR'
                  WHEN i2.calibrated_defect_probability / i2.pass_threshold_applied + 0.000000001 >= k2.mid_ratio THEN 'MID'
                  ELSE 'LOW' END AS stratum,
             CASE WHEN i2.calibrated_defect_probability / i2.pass_threshold_applied + 0.000000001 >= k2.near_ratio THEN k2.near_rate
                  WHEN i2.calibrated_defect_probability / i2.pass_threshold_applied + 0.000000001 >= k2.mid_ratio THEN k2.mid_rate
                  ELSE k2.low_rate END AS rate
      FROM inspection i2 JOIN recheck_rule k2 ON k2.id = i2.recheck_rule_id) s ON s.insp_id = i.id
WHERE i.id = 'example-wp-0001' AND i.recommended_action = 'AUTO_PASS';

-- W3-3. 재확인 결과 (POST /inspections/{id}/recheck, WORKER): 뽑힌 건만, 결과가 비어 있을 때만 (동시 제출 1건)
UPDATE auto_pass_recheck SET result = 'FAIL', comment = '예시 메모: 고정부 들뜸 의심',
       rechecked_by = @worker_id, rechecked_at = '2026-10-28 09:20:00',
       screen_dwell_ms = 18250, first_opened_at = '2026-10-28 09:19:40', open_count = 1
WHERE inspection_id = 'example-wp-0001' AND sampled = TRUE AND result IS NULL;

-- W3-4. 관리자 확인함 (POST /admin/rechecks/{id}/acknowledge, ADMIN): 재확인 FAIL만, 처음 기록 유지
UPDATE auto_pass_recheck SET acknowledged_by = @admin_id, acknowledged_at = '2026-10-28 09:30:00',
       acknowledge_note = '예시 메모: 라인 담당자에게 전달'
WHERE inspection_id = 'example-wp-0001' AND result = 'FAIL' AND acknowledged_by IS NULL;

-- 원래 판정은 그대로 (AUTO_PASS·PASS·SYSTEM), 재확인 결과는 따로
SELECT i.inspection_no, i.recommended_action, i.final_judgement, i.judged_by,
       r.stratum, r.sampling_rate, r.sampled, r.result, r.acknowledged_at
FROM inspection i JOIN auto_pass_recheck r ON r.inspection_id = i.id WHERE i.id = 'example-wp-0001';

-- =====================================================================
-- W4. 두 번째 검사: REVIEW (ABOVE_THRESHOLD) → W5 작업자 확인
--     접수·분석 시작은 W1·W2와 같은 순서 (번호 발급 포함)
-- =====================================================================
SELECT last_val INTO @seq FROM inspection_no_seq WHERE name = 'INSPECTION' FOR UPDATE;
UPDATE inspection_no_seq SET last_val = last_val + 1 WHERE name = 'INSPECTION';
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, line_code, model_id, status,
                        automation_policy_ready, received_at, captured_at)
VALUES ('example-wp-0002', CONCAT('INS-', LPAD(@seq + 1, 6, '0')), @device_id, 'DEVICE', @part_id, @item_id,
        'LINE-A', @model_id, 'RECEIVED', FALSE, '2026-10-28 09:01:00', '2026-10-28 09:00:58');
INSERT INTO image_storage (id, inspection_id, image_type, storage_uri, content_type, size_bytes, width, height, checksum, created_at)
VALUES ('example-wp-img-0002', 'example-wp-0002', 'ORIGINAL', 'example/original/2026/10/28/example-wp-0002.jpg',
        'image/jpeg', 2300000, 4032, 3024, REPEAT('b', 64), '2026-10-28 09:01:00');
UPDATE inspection SET status = 'ANALYZING', started_at = '2026-10-28 09:01:01'
WHERE id = 'example-wp-0002' AND status = 'RECEIVED';

UPDATE inspection SET
    status = 'COMPLETED', predicted_quality = 'GOOD',
    raw_defect_probability = 0.150000, calibrated_defect_probability = 0.120000, calibrator_version = @model_cal,
    automation_policy_ready = TRUE, policy_id = @policy_id, pass_threshold_applied = @threshold,
    recommended_action = 'REVIEW', review_reason = 'ABOVE_THRESHOLD',
    gradcam_status = 'NOT_REQUIRED', inference_time_ms = 870, completed_at = '2026-10-28 09:01:02'
WHERE id = 'example-wp-0002' AND status = 'ANALYZING';

-- W5. 작업자 확인 (PATCH /inspections/{id}/confirmation)
--     확인 기록 INSERT + 검사 판정 UPDATE를 한 트랜잭션. 동시 제출은 worker_confirmation.inspection_id UNIQUE가 막음
--     UPDATE 영향 행이 0이면(이미 확정·대상 아님) 트랜잭션 전체를 되돌린다
--     화면 체류 시간 3개는 선택, 셋 다 넣거나 셋 다 비움 (V9)
INSERT INTO worker_confirmation (id, inspection_id, worker_id, final_judgement, comment, confirmed_at,
                                 screen_dwell_ms, first_opened_at, open_count)
VALUES ('example-wp-conf-0002', 'example-wp-0002', @worker_id, 'PASS', '예시 메모: 반사광', '2026-10-28 09:05:00',
        9000, '2026-10-28 09:04:50', 1);

UPDATE inspection SET final_judgement = 'PASS', judged_by = 'WORKER'
WHERE id = 'example-wp-0002' AND status = 'COMPLETED' AND recommended_action = 'REVIEW' AND final_judgement IS NULL;

-- =====================================================================
-- W6. 세 번째 검사: DEFECT 예측 + Grad-CAM 생성
--     Grad-CAM 파일 저장에 실패하면 gradcam_status = 'FAILED', 이미지 행 없이 COMPLETED (검사 자체는 실패 아님)
--     계산은 됐지만 강조 반응이 없으면(0맵·상수맵) gradcam_status = 'NO_ACTIVATION', 이미지 행 없음 (10/28 합의)
-- =====================================================================
SELECT last_val INTO @seq FROM inspection_no_seq WHERE name = 'INSPECTION' FOR UPDATE;
UPDATE inspection_no_seq SET last_val = last_val + 1 WHERE name = 'INSPECTION';
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, line_code, model_id, status,
                        automation_policy_ready, received_at, captured_at)
VALUES ('example-wp-0003', CONCAT('INS-', LPAD(@seq + 1, 6, '0')), @device_id, 'DEVICE', @part_id, @item_id,
        'LINE-A', @model_id, 'RECEIVED', FALSE, '2026-10-28 09:02:00', '2026-10-28 09:01:58');
INSERT INTO image_storage (id, inspection_id, image_type, storage_uri, content_type, size_bytes, width, height, checksum, created_at)
VALUES ('example-wp-img-0003', 'example-wp-0003', 'ORIGINAL', 'example/original/2026/10/28/example-wp-0003.jpg',
        'image/jpeg', 2350000, 4032, 3024, REPEAT('c', 64), '2026-10-28 09:02:00');
UPDATE inspection SET status = 'ANALYZING', started_at = '2026-10-28 09:02:01'
WHERE id = 'example-wp-0003' AND status = 'RECEIVED';

INSERT INTO image_storage (id, inspection_id, image_type, storage_uri, content_type, size_bytes, width, height, checksum, created_at)
VALUES ('example-wp-cam-0003', 'example-wp-0003', 'GRADCAM', 'example/gradcam/2026/10/28/example-wp-0003.png',
        'image/png', 900000, 4032, 3024, REPEAT('d', 64), '2026-10-28 09:02:02');

UPDATE inspection SET
    status = 'COMPLETED', predicted_quality = 'DEFECT',
    raw_defect_probability = 0.910000, calibrated_defect_probability = 0.870000, calibrator_version = @model_cal,
    automation_policy_ready = TRUE, policy_id = @policy_id, pass_threshold_applied = @threshold,   -- DEFECT도 정책·기준치 기록 (10/28 확인)
    recommended_action = 'REVIEW', review_reason = 'DEFECT_PREDICTED',
    gradcam_status = 'GENERATED', inference_time_ms = 1200, completed_at = '2026-10-28 09:02:03'
WHERE id = 'example-wp-0003' AND status = 'ANALYZING';

-- =====================================================================
-- W7. 네 번째 검사: 분석 실패 (AI_SERVER_TIMEOUT) → W8 재검사
-- =====================================================================
SELECT last_val INTO @seq FROM inspection_no_seq WHERE name = 'INSPECTION' FOR UPDATE;
UPDATE inspection_no_seq SET last_val = last_val + 1 WHERE name = 'INSPECTION';
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, line_code, model_id, status,
                        automation_policy_ready, received_at, captured_at, trace_id)
VALUES ('example-wp-0004', CONCAT('INS-', LPAD(@seq + 1, 6, '0')), @device_id, 'DEVICE', @part_id, @item_id,
        'LINE-A', @model_id, 'RECEIVED', FALSE, '2026-10-28 09:03:00', '2026-10-28 09:02:58', 'exampletrace0004');
INSERT INTO image_storage (id, inspection_id, image_type, storage_uri, content_type, size_bytes, width, height, checksum, created_at)
VALUES ('example-wp-img-0004', 'example-wp-0004', 'ORIGINAL', 'example/original/2026/10/28/example-wp-0004.jpg',
        'image/jpeg', 2380000, 4032, 3024, REPEAT('e', 64), '2026-10-28 09:03:00');
UPDATE inspection SET status = 'ANALYZING', started_at = '2026-10-28 09:03:01'
WHERE id = 'example-wp-0004' AND status = 'RECEIVED';

-- 실패 시 예측값(predicted_quality 등)은 저장하지 않는다 (AI_RESPONSE_INVALID 포함, 10/28 백엔드 확인)
UPDATE inspection SET status = 'FAILED', error_code = 'AI_SERVER_TIMEOUT',
       error_detail = 'example: 30초 초과', completed_at = '2026-10-28 09:03:31'   -- 실패 시 completed_at 기록 (10/28 확인)
WHERE id = 'example-wp-0004' AND status = 'ANALYZING';

-- 타임아웃 뒤 늦게 도착한 AI 결과: 직전 상태 조건 때문에 0행 갱신 (FAILED 유지)
UPDATE inspection SET status = 'COMPLETED'
WHERE id = 'example-wp-0004' AND status = 'ANALYZING';

-- W8. 재검사 (POST /inspections/{id}/retry): 원래 행은 그대로, 새 행 + 같은 원본 파일 참조
--     같은 FAILED를 두 번 재검사하면 uq_insp_retry_of로 거부
SELECT last_val INTO @seq FROM inspection_no_seq WHERE name = 'INSPECTION' FOR UPDATE;
UPDATE inspection_no_seq SET last_val = last_val + 1 WHERE name = 'INSPECTION';

INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, line_code, model_id, status,
                        automation_policy_ready, retry_of_inspection_id, received_at, captured_at)
SELECT 'example-wp-0005', CONCAT('INS-', LPAD(@seq + 1, 6, '0')), @admin_id, 'RETRY', o.part_id, o.item_id,
       o.line_code, @model_id, 'RECEIVED', FALSE, o.id, '2026-10-28 09:10:00', o.captured_at
FROM inspection o
WHERE o.id = 'example-wp-0004' AND o.status = 'FAILED';

INSERT INTO image_storage (id, inspection_id, image_type, storage_uri, content_type, size_bytes, width, height,
                           checksum, exif_orientation, created_at)
SELECT 'example-wp-img-0005', 'example-wp-0005', 'ORIGINAL', storage_uri, content_type, size_bytes, width, height,
       checksum, exif_orientation, '2026-10-28 09:10:00'
FROM image_storage WHERE inspection_id = 'example-wp-0004' AND image_type = 'ORIGINAL';

-- =====================================================================
-- W8-2. 수동 판정 전환 (V6, 11/11 B안): AI 무응답으로 FAILED → 원본 재사용한 새 검사(MANUAL) → 작업자 확인
--       원본 연결은 재검사와 같은 retry_of_inspection_id (UNIQUE) → FAILED 1건당 재검사 또는 수동 전환 중 1건만
-- =====================================================================
SELECT last_val INTO @seq FROM inspection_no_seq WHERE name = 'INSPECTION' FOR UPDATE;
UPDATE inspection_no_seq SET last_val = last_val + 1 WHERE name = 'INSPECTION';
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, line_code, model_id, status,
                        automation_policy_ready, received_at, captured_at)
VALUES ('example-wp-0006', CONCAT('INS-', LPAD(@seq + 1, 6, '0')), @device_id, 'DEVICE', @part_id, @item_id,
        'LINE-A', @model_id, 'RECEIVED', FALSE, '2026-10-28 09:11:00', '2026-10-28 09:10:58');
INSERT INTO image_storage (id, inspection_id, image_type, storage_uri, content_type, size_bytes, width, height, checksum, created_at)
VALUES ('example-wp-img-0006', 'example-wp-0006', 'ORIGINAL', 'example/original/2026/10/28/example-wp-0006.jpg',
        'image/jpeg', 2310000, 4032, 3024, REPEAT('f', 64), '2026-10-28 09:11:00');
UPDATE inspection SET status = 'ANALYZING', started_at = '2026-10-28 09:11:01'
WHERE id = 'example-wp-0006' AND status = 'RECEIVED';
UPDATE inspection SET status = 'FAILED', error_code = 'AI_SERVER_ERROR',
       error_detail = 'example: AI 서버 연결 실패', completed_at = '2026-10-28 09:11:02'
WHERE id = 'example-wp-0006' AND status = 'ANALYZING';

-- 전환 (POST /inspections/{id}/manual, WORKER): 새 검사는 바로 COMPLETED·REVIEW·AI_UNAVAILABLE, AI 결과·정책 값 없음
--   model_id는 필수 칸이라 원래 FAILED의 모델을 그대로 기록 (어떤 모델이 실패했는지 남김)
SELECT last_val INTO @seq FROM inspection_no_seq WHERE name = 'INSPECTION' FOR UPDATE;
UPDATE inspection_no_seq SET last_val = last_val + 1 WHERE name = 'INSPECTION';
INSERT INTO inspection (id, inspection_no, user_id, source, part_id, item_id, line_code, model_id, status,
                        automation_policy_ready, recommended_action, review_reason, retry_of_inspection_id,
                        received_at, captured_at, completed_at)
SELECT 'example-wp-0007', CONCAT('INS-', LPAD(@seq + 1, 6, '0')), @worker_id, 'MANUAL', o.part_id, o.item_id,
       o.line_code, o.model_id, 'COMPLETED', FALSE, 'REVIEW', 'AI_UNAVAILABLE', o.id,
       '2026-10-28 09:12:00', o.captured_at, '2026-10-28 09:12:00'
FROM inspection o
WHERE o.id = 'example-wp-0006' AND o.status = 'FAILED';

INSERT INTO image_storage (id, inspection_id, image_type, storage_uri, content_type, size_bytes, width, height,
                           checksum, exif_orientation, created_at)
SELECT 'example-wp-img-0007', 'example-wp-0007', 'ORIGINAL', storage_uri, content_type, size_bytes, width, height,
       checksum, exif_orientation, '2026-10-28 09:12:00'
FROM image_storage WHERE inspection_id = 'example-wp-0006' AND image_type = 'ORIGINAL';

-- 판정: 기존 작업자 확인(W5)과 같은 방식
INSERT INTO worker_confirmation (id, inspection_id, worker_id, final_judgement, comment, confirmed_at)
VALUES ('example-wp-conf-0007', 'example-wp-0007', @worker_id, 'PASS', '예시 메모: 육안 확인', '2026-10-28 09:13:00');
UPDATE inspection SET final_judgement = 'PASS', judged_by = 'WORKER'
WHERE id = 'example-wp-0007' AND status = 'COMPLETED' AND recommended_action = 'REVIEW' AND final_judgement IS NULL;

-- =====================================================================
-- W9. 기준 조정 (관리자): 기존 정책 행은 수정하지 않고 검증 범위 안에서 새 버전 생성
-- =====================================================================
INSERT INTO automation_policy (id, model_id, item_id, calibrator_version, policy_version, target_miss_rate,
                               pass_threshold, validated_min, validated_max, metrics_json, ready, active,
                               based_on_policy_id, created_at)
SELECT 'example-wp-policy-p2', p.model_id, p.item_id, p.calibrator_version, 'example-door-p2', NULL,
       0.040000, p.validated_min, p.validated_max, p.metrics_json, TRUE, FALSE,
       p.id, '2026-10-28 09:20:00'
FROM automation_policy p
WHERE p.id = @policy_id AND 0.040000 BETWEEN p.validated_min AND p.validated_max;

-- W10. 적용 전환: 기존 정책을 먼저 내리고 새 정책을 올린다 (순서를 바꾸면 uq_policy_active_model 위반)
UPDATE automation_policy SET active = FALSE WHERE id = @policy_id AND active = TRUE;
UPDATE automation_policy SET active = TRUE, activated_at = '2026-10-28 09:21:00'
WHERE id = 'example-wp-policy-p2' AND ready = TRUE;

-- 과거 검사의 정책·기준치 스냅숏은 그대로 (0.050000 유지)
SELECT inspection_no, policy_id, pass_threshold_applied FROM inspection WHERE id LIKE 'example-wp-%' ORDER BY received_at;

-- =====================================================================
-- W11. 서버 재시작 정리 (계약 5장 [제안])
--      RECEIVED는 다시 처리 대상으로 조회, ANALYZING은 결과를 알 수 없으므로 FAILED로 확정
-- =====================================================================
SELECT id FROM inspection WHERE status = 'RECEIVED' ORDER BY received_at;

UPDATE inspection SET status = 'FAILED', error_code = 'INTERNAL_SERVER_ERROR',
       error_detail = '서버 재시작으로 분석 결과 확인 불가', completed_at = NOW(6)
WHERE status = 'ANALYZING';

-- =====================================================================
-- 정리: 흐름 확인용이므로 되돌린다 (남기려면 COMMIT)
-- =====================================================================
ROLLBACK;
SET SQL_SAFE_UPDATES = 1;
