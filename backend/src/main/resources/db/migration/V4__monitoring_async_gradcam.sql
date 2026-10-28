-- V4: 공정 모니터링·비동기 접수·Grad-CAM·정책 버전 (계약 v4 9장)
-- 김남균 DB 설계(01_schema.sql) 수령 후 컬럼명·제약을 대조해 맞출 것

-- 1) 표시용 검사 번호(INS-000001) 발급 카운터. 행 잠금으로 번호 중복 방지
CREATE TABLE inspection_no_seq (
    name     VARCHAR(20) NOT NULL PRIMARY KEY,
    last_val BIGINT      NOT NULL
);
INSERT INTO inspection_no_seq (name, last_val) VALUES ('INSPECTION', 0);

-- 2) inspection: 접수 시각 명칭 변경 + 비동기·판정·재검사·통계 대비 컬럼
ALTER TABLE inspection RENAME COLUMN created_at TO received_at;

ALTER TABLE inspection
    MODIFY COLUMN user_id CHAR(36) NULL,                                   -- 접수 계정 (DEVICE 또는 ADMIN)
    ADD COLUMN inspection_no          VARCHAR(20)   NOT NULL AFTER id,      -- 화면 표시용 번호
    ADD COLUMN source                 VARCHAR(10)   NOT NULL DEFAULT 'DEVICE' AFTER user_id, -- DEVICE, ADMIN, RETRY
    ADD COLUMN line_code              VARCHAR(30)   NULL AFTER item_id,     -- 향후 라인별 통계 대비 (9.1)
    ADD COLUMN captured_at            DATETIME(6)   NULL,                   -- 촬영(모사) 시각
    ADD COLUMN started_at             DATETIME(6)   NULL,                   -- 분석 시작 시각
    ADD COLUMN calibrator_version     VARCHAR(100)  NULL,
    ADD COLUMN review_reason          VARCHAR(30)   NULL,                   -- DEFECT_PREDICTED 등 (계약 4장)
    ADD COLUMN judged_by              VARCHAR(10)   NULL,                   -- SYSTEM, WORKER
    ADD COLUMN pass_threshold_applied DECIMAL(7, 6) NULL,                   -- 판정 당시 기준치 스냅숏
    ADD COLUMN gradcam_status         VARCHAR(20)   NULL,                   -- GENERATED, NOT_REQUIRED, FAILED
    ADD COLUMN retry_of_inspection_id CHAR(36)      NULL,                   -- 재검사 원본 FAILED 검사
    ADD COLUMN client_request_id      VARCHAR(100)  NULL,                   -- Idempotency-Key
    ADD COLUMN ai_response_json       JSON          NULL,                   -- AI 응답 원문 (이미지 데이터 제외)
    ADD COLUMN error_detail           VARCHAR(1000) NULL,                   -- AI 오류 코드·메시지 등
    ADD COLUMN trace_id               VARCHAR(32)   NULL,                   -- 접수 요청 traceId
    ADD CONSTRAINT uq_insp_no UNIQUE (inspection_no),
    ADD CONSTRAINT uq_insp_retry_of UNIQUE (retry_of_inspection_id),      -- FAILED 1건당 재검사 1회
    ADD CONSTRAINT uq_insp_client_request UNIQUE (user_id, client_request_id),
    ADD CONSTRAINT fk_insp_retry_of FOREIGN KEY (retry_of_inspection_id) REFERENCES inspection (id),
    ADD INDEX idx_insp_part_received (part_id, received_at),
    ADD INDEX idx_insp_queue (status, recommended_action, final_judgement, received_at);

