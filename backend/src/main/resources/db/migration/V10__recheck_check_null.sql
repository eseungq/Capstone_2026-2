-- V10: 표본 재확인 CHECK 보강 (김남균 DB 검토 11/20·11/21, 점검 I18·I20·I21·I22)
--   - MySQL CHECK는 결과가 NULL이면 통과. V9의 두 제약이 비교 대상 NULL일 때 통과하던 구멍을 막음
--   - 같은 행 안에서 확인되는 규칙(뽑힘 = 추출 값 < 비율, 시각 순서)을 점검 SQL에서 CHECK로 옮김
--   - 적용 전 db/04_integrity_checks.sql의 I18·I20·I21·I22가 0건인지 확인할 것
--     (MySQL DDL은 트랜잭션으로 묶이지 않아, 중간에 실패하면 앞 문장만 적용된 채 Flyway가 실패 처리)

-- 1) 재확인 규칙은 AUTO_PASS 판정 건에만. V9는 recommended_action이 NULL(접수·분석 중·실패)이면 통과 (I18)
ALTER TABLE inspection DROP CHECK chk_insp_recheck_rule;
ALTER TABLE inspection
    ADD CONSTRAINT chk_insp_recheck_rule CHECK (recheck_rule_id IS NULL
        OR (recommended_action IS NOT NULL AND recommended_action = 'AUTO_PASS'));

-- 2) 확인함은 재확인 FAIL에만, 확인자·시각은 짝. V9는 result가 NULL이면 통과 (I22)
ALTER TABLE auto_pass_recheck DROP CHECK chk_recheck_ack;
ALTER TABLE auto_pass_recheck
    ADD CONSTRAINT chk_recheck_ack CHECK (
           (acknowledged_by IS NULL AND acknowledged_at IS NULL AND acknowledge_note IS NULL)
        OR (acknowledged_by IS NOT NULL AND acknowledged_at IS NOT NULL
            AND result IS NOT NULL AND result = 'FAIL'));

-- 3) 규칙이 있는 결정 행은 뽑힘 = 추출 값 < 구간 비율 (I20 중 같은 행 부분, 백엔드 RecheckRules와 같음)
--    sampling_rate는 DECIMAL(7,6), draw_value는 DOUBLE. MySQL은 둘을 double로 비교하고,
--    백엔드도 비율을 소수 6자리로 맞춘 double로 비교하므로 경계에서 결과가 갈리지 않음. V8 행(rule_id NULL)은 제외
ALTER TABLE auto_pass_recheck
    ADD CONSTRAINT chk_recheck_draw CHECK (rule_id IS NULL
        OR sampled = (sampling_rate > 0 AND draw_value < sampling_rate));

-- 4) 시각 순서: 재확인은 추출 결정 뒤, 확인함은 재확인 뒤 (I21 중 같은 행 부분. 모두 서버 시각)
--    검사 완료 → 추출 결정은 테이블이 달라 점검 SQL로 확인
ALTER TABLE auto_pass_recheck
    ADD CONSTRAINT chk_recheck_order CHECK (
            (rechecked_at IS NULL OR rechecked_at >= sampled_at)
        AND (acknowledged_at IS NULL OR (rechecked_at IS NOT NULL AND acknowledged_at >= rechecked_at)));
