-- 부품 11종 (부품명은 필요 시 수정)
INSERT INTO part (id, part_code, name) VALUES
    (UUID(), 'DOOR', '도어'),
    (UUID(), 'RAD_GRILLE', '라디에이터 그릴'),
    (UUID(), 'ROOF_SIDE', '루프 사이드'),
    (UUID(), 'WIRING', '와이어링'),
    (UUID(), 'BUMPER', '범퍼'),
    (UUID(), 'COWL_COVER', '카울 커버'),
    (UUID(), 'CONNECTOR', '커넥터'),
    (UUID(), 'TAIL_LAMP', '테일 램프'),
    (UUID(), 'HEAD_LAMP', '헤드 램프'),
    (UUID(), 'FRAME', '프레임'),
    (UUID(), 'FENDER', '펜더');

-- 프로토타입 검사항목: 도어 스크래치 (코드값은 TBD-04 결정 전 임시)
INSERT INTO inspection_item (id, part_id, item_code, name)
SELECT UUID(), id, 'SCRATCH', '스크래치' FROM part WHERE part_code = 'DOOR';
