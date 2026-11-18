-- V8: AUTO_PASS 표본 재확인 (계약 6.11 [제안 11/18])
-- 작업자 판정은 REVIEW 건에만 쌓여 AUTO_PASS로 빠진 불량을 알 수 없으므로, AUTO_PASS 건 일부를
-- 보정 확률 구간별 비율로 뽑아 작업자가 다시 확인한다.
--   - AUTO_PASS마다 추출 결정을 1행 기록 (뽑히지 않은 건도 sampled = FALSE로). 행이 없으면 아직 결정 전이거나
--     결정 저장에 실패한 건이라 주기적으로 다시 처리 (RecheckSweeper)
--   - 시스템 판정(inspection의 final_judgement = PASS, judged_by = SYSTEM)은 바꾸지 않고 이 테이블에만 기록
--   - 뽑을 때 쓴 비율을 함께 저장 (집계 시 가중치 1/sampling_rate)
--   - 테이블 간 규칙(대상 검사가 AUTO_PASS·SYSTEM인지)은 CHECK로 막을 수 없어 점검 SQL로 확인 (김남균 협의)
CREATE TABLE auto_pass_recheck (
    id            CHAR(36)     NOT NULL PRIMARY KEY,
    inspection_id CHAR(36)     NOT NULL UNIQUE,         -- 검사당 최대 1건
    sampled       BOOLEAN      NOT NULL,                -- 재확인 대상으로 뽑혔는지
    stratum       VARCHAR(10)  NOT NULL,                -- NEAR / MID / LOW (보정 확률 ÷ 적용 기준치)
    sampling_rate DECIMAL(7,6) NOT NULL,                -- 이 구간의 추출 비율 (뽑히지 않은 건도 기록, 구간별 모집단 집계용)
    sampled_at    DATETIME(6)  NOT NULL,                -- 추출 결정 시각
    result        VARCHAR(10)  NULL,                    -- PASS / FAIL, 재확인 전이거나 뽑히지 않았으면 NULL
    comment       VARCHAR(200) NULL,
    rechecked_by  CHAR(36)     NULL,
    rechecked_at  DATETIME(6)  NULL,
    CONSTRAINT fk_recheck_insp FOREIGN KEY (inspection_id) REFERENCES inspection (id),
    CONSTRAINT fk_recheck_user FOREIGN KEY (rechecked_by) REFERENCES users (id),
    CONSTRAINT chk_recheck_values CHECK (stratum IN ('NEAR', 'MID', 'LOW')
        AND (result IS NULL OR result IN ('PASS', 'FAIL'))),
    -- 비율 0인 구간은 뽑히지 않으므로 0도 허용. 뽑힌 건은 비율이 0보다 커야 함
    CONSTRAINT chk_recheck_rate CHECK (sampling_rate >= 0 AND sampling_rate <= 1 AND (sampled = FALSE OR sampling_rate > 0)),
    -- 뽑히지 않은 건은 재확인 결과가 없음
    CONSTRAINT chk_recheck_sampled CHECK (sampled = TRUE OR result IS NULL),
    -- 결과·확인자·확인 시각은 셋 다 없거나 셋 다 있음
    CONSTRAINT chk_recheck_done CHECK (
           (result IS NULL AND rechecked_by IS NULL AND rechecked_at IS NULL)
        OR (result IS NOT NULL AND rechecked_by IS NOT NULL AND rechecked_at IS NOT NULL))
);

-- 재확인 목록: 뽑힌 건의 대기·완료별 뽑힌 순서
CREATE INDEX idx_recheck_result_sampled ON auto_pass_recheck (sampled, result, sampled_at);
