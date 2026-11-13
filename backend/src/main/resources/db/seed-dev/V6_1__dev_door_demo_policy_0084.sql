-- 개발용: 도어 Mock 시연 정책 0.84% (AI 김도현 11/12 도어 내부 평가, 모바일 PR #24와 같은 값)
-- V5_3(example-door-demo-30, 0.30)을 대신하는 시연 값. 개발 DB에 V6이 이미 적용돼 있어 V6_1로 둔다(V5_x면 Flyway 검증 실패). V5_3은 이미 적용된 DB가 있어 지우지 않고 비활성으로 둔다
-- 시작 기준치 0.0084, 조정 범위 0.0084~0.0092. 관리자 조정 시연: Mock 보정 0.0088은 0.0084에서 REVIEW,
-- 0.0092로 조정·적용 후 AUTO_PASS (backend/README.md "시연 정책", Mock 시나리오 GOOD_DEMO_0088)
-- 실제 e02는 보정기가 없어 정책을 붙일 수 없으므로, 보정기가 있는 Mock 모델에 같은 기준을 등록한다. ready·비활성
INSERT INTO automation_policy (id, model_id, item_id, calibrator_version, policy_version, target_miss_rate,
                               pass_threshold, validated_min, validated_max, metrics_json, ready, active,
                               created_at, activated_at)
SELECT UUID(), m.id, m.item_id, 'mock-cal-v1', 'example-door-demo-0084', NULL,
       0.008400, 0.008400, 0.009200,
       JSON_OBJECT('note', '도어 11/12 내부 평가 시연 기준을 Mock 모델로 재현. 기본값 0.92%, 시연은 0.84%에서 시작. 독립 검증된 운영 정책 아님'),
       TRUE, FALSE, NOW(6), NULL
FROM ai_model m WHERE m.model_version = 'mock-door-swin-t-v1';
