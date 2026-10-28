-- 개발·시연용 Mock 모델과 예시 정책 (실제 검증 값 아님)
-- Mock 모델 버전은 mock-, 예시 정책 버전은 example- 접두어로 실제와 구분 (계약 v4 0.2)
INSERT INTO ai_model (id, item_id, model_version, pipeline_config_json, checksum, metrics_json,
                      patch_inspection_supported, active, calibrator_version, created_at)
SELECT UUID(), i.id, 'mock-door-swin-t-v1', JSON_OBJECT('note', 'Mock AI 서버용'), 'mock', NULL,
       FALSE, TRUE, 'mock-cal-v1', NOW(6)
FROM inspection_item i JOIN part p ON p.id = i.part_id
WHERE p.part_code = 'DOOR' AND i.item_code = 'SCRATCH';

INSERT INTO automation_policy (id, model_id, item_id, calibrator_version, policy_version, target_miss_rate,
                               pass_threshold, validated_min, validated_max, metrics_json, ready, active,
                               created_at, activated_at)
SELECT UUID(), m.id, m.item_id, 'mock-cal-v1', 'example-door-p1', NULL,
       0.050000, 0.020000, 0.080000, JSON_OBJECT('note', '예시 정책. 실제 AI 검증 결과가 아님', 'sampleCount', 0),
       TRUE, TRUE, NOW(6), NOW(6)
FROM ai_model m WHERE m.model_version = 'mock-door-swin-t-v1';
