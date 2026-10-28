-- 개발용: 실제 DOOR 모델 버전 등록 (AI 김도현 10/28 전달, 형식 검증용)
-- 보정기 미준비라 calibrator_version은 NULL, 정책도 만들지 않음 → 분석 성공 건은 REVIEW(NO_ACTIVE_POLICY)
-- V5에서 검사항목당 active 모델은 1개라 기본은 Mock 모델 active 유지, 이 모델은 비활성으로 등록
-- 실제 AI로 바꾸는 SQL은 backend/README.md "실제 AI 연결" 참고
INSERT INTO ai_model (id, item_id, model_version, pipeline_config_json, checksum, metrics_json,
                      patch_inspection_supported, active, calibrator_version, created_at)
SELECT UUID(), i.id, 'door-swin-tiny-e20-8d042c7bfab2',
       JSON_OBJECT('backbone', 'swin-tiny', 'checkpoint', 'epoch20 best.pt',
                   'weightsSha256', '8d042c7bfab20ba2527ef3693aed08e0df7e1b1ce58acc45b44de7ae5d0d6ab7',
                   'note', 'AI 10/28 전달. 보정기 미준비'),
       '8d042c7bfab20ba2527ef3693aed08e0df7e1b1ce58acc45b44de7ae5d0d6ab7', NULL,
       FALSE, FALSE, NULL, NOW(6)
FROM inspection_item i JOIN part p ON p.id = i.part_id
WHERE p.part_code = 'DOOR' AND i.item_code = 'SCRATCH';
