-- 개발용: 재학습 DOOR 2회차 모델 버전 등록 (AI 김도현 11/03 전달, 실제 AI 연동 시험용)
-- 보정기 미준비라 calibrator_version은 NULL, 정책도 만들지 않음 → 분석 성공 건은 REVIEW(NO_ACTIVE_POLICY)
-- 검사항목당 active 모델은 1개라 비활성으로 등록. 전환 SQL은 backend/README.md "실제 AI 연결" 참고
-- checksum은 버전 이름의 가중치 해시 앞 12자리. 전체 sha256을 받으면 교체
INSERT INTO ai_model (id, item_id, model_version, pipeline_config_json, checksum, metrics_json,
                      patch_inspection_supported, active, calibrator_version, created_at)
SELECT UUID(), i.id, 'door-swin-tiny-e02-28a2dd1cb40b-dev',
       JSON_OBJECT('backbone', 'swin-tiny', 'checkpoint', '재학습 2회차',
                   'weightsSha256Prefix', '28a2dd1cb40b',
                   'note', 'AI 11/03 전달. GPU HTTP 단독 시험 23개 사례 통과. 보정기 미준비'),
       '28a2dd1cb40b', NULL,
       FALSE, FALSE, NULL, NOW(6)
FROM inspection_item i JOIN part p ON p.id = i.part_id
WHERE p.part_code = 'DOOR' AND i.item_code = 'SCRATCH';
