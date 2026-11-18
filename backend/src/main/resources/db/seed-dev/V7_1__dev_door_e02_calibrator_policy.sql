-- 개발용: 도어 e02 시연 보정기와 실제 모델 시연 정책 (AI 김도현 11/17 전달)
-- 보정기 door-e02-temperature-30962f5cac45-demo를 e02에 연결. 8771이 이 보정기로 응답하기 전까지는
--   응답 calibratorVersion이 null이라 정책과 호환되지 않아 지금처럼 REVIEW(NO_ACTIVE_POLICY)
-- 내부 평가(같은 e02 가중치·보정기, 1,159개 사진 그룹):
--   0.92%: 정상 208/566그룹 자동 통과, 불량 0/593 / 0.84%: 정상 189/566, 불량 0/593
-- 시연: 공동 시험에서 0.84% 적용 → 정상 사진(보정 약 0.876%) REVIEW(ABOVE_THRESHOLD)
--   → 0.92% 적용 → 같은 사진 새 접수 AUTO_PASS. 사후 적용한 시연 기준이며 운영 기준 아님
-- 두 정책 모두 ready·비활성으로 등록 (공동 시험 전 동작 유지). V7 이후라 검사항목은 UNIFIED
UPDATE ai_model SET calibrator_version = 'door-e02-temperature-30962f5cac45-demo'
WHERE model_version = 'door-swin-tiny-e02-28a2dd1cb40b-dev';

INSERT INTO automation_policy (id, model_id, item_id, calibrator_version, policy_version, target_miss_rate,
                               pass_threshold, validated_min, validated_max, metrics_json, ready, active,
                               created_at, activated_at)
SELECT UUID(), m.id, m.item_id, 'door-e02-temperature-30962f5cac45-demo', 'door-e02-demo-0092', NULL,
       0.009200, 0.008400, 0.009200,
       JSON_OBJECT('note', '도어 e02 캡스톤 시연 기준. 내부 평가 사진 그룹에 사후 적용한 값, 독립 검증된 운영 정책 아님',
                   'sampleCount', 1159, 'normalAutoPass', '208/566', 'defectAutoPass', '0/593'),
       TRUE, FALSE, NOW(6), NULL
FROM ai_model m JOIN inspection_item i ON i.id = m.item_id
WHERE m.model_version = 'door-swin-tiny-e02-28a2dd1cb40b-dev' AND i.item_code = 'UNIFIED';

INSERT INTO automation_policy (id, model_id, item_id, calibrator_version, policy_version, target_miss_rate,
                               pass_threshold, validated_min, validated_max, metrics_json, ready, active,
                               created_at, activated_at)
SELECT UUID(), m.id, m.item_id, 'door-e02-temperature-30962f5cac45-demo', 'door-e02-demo-0084', NULL,
       0.008400, 0.008400, 0.009200,
       JSON_OBJECT('note', '도어 e02 시연 조정 하한. 0.92%와 같은 평가 사진 그룹 기준',
                   'sampleCount', 1159, 'normalAutoPass', '189/566', 'defectAutoPass', '0/593'),
       TRUE, FALSE, NOW(6), NULL
FROM ai_model m JOIN inspection_item i ON i.id = m.item_id
WHERE m.model_version = 'door-swin-tiny-e02-28a2dd1cb40b-dev' AND i.item_code = 'UNIFIED';
