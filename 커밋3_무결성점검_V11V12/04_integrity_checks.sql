-- 테이블 간 무결성 점검 (CHECK로 막을 수 없는 규칙). 정상이면 모든 결과가 0건.
-- V1~V12 스키마 명칭 기준 (11/11 수동 판정 I13·I14, 11/20 표본 재확인 I15~I21, 11/21 I19·I20 보강·I22 추가, 11/24 일괄 FAIL·판정 확인 요청 I23~I29). 개발 DB에서 수시로 실행해 백엔드 저장 로직을 점검한다.

-- I1. REVIEW 확정 건인데 작업자 확인 기록이 없음
SELECT 'I1' AS rule_name, i.id, i.inspection_no FROM inspection i
LEFT JOIN worker_confirmation w ON w.inspection_id = i.id
WHERE i.recommended_action = 'REVIEW' AND i.final_judgement IS NOT NULL AND w.id IS NULL;

-- I2. 작업자 확인 값과 검사의 최종 판정·판정 주체가 다름
SELECT 'I2' AS rule_name, i.id, i.inspection_no FROM inspection i
JOIN worker_confirmation w ON w.inspection_id = i.id
WHERE i.final_judgement IS NULL OR i.final_judgement <> w.final_judgement
   OR i.judged_by IS NULL OR i.judged_by <> 'WORKER';

-- I3. REVIEW가 아닌 검사에 작업자 확인 기록이 있음 (AUTO_PASS를 작업자 확인으로 기록한 경우 등)
SELECT 'I3' AS rule_name, i.id, i.inspection_no FROM inspection i
JOIN worker_confirmation w ON w.inspection_id = i.id
WHERE i.recommended_action IS NULL OR i.recommended_action <> 'REVIEW';

-- I4. 원본 이미지가 없는 검사
SELECT 'I4' AS rule_name, i.id, i.inspection_no FROM inspection i
LEFT JOIN image_storage img ON img.inspection_id = i.id AND img.image_type = 'ORIGINAL'
WHERE img.id IS NULL;

-- I5. gradcam_status = GENERATED인데 Grad-CAM 이미지 행이 없음
SELECT 'I5' AS rule_name, i.id, i.inspection_no FROM inspection i
LEFT JOIN image_storage img ON img.inspection_id = i.id AND img.image_type = 'GRADCAM'
WHERE i.gradcam_status = 'GENERATED' AND img.id IS NULL;

-- I6. Grad-CAM 이미지 행이 있는데 gradcam_status가 GENERATED가 아님 (NOT_REQUIRED·FAILED·NO_ACTIVATION은 이미지 행 없음)
SELECT 'I6' AS rule_name, i.id, i.inspection_no FROM inspection i
JOIN image_storage img ON img.inspection_id = i.id AND img.image_type = 'GRADCAM'
WHERE i.gradcam_status IS NULL OR i.gradcam_status <> 'GENERATED';

-- I7. 재검사·수동 판정 원본이 FAILED가 아님 (11/11 수동 판정 포함)
SELECT 'I7' AS rule_name, r.id, r.inspection_no FROM inspection r
JOIN inspection o ON o.id = r.retry_of_inspection_id
WHERE o.status <> 'FAILED';

-- I8. source(RETRY·MANUAL)와 retry_of_inspection_id가 서로 맞지 않음 (11/11 MANUAL 추가)
SELECT 'I8' AS rule_name, i.id, i.inspection_no FROM inspection i
WHERE (i.source IN ('RETRY', 'MANUAL') AND i.retry_of_inspection_id IS NULL)
   OR (i.source NOT IN ('RETRY', 'MANUAL') AND i.retry_of_inspection_id IS NOT NULL);

-- I9. 재검사·수동 판정 건의 원본 이미지가 원래 검사의 원본과 다른 파일을 가리킴
SELECT 'I9' AS rule_name, r.id, r.inspection_no FROM inspection r
JOIN image_storage ri ON ri.inspection_id = r.id AND ri.image_type = 'ORIGINAL'
JOIN image_storage oi ON oi.inspection_id = r.retry_of_inspection_id AND oi.image_type = 'ORIGINAL'
WHERE ri.storage_uri <> oi.storage_uri;

