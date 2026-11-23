-- V9: 표본 재확인 공동시험 기록 (계약 6.11 [합의 11/18 김도현·홍승인])
--   - recheck_rule: 추출 규칙(구간 경계·비율, 시험 이름) 1건 = 1행. 같은 값·같은 시험 이름이면 같은 행
--   - inspection.recheck_rule_id: AUTO_PASS로 판정할 때 적용 중이던 규칙 (판정과 같은 트랜잭션).
--     재처리는 이 규칙으로 결정하므로 실행 중 설정이 바뀌어도 판정 당시 규칙을 씀. 없으면 결정하지 않음(누락)
--   - auto_pass_recheck: 결정에 쓴 규칙·r·추출 값. V8로 기록된 행은 셋 다 NULL
--   - 관리자 확인함: 재확인 FAIL을 관리자가 봤다는 기록 (해결 완료 아님)
--   - 화면 체류 시간: 앱이 측정해 제출과 함께 보냄 (선택). REVIEW 확인(worker_confirmation)에도 같은 필드
CREATE TABLE recheck_rule (
    id           CHAR(36)     NOT NULL PRIMARY KEY,
    rule_version VARCHAR(60)  NOT NULL,   -- 값으로 만든 이름 (예: v1-b40-80-p100-30-10)
    trial_name   VARCHAR(60)  NULL,       -- 같은 설정의 시험 회차 구분 (선택, 예: 공동시험 1차)
    trial_key    VARCHAR(60)  AS (COALESCE(trial_name, '')) STORED,  -- NULL도 하나로 묶기 위한 UNIQUE용
    near_ratio   DECIMAL(7,6) NOT NULL,
    mid_ratio    DECIMAL(7,6) NOT NULL,
    near_rate    DECIMAL(7,6) NOT NULL,
    mid_rate     DECIMAL(7,6) NOT NULL,
    low_rate     DECIMAL(7,6) NOT NULL,
    created_at   DATETIME(6)  NOT NULL,
    CONSTRAINT uk_recheck_rule UNIQUE (rule_version, trial_key),
    CONSTRAINT chk_recheck_rule_values CHECK (0 <= mid_ratio AND mid_ratio <= near_ratio AND near_ratio <= 1
        AND near_rate BETWEEN 0 AND 1 AND mid_rate BETWEEN 0 AND 1 AND low_rate BETWEEN 0 AND 1)
);

ALTER TABLE inspection
    ADD COLUMN recheck_rule_id CHAR(36) NULL,   -- AUTO_PASS 판정 당시 표본 재확인 규칙 (기능이 꺼져 있었으면 NULL)
    ADD CONSTRAINT fk_insp_recheck_rule FOREIGN KEY (recheck_rule_id) REFERENCES recheck_rule (id),
    ADD CONSTRAINT chk_insp_recheck_rule CHECK (recheck_rule_id IS NULL OR recommended_action = 'AUTO_PASS');

ALTER TABLE auto_pass_recheck
    ADD COLUMN rule_id          CHAR(36)     NULL,   -- 결정에 쓴 규칙
    ADD COLUMN ratio            DOUBLE       NULL,   -- 보정 확률 ÷ 적용 기준치
    ADD COLUMN draw_value       DOUBLE       NULL,   -- 검사 ID로 정한 0~1 값 (sampled = draw_value < sampling_rate)
    ADD COLUMN acknowledged_by  CHAR(36)     NULL,
    ADD COLUMN acknowledged_at  DATETIME(6)  NULL,
    ADD COLUMN acknowledge_note VARCHAR(200) NULL,
    ADD COLUMN screen_dwell_ms  BIGINT       NULL,   -- 상세 화면이 앞에 보인 시간 합 (ms)
    ADD COLUMN first_opened_at  DATETIME(6)  NULL,   -- 상세 화면을 처음 연 시각 (기기 시계)
    ADD COLUMN open_count       INT          NULL,
    ADD CONSTRAINT fk_recheck_rule FOREIGN KEY (rule_id) REFERENCES recheck_rule (id),
    ADD CONSTRAINT fk_recheck_ack_user FOREIGN KEY (acknowledged_by) REFERENCES users (id),
    ADD CONSTRAINT chk_recheck_rule CHECK (
           (rule_id IS NULL AND ratio IS NULL AND draw_value IS NULL)
        OR (rule_id IS NOT NULL AND ratio IS NOT NULL AND draw_value IS NOT NULL
            AND draw_value >= 0 AND draw_value < 1)),
    -- 확인함은 재확인 FAIL에만, 확인자·시각은 짝
    ADD CONSTRAINT chk_recheck_ack CHECK (
           (acknowledged_by IS NULL AND acknowledged_at IS NULL AND acknowledge_note IS NULL)
        OR (acknowledged_by IS NOT NULL AND acknowledged_at IS NOT NULL AND result = 'FAIL')),
    -- 체류 시간은 재확인 결과와 함께만
    ADD CONSTRAINT chk_recheck_timing CHECK (
           (screen_dwell_ms IS NULL AND first_opened_at IS NULL AND open_count IS NULL)
        OR (screen_dwell_ms IS NOT NULL AND first_opened_at IS NOT NULL AND open_count IS NOT NULL
            AND screen_dwell_ms >= 0 AND open_count >= 1 AND result IS NOT NULL));

ALTER TABLE worker_confirmation
    ADD COLUMN screen_dwell_ms BIGINT      NULL,
    ADD COLUMN first_opened_at DATETIME(6) NULL,
    ADD COLUMN open_count      INT         NULL,
    ADD CONSTRAINT chk_confirm_timing CHECK (
           (screen_dwell_ms IS NULL AND first_opened_at IS NULL AND open_count IS NULL)
        OR (screen_dwell_ms IS NOT NULL AND first_opened_at IS NOT NULL AND open_count IS NOT NULL
            AND screen_dwell_ms >= 0 AND open_count >= 1));
