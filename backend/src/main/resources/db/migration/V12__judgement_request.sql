-- V12: 판정 확인 요청·정정 (계약 6.12 [제안 11/23])
--   - 시스템 판정 건(judged_by = SYSTEM)을 작업자가 다르게 확인하면 요청을 남기고, 관리자가 유지(KEPT)·정정(CORRECTED)
--   - 정정해도 inspection.final_judgement·judged_by(최초 판정)는 바꾸지 않음 (V5 CHECK, 정책 실적은 최초 경로로 셈)
--     현재 판정 = 마지막 CORRECTED 요청의 claimed_judgement, 없으면 최초 판정
--   - 검사당 처리 대기(OPEN) 요청은 1건: open_key 생성 컬럼 UNIQUE (V9 trial_key와 같은 방식, NULL은 여러 건 허용)
--   - MySQL CHECK는 결과가 NULL이면 통과하므로 NULL이 될 수 있는 값은 IS NULL·IS NOT NULL을 함께 검사
--   - 테이블 간 규칙(대상이 judged_by = SYSTEM, 요청자 WORKER, 처리자 ADMIN)은 CHECK로 막을 수 없어 점검 SQL로 확인
--   - V11(worker_confirmation.batch_id)과 관계없음
CREATE TABLE judgement_request (
    id                 CHAR(36)     NOT NULL PRIMARY KEY,
    inspection_id      CHAR(36)     NOT NULL,
    requested_by       CHAR(36)     NOT NULL,   -- 요청 작업자
    requested_at       DATETIME(6)  NOT NULL,
    original_judgement VARCHAR(10)  NOT NULL,   -- 검사의 최초 판정
    current_judgement  VARCHAR(10)  NOT NULL,   -- 요청 당시 현재 판정 (앞선 정정이 있으면 그 값)
    claimed_judgement  VARCHAR(10)  NOT NULL,   -- 작업자가 확인한 판정 (현재 판정과 다름)
    area               VARCHAR(100) NULL,       -- 부위 (선택)
    reason             VARCHAR(500) NOT NULL,
    status             VARCHAR(10)  NOT NULL,   -- OPEN / KEPT / CORRECTED
    resolved_by        CHAR(36)     NULL,       -- 처리 관리자
    resolved_at        DATETIME(6)  NULL,
    resolve_note       VARCHAR(500) NULL,
    open_key           CHAR(36)     AS (IF(status = 'OPEN', inspection_id, NULL)) STORED,
    CONSTRAINT fk_jreq_insp FOREIGN KEY (inspection_id) REFERENCES inspection (id),
    CONSTRAINT fk_jreq_requested_by FOREIGN KEY (requested_by) REFERENCES users (id),
    CONSTRAINT fk_jreq_resolved_by FOREIGN KEY (resolved_by) REFERENCES users (id),
    CONSTRAINT uk_judgement_request_open UNIQUE (open_key),
    -- 값 목록 (세 판정·상태는 NOT NULL이라 NULL로 통과하지 않음)
    CONSTRAINT chk_jreq_values CHECK (original_judgement IN ('PASS', 'FAIL') AND current_judgement IN ('PASS', 'FAIL')
        AND claimed_judgement IN ('PASS', 'FAIL') AND status IN ('OPEN', 'KEPT', 'CORRECTED')),
    CONSTRAINT chk_jreq_claim CHECK (claimed_judgement <> current_judgement),
    -- 대기면 처리자·시각·메모 셋 다 없음, 처리됐으면 셋 다 있음
    CONSTRAINT chk_jreq_resolved CHECK (
           (status = 'OPEN' AND resolved_by IS NULL AND resolved_at IS NULL AND resolve_note IS NULL)
        OR (status IN ('KEPT', 'CORRECTED') AND resolved_by IS NOT NULL AND resolved_at IS NOT NULL
            AND resolve_note IS NOT NULL AND CHAR_LENGTH(resolve_note) >= 1)),
    -- 사유는 1자 이상, 처리는 요청 뒤 (모두 서버 시각)
    CONSTRAINT chk_jreq_text_order CHECK (CHAR_LENGTH(reason) >= 1
        AND (resolved_at IS NULL OR resolved_at >= requested_at)),
    -- 상세(검사별 최신순)·이력(정정 일괄 조회)
    INDEX idx_jreq_insp (inspection_id, status, requested_at),
    -- 관리자 목록: 상태별 요청 순
    INDEX idx_jreq_status_requested (status, requested_at)
);