-- I10. 검사에 기록된 정책이 그 검사의 모델·보정기 버전과 맞지 않음 (계약 4장 조건 3)
SELECT 'I10' AS rule_name, i.id, i.inspection_no FROM inspection i
JOIN automation_policy p ON p.id = i.policy_id
WHERE p.model_id <> i.model_id
   OR (i.recommended_action = 'AUTO_PASS'
       AND (i.calibrator_version IS NULL OR p.calibrator_version IS NULL OR p.calibrator_version <> i.calibrator_version));

-- I11. AUTO_PASS 건의 기준치 스냅숏이 적용 정책의 기준치와 다름 (판정 시점 값 보존 확인)
SELECT 'I11' AS rule_name, i.id, i.inspection_no FROM inspection i
JOIN automation_policy p ON p.id = i.policy_id
WHERE i.recommended_action = 'AUTO_PASS' AND i.pass_threshold_applied <> p.pass_threshold;

-- I12. 적용 중인 정책의 모델이 비활성 상태
SELECT 'I12' AS rule_name, p.id, p.policy_version FROM automation_policy p
JOIN ai_model m ON m.id = p.model_id
WHERE p.active = TRUE AND m.active = FALSE;

-- I13. 수동 판정 건(MANUAL)이 원래 FAILED와 부품·검사항목·모델이 다름 (11/11, V6)
SELECT 'I13' AS rule_name, m.id, m.inspection_no FROM inspection m
JOIN inspection o ON o.id = m.retry_of_inspection_id
WHERE m.source = 'MANUAL'
  AND (m.part_id <> o.part_id OR m.item_id <> o.item_id OR m.model_id <> o.model_id);

-- I14. 수동 판정 건이 판정됐는데 판정 주체가 작업자가 아니거나 작업자 확인 기록이 없음 (11/11, V6)
SELECT 'I14' AS rule_name, m.id, m.inspection_no FROM inspection m
LEFT JOIN worker_confirmation w ON w.inspection_id = m.id
WHERE m.source = 'MANUAL' AND m.final_judgement IS NOT NULL
  AND (m.judged_by IS NULL OR m.judged_by <> 'WORKER' OR w.id IS NULL);

-- ===================== 표본 재확인 (V8·V9, 11/20) =====================
-- 화면 체류 시간의 first_opened_at은 기기 시계라 서버 시각과 비교하지 않는다.

-- I15. 재확인 결정 행의 대상 검사가 AUTO_PASS·PASS·SYSTEM이 아님
SELECT 'I15' AS rule_name, i.id, i.inspection_no FROM auto_pass_recheck r
JOIN inspection i ON i.id = r.inspection_id
WHERE COALESCE(i.recommended_action, '') <> 'AUTO_PASS'
   OR COALESCE(i.final_judgement, '') <> 'PASS' OR COALESCE(i.judged_by, '') <> 'SYSTEM';

-- I16. 재확인자가 WORKER가 아님
SELECT 'I16' AS rule_name, i.id, i.inspection_no FROM auto_pass_recheck r
JOIN inspection i ON i.id = r.inspection_id
JOIN users u ON u.id = r.rechecked_by
WHERE u.role <> 'WORKER';

-- I17. 재확인 FAIL "확인함"을 남긴 사람이 ADMIN이 아님
SELECT 'I17' AS rule_name, i.id, i.inspection_no FROM auto_pass_recheck r
JOIN inspection i ON i.id = r.inspection_id
JOIN users u ON u.id = r.acknowledged_by
WHERE u.role <> 'ADMIN';

-- I18. 재확인 규칙(recheck_rule_id)이 있는 검사가 AUTO_PASS·PASS·SYSTEM이 아님
--      (V9 chk_insp_recheck_rule은 recommended_action이 NULL이면 통과하므로 여기서 함께 확인)
SELECT 'I18' AS rule_name, i.id, i.inspection_no FROM inspection i
WHERE i.recheck_rule_id IS NOT NULL
  AND (COALESCE(i.recommended_action, '') <> 'AUTO_PASS'
       OR COALESCE(i.final_judgement, '') <> 'PASS' OR COALESCE(i.judged_by, '') <> 'SYSTEM');

