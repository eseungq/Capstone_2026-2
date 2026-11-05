-- 테이블 간 무결성 점검 (CHECK로 막을 수 없는 규칙). 정상이면 모든 결과가 0건.
-- V1·V3·V4·V5 스키마 명칭 기준. 개발 DB에서 수시로 실행해 백엔드 저장 로직을 점검한다.

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

-- I7. 재검사 원본이 FAILED가 아님
SELECT 'I7' AS rule_name, r.id, r.inspection_no FROM inspection r
JOIN inspection o ON o.id = r.retry_of_inspection_id
WHERE o.status <> 'FAILED';

-- I8. source = RETRY와 retry_of_inspection_id가 서로 맞지 않음
SELECT 'I8' AS rule_name, i.id, i.inspection_no FROM inspection i
WHERE (i.source = 'RETRY' AND i.retry_of_inspection_id IS NULL)
   OR (i.source <> 'RETRY' AND i.retry_of_inspection_id IS NOT NULL);

-- I9. 재검사 건의 원본 이미지가 원래 검사의 원본과 다른 파일을 가리킴
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
