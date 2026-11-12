-- 개발용: 도어 Mock 시연 정책 기본값 0.92% (AI 김도현 11/12 도어 e02 내부 평가 재진행 결과)
-- 기본 기준치 0.0092, 관리자 조정 범위 0.0084~0.0092. 내부 평가 1,159개 사진 그룹:
--   0.92%: 정상 209/566그룹 자동 통과, 불량 자동 통과 0/593그룹 / 0.84%: 정상 189/566, 불량 0/593
-- 시연: 이 정책 적용 → Mock 보정 0.0088 AUTO_PASS → 0.0084로 조정·적용 → 같은 입력 REVIEW(ABOVE_THRESHOLD) → 이 정책 재적용
-- V6_1(example-door-demo-0084, 시작값 0.0084)은 이미 적용된 DB가 있어 그대로 두고 비활성. 기존 30%(V5_3)는 외부 사진 사후 적용 참고값
-- 실제 e02는 보정기가 없어 정책을 붙일 수 없으므로 보정기가 있는 Mock 모델에 등록한다. ready·비활성
INSERT INTO automation_policy (id, model_id, item_id, calibrator_version, policy_version, target_miss_rate,
                               pass_threshold, validated_min, validated_max, metrics_json, ready, active,
                               created_at, activated_at)
SELECT UUID(), m.id, m.item_id, 'mock-cal-v1', 'example-door-demo-0092', NULL,
       0.009200, 0.008400, 0.009200,
       JSON_OBJECT('note', '도어 e02 11/12 내부 평가 시연 기준을 Mock 모델로 재현. 평가 단위는 사진 그룹, 독립 검증된 운영 정책 아님',
                   'sampleCount', 1159, 'normalAutoPass', '209/566', 'defectAutoPass', '0/593',
                   'atValidatedMin', JSON_OBJECT('passThreshold', 0.0084, 'normalAutoPass', '189/566', 'defectAutoPass', '0/593')),
       TRUE, FALSE, NOW(6), NULL
FROM ai_model m WHERE m.model_version = 'mock-door-swin-t-v1';