-- I19. 결정 행의 규칙(rule_id)과 검사의 판정 당시 규칙(recheck_rule_id)이 다름
--      한쪽만 NULL인 경우도 포함 (검사에는 규칙이 있는데 결정 행만 NULL 등). V8 시절 행은 둘 다 NULL이라 제외됨
SELECT 'I19' AS rule_name, i.id, i.inspection_no FROM auto_pass_recheck r
JOIN inspection i ON i.id = r.inspection_id
WHERE (r.rule_id IS NULL AND i.recheck_rule_id IS NOT NULL)
   OR (r.rule_id IS NOT NULL AND (i.recheck_rule_id IS NULL OR r.rule_id <> i.recheck_rule_id));

-- I20. 결정 행의 값이 규칙으로 다시 계산한 값과 다름 (rule_id 있는 행만)
--      r은 저장된 ratio가 아니라 검사의 보정 확률 ÷ 판정 당시 기준치로 다시 계산 (기준치 0 이하이면 1, 백엔드와 같음)
--      구간: r ≥ near_ratio → NEAR, ≥ mid_ratio → MID, 나머지 LOW (백엔드 RecheckRules와 같이 1e-9 여유)
--      확인: 저장된 ratio ≈ r, 구간, 구간 비율, 뽑힘 = 비율 > 0 이고 draw_value < 비율
SELECT 'I20' AS rule_name, c.id, c.inspection_no FROM (
    SELECT i.id, i.inspection_no, r.ratio, r.stratum, r.sampling_rate, r.sampled, r.draw_value,
           k.near_ratio, k.mid_ratio, k.near_rate, k.mid_rate, k.low_rate,
           CASE WHEN i.calibrated_defect_probability IS NULL OR i.pass_threshold_applied IS NULL THEN NULL
                WHEN i.pass_threshold_applied > 0 THEN i.calibrated_defect_probability / i.pass_threshold_applied
                ELSE 1 END AS r_calc
    FROM auto_pass_recheck r
    JOIN inspection i ON i.id = r.inspection_id
    JOIN recheck_rule k ON k.id = r.rule_id
) c
WHERE c.r_calc IS NULL
   OR ABS(c.ratio - c.r_calc) > 0.000001
   OR c.stratum <> CASE WHEN c.r_calc + 0.000000001 >= c.near_ratio THEN 'NEAR'
                        WHEN c.r_calc + 0.000000001 >= c.mid_ratio THEN 'MID' ELSE 'LOW' END
   OR c.sampling_rate <> CASE WHEN c.r_calc + 0.000000001 >= c.near_ratio THEN c.near_rate
                              WHEN c.r_calc + 0.000000001 >= c.mid_ratio THEN c.mid_rate ELSE c.low_rate END
   OR c.sampled <> (c.sampling_rate > 0 AND c.draw_value < c.sampling_rate);

-- I21. 시각 순서가 맞지 않음: 추출 결정이 검사 완료 전, 재확인이 추출 결정 전, 확인함이 재확인 전
SELECT 'I21' AS rule_name, i.id, i.inspection_no FROM auto_pass_recheck r
JOIN inspection i ON i.id = r.inspection_id
WHERE r.sampled_at < i.completed_at
   OR (r.rechecked_at IS NOT NULL AND r.rechecked_at < r.sampled_at)
   OR (r.acknowledged_at IS NOT NULL AND r.acknowledged_at < r.rechecked_at);

-- I22. 재확인 결과가 FAIL이 아닌데(PASS 또는 아직 없음) 관리자 확인함이 있음 (11/21)
--      V9 chk_recheck_ack는 result가 NULL이면 통과하므로 백엔드 V10에서 고칠 때까지 여기서 확인
SELECT 'I22' AS rule_name, i.id, i.inspection_no FROM auto_pass_recheck r
JOIN inspection i ON i.id = r.inspection_id
WHERE (r.acknowledged_by IS NOT NULL OR r.acknowledged_at IS NOT NULL OR r.acknowledge_note IS NOT NULL)
  AND (r.result IS NULL OR r.result <> 'FAIL');

