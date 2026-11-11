-- 개발용: 프레임 통합 모델과 시연 정책 (AI 김도현 11/11 전달)
-- AI 서버는 도어(8771)와 별도인 8774. 백엔드에서 app.ai.part-base-urls.FRAME으로 연결 (backend/README.md "실제 AI 연결")
-- 검사항목은 통합 모델 1개라 UNIFIED로 둠 (코드표 TBD-04 결정 전 임시)
INSERT INTO inspection_item (id, part_id, item_code, name)
SELECT UUID(), id, 'UNIFIED', '통합 불량' FROM part WHERE part_code = 'FRAME';

-- 보정기가 있는 첫 실제 모델. 검사항목당 active 1개라 바로 활성으로 등록
INSERT INTO ai_model (id, item_id, model_version, pipeline_config_json, checksum, metrics_json,
                      patch_inspection_supported, active, calibrator_version, created_at)
SELECT UUID(), i.id, 'frame-swin-tiny-unified-e08-2425d7e46572-dev',
       JSON_OBJECT('backbone', 'swin-tiny', 'checkpoint', '통합 e08', 'cam', 'LayerCAM',
                   'note', 'AI 11/11 전달. 보정기 frame-e08-temperature-5d4299808c3e-demo'),
       '2425d7e46572', NULL,
       FALSE, TRUE, 'frame-e08-temperature-5d4299808c3e-demo', NOW(6)
FROM inspection_item i JOIN part p ON p.id = i.part_id
WHERE p.part_code = 'FRAME' AND i.item_code = 'UNIFIED';

-- 시연 정책: 기준치 3.67%, 검증 범위 3.00~3.67%. 평가 사진 사후 적용값으로 운영 기준 아님
-- ready·비활성으로 등록. 공동 시험 때 관리자 API(POST /api/v1/admin/policies/{id}/activate)로 적용
INSERT INTO automation_policy (id, model_id, item_id, calibrator_version, policy_version, target_miss_rate,
                               pass_threshold, validated_min, validated_max, metrics_json, ready, active,
                               created_at, activated_at)
SELECT UUID(), m.id, m.item_id, 'frame-e08-temperature-5d4299808c3e-demo', 'frame-e08-demo-0367', NULL,
       0.036700, 0.030000, 0.036700,
       JSON_OBJECT('note', '프레임 e08 캡스톤 시연 기준. 같은 평가 사진에 사후 적용한 값이며 독립 검증 아님',
                   'sampleCount', 3241, 'normalAutoPass', '846/1439', 'defectAutoPass', '0/1802'),
       TRUE, FALSE, NOW(6), NULL
FROM ai_model m WHERE m.model_version = 'frame-swin-tiny-unified-e08-2425d7e46572-dev';