-- 상태 조합 제약. CHECK는 결과가 NULL이면 통과하므로 IS NOT NULL을 함께 검사 (김남균 DB 설계 반영)
ALTER TABLE inspection
    ADD CONSTRAINT chk_insp_status CHECK (status IN ('RECEIVED', 'ANALYZING', 'COMPLETED', 'FAILED')),
    ADD CONSTRAINT chk_insp_failed CHECK (status <> 'FAILED'
        OR (recommended_action IS NULL AND final_judgement IS NULL)),
    ADD CONSTRAINT chk_insp_completed CHECK (status <> 'COMPLETED'
        OR (recommended_action IS NOT NULL AND predicted_quality IS NOT NULL)),
    ADD CONSTRAINT chk_insp_auto_pass CHECK (recommended_action IS NULL OR recommended_action <> 'AUTO_PASS'
        OR (final_judgement IS NOT NULL AND final_judgement = 'PASS' AND judged_by IS NOT NULL AND judged_by = 'SYSTEM')),
    ADD CONSTRAINT chk_insp_review CHECK (recommended_action IS NULL OR recommended_action <> 'REVIEW'
        OR (review_reason IS NOT NULL
            AND (final_judgement IS NULL OR (judged_by IS NOT NULL AND judged_by = 'WORKER')))),
    ADD CONSTRAINT chk_insp_judged_by CHECK (final_judgement IS NULL OR judged_by IS NOT NULL);

-- 3) image_storage: 원본과 Grad-CAM 구분 저장. 검사당 원본 1, Grad-CAM 최대 1
--    storage_uri는 저장소 상대 키 (예: original/2026/10/16/<id>.jpg)
ALTER TABLE image_storage
    ADD COLUMN image_type       VARCHAR(10) NOT NULL DEFAULT 'ORIGINAL' AFTER inspection_id,
    ADD COLUMN exif_orientation INT         NULL,
    ADD CONSTRAINT uq_image_insp_type UNIQUE (inspection_id, image_type),
    ADD CONSTRAINT chk_image_type CHECK (image_type IN ('ORIGINAL', 'GRADCAM'));
-- 기존 inspection_id 단일 UNIQUE 제거 (FK는 위 복합 UNIQUE 인덱스를 사용)
ALTER TABLE image_storage DROP INDEX inspection_id;

-- 4) automation_policy: 목표 미검출률 방식 → passThreshold 조정 방식. 조정은 행 수정 대신 새 버전
ALTER TABLE automation_policy
    MODIFY COLUMN target_miss_rate DECIMAL(6, 5) NULL,                     -- 과거 기록 보존용
    ADD COLUMN calibrator_version VARCHAR(100)  NULL AFTER item_id,        -- 호환 보정기 버전
    ADD COLUMN validated_min      DECIMAL(7, 6) NULL AFTER pass_threshold, -- AI 검증 범위
    ADD COLUMN validated_max      DECIMAL(7, 6) NULL AFTER validated_min,
    ADD COLUMN based_on_policy_id CHAR(36)      NULL,                      -- 기준 조정으로 만든 버전의 원래 정책
    ADD COLUMN activated_at       DATETIME(6)   NULL,
    ADD CONSTRAINT fk_policy_based_on FOREIGN KEY (based_on_policy_id) REFERENCES automation_policy (id),
    ADD CONSTRAINT chk_policy_active_ready CHECK (active = FALSE OR ready = TRUE),
    ADD CONSTRAINT chk_policy_threshold_range CHECK (pass_threshold IS NULL OR validated_min IS NULL
        OR validated_max IS NULL OR (pass_threshold >= validated_min AND pass_threshold <= validated_max));

-- 5) ai_model: 현재 모델에 맞춘 보정기 버전
ALTER TABLE ai_model
    ADD COLUMN calibrator_version VARCHAR(100) NULL;

-- 6) worker_confirmation: 작업자 메모 (선택, 최대 200자)
ALTER TABLE worker_confirmation
    ADD COLUMN comment VARCHAR(200) NULL;

-- 7) 푸시 알림 기기 토큰 (Expo 푸시 토큰). 알림 기록 테이블은 두지 않음 (계약 8.3)
CREATE TABLE device_token (
    id           CHAR(36)     NOT NULL PRIMARY KEY,
    user_id      CHAR(36)     NOT NULL,
    token        VARCHAR(200) NOT NULL UNIQUE,
    platform     VARCHAR(10)  NOT NULL,                -- ANDROID, IOS
    created_at   DATETIME(6)  NOT NULL,
    last_seen_at DATETIME(6)  NOT NULL,
    CONSTRAINT fk_device_token_user FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT chk_device_token_platform CHECK (platform IN ('ANDROID', 'IOS'))
);