-- ===================== 일괄 FAIL·판정 확인 요청 (V11·V12, 11/24) =====================
-- V11(worker_confirmation.batch_id)·V12(judgement_request)가 적용된 DB에서만 실행된다 (그 전에는 테이블·컬럼이 없어 오류)

-- I23. 일괄로 저장된 작업자 확인(batch_id 있음)인데 판정이 FAIL이 아님 (일괄은 FAIL만, 계약 6.7.1)
SELECT 'I23' AS rule_name, i.id, i.inspection_no FROM worker_confirmation w
JOIN inspection i ON i.id = w.inspection_id
WHERE w.batch_id IS NOT NULL AND w.final_judgement <> 'FAIL';

-- I24. 판정 확인 요청의 대상 검사가 시스템 판정(judged_by = SYSTEM, 최종 판정 있음)이 아님 (계약 6.12)
SELECT 'I24' AS rule_name, i.id, i.inspection_no FROM judgement_request q
JOIN inspection i ON i.id = q.inspection_id
WHERE COALESCE(i.judged_by, '') <> 'SYSTEM' OR i.final_judgement IS NULL;

-- I25. 요청자가 WORKER가 아님
SELECT 'I25' AS rule_name, i.id, i.inspection_no FROM judgement_request q
JOIN inspection i ON i.id = q.inspection_id
JOIN users u ON u.id = q.requested_by
WHERE u.role <> 'WORKER';

-- I26. 처리자가 ADMIN이 아님
SELECT 'I26' AS rule_name, i.id, i.inspection_no FROM judgement_request q
JOIN inspection i ON i.id = q.inspection_id
JOIN users u ON u.id = q.resolved_by
WHERE u.role <> 'ADMIN';

-- I27. 요청에 남긴 최초 판정(original_judgement)이 검사의 최초 판정과 다름 (정정해도 검사의 판정은 바뀌지 않음)
SELECT 'I27' AS rule_name, i.id, i.inspection_no FROM judgement_request q
JOIN inspection i ON i.id = q.inspection_id
WHERE i.final_judgement IS NULL OR q.original_judgement <> i.final_judgement;

-- I28. 요청 당시 현재 판정(current_judgement)이 맞지 않음
--      = 이 요청 전에 처리된 마지막 CORRECTED 요청의 claimed_judgement, 없으면 최초 판정
SELECT 'I28' AS rule_name, i.id, i.inspection_no FROM judgement_request q
JOIN inspection i ON i.id = q.inspection_id
WHERE q.current_judgement <> COALESCE(
        (SELECT p.claimed_judgement FROM judgement_request p
         WHERE p.inspection_id = q.inspection_id AND p.id <> q.id AND p.status = 'CORRECTED'
           AND p.resolved_at <= q.requested_at
         ORDER BY p.resolved_at DESC LIMIT 1),
        q.original_judgement);

-- I29. 요청 시각이 검사 판정(완료) 전
SELECT 'I29' AS rule_name, i.id, i.inspection_no FROM judgement_request q
JOIN inspection i ON i.id = q.inspection_id
WHERE i.completed_at IS NULL OR q.requested_at < i.completed_at;

-- ===================== 참고 (0건이 아니어도 오류는 아님) =====================
-- X1. 판정 당시 규칙이 있는데 1시간이 지나도 추출 결정 행이 없는 AUTO_PASS (RecheckSweeper 재처리 대상·누락 확인용)
SELECT 'X1' AS rule_name, i.id, i.inspection_no, i.completed_at FROM inspection i
LEFT JOIN auto_pass_recheck r ON r.inspection_id = i.id
--     DB 시각은 서울 시각으로 저장하므로(계약 2장) 기준 시각도 서울로 맞춤. NOW()는 MySQL 서버 시간대를 따라 UTC 서버면 9시간 어긋남
WHERE i.recheck_rule_id IS NOT NULL AND r.id IS NULL
  AND i.completed_at < UTC_TIMESTAMP(6) + INTERVAL 9 HOUR - INTERVAL 1 HOUR;
