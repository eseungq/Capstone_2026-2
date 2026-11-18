-- V7: 검사항목 코드 통일 (TBD-04, 11/17 김도현 결정)
-- 도어 e02도 스크래치·외관 손상을 한 모델에서 정상·불량으로 분류 → 프레임·카울커버와 같이 UNIFIED
-- 모델·정책·검사는 inspection_item.id(UUID)로 연결돼 있어 코드·이름만 바꿔도 기존 이력·연결은 그대로
-- 이후 도어 시드는 item_code = 'UNIFIED'로 찾는다 (V5_1·V5_2 등 이미 적용된 시드는 고치지 않음)
UPDATE inspection_item i JOIN part p ON p.id = i.part_id
SET i.item_code = 'UNIFIED', i.name = '통합 불량'
WHERE p.part_code = 'DOOR' AND i.item_code = 'SCRATCH';
