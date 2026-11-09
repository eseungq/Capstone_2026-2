-- 개발용: 도어 캡스톤 시연 정책 (AI 김도현 11/09 전달, ai/VALIDATION.md "도어 e02 캡스톤 시연 기준")
-- 실제 e02는 보정기가 없어 정책을 붙일 수 없으므로, 보정기가 있는 Mock 모델에 같은 기준을 등록해 시연한다
-- 기준치 0.30, 검증 범위 0.2801~0.3752. 관리자 조정 시연: Mock 보정 0.32는 0.30에서 REVIEW, 0.35로 조정·적용 후 AUTO_PASS
-- ready·비활성으로 등록. 시연 때 관리자 API로 example-door-p1을 중지하고 이 정책을 적용 (backend/README.md "시연 정책")
INSERT INTO automation_policy (id, model_id, item_id, calibrator_version, policy_version, target_miss_rate,
                               pass_threshold, validated_min, validated_max, metrics_json, ready, active,
                               created_at, activated_at)
SELECT UUID(), m.id, m.item_id, 'mock-cal-v1', 'example-door-demo-30', NULL,
       0.300000, 0.280100, 0.375200,
       JSON_OBJECT('note', '도어 e02 캡스톤 시연 기준을 Mock 모델로 재현. 사후 적용값이며 실제 검증 정책 아님',
                   'sampleCount', 148, 'normalAutoPass', '53/62', 'defectAutoPass', '0/86'),
       TRUE, FALSE, NOW(6), NULL
FROM ai_model m WHERE m.model_version = 'mock-door-swin-t-v1';
