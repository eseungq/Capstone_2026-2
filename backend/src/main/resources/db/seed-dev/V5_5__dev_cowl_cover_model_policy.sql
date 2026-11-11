-- 개발용: 카울커버 통합 모델과 시연 정책 (AI 김도현 11/11 전달)
-- AI 서버는 8778. 백엔드에서 APP_AI_PARTBASEURLS_COWL_COVER로 연결 (backend/README.md "실제 AI 연결")
-- 검사항목은 프레임과 같이 통합 모델 1개라 UNIFIED (코드표 TBD-04 결정 전 임시)
INSERT INTO inspection_item (id, part_id, item_code, name)
SELECT UUID(), id, 'UNIFIED', '통합 불량' FROM part WHERE part_code = 'COWL_COVER';

INSERT INTO ai_model (id, item_id, model_version, pipeline_config_json, checksum, metrics_json,
                      patch_inspection_supported, active, calibrator_version, created_at)
SELECT UUID(), i.id, 'cowl-cover-unified-swin-tiny-e08-458a07d46453-dev',
       JSON_OBJECT('backbone', 'swin-tiny', 'checkpoint', '통합 e08', 'cam', 'LayerCAM',
                   'note', 'AI 11/11 전달. 보정기 cowl-unified-e08-temperature-2d80fc926685-demo'),
       '458a07d46453', NULL,
       FALSE, TRUE, 'cowl-unified-e08-temperature-2d80fc926685-demo', NOW(6)
FROM inspection_item i JOIN part p ON p.id = i.part_id
WHERE p.part_code = 'COWL_COVER' AND i.item_code = 'UNIFIED';

-- 시연 정책: 기준치 1.63%, 검증 범위 1.00~1.63%. 사전에 고정한 기준을 평가 사진에 적용한 값이며 운영 기준 아님
-- 조정 범위는 기존 점수를 다시 비교해 정한 시연용 값. ready·비활성으로 등록 후 관리자 API로 적용
INSERT INTO automation_policy (id, model_id, item_id, calibrator_version, policy_version, target_miss_rate,
                               pass_threshold, validated_min, validated_max, metrics_json, ready, active,
                               created_at, activated_at)
SELECT UUID(), m.id, m.item_id, 'cowl-unified-e08-temperature-2d80fc926685-demo', 'cowl-e08-demo-0163', NULL,
       0.016300, 0.010000, 0.016300,
       JSON_OBJECT('note', '카울커버 e08 캡스톤 시연 기준. 1.63%를 사전 고정해 평가 사진에 적용. 조정 범위는 기존 점수 재비교로 정한 시연용 값',
                   'sampleCount', 2531, 'normalAutoPass', '109/1250', 'defectAutoPass', '0/1281'),
       TRUE, FALSE, NOW(6), NULL
FROM ai_model m WHERE m.model_version = 'cowl-cover-unified-swin-tiny-e08-458a07d46453-dev';
