-- 최종 스키마 전체 (V1 → V2 → V3 → V4 → V5 → V6 적용 결과를 한 파일로 합친 것) · 김남균 DB · 2026-10-28
--
-- 11/11 갱신: V6 수동 판정 반영 — source MANUAL, review_reason AI_UNAVAILABLE, 완료 규칙 통합(chk_insp_completed_v6),
--   chk_insp_manual·chk_insp_reason_ai_unavailable 추가
-- 용도: 비교·검토용 원본. Flyway에 넣지 않는다 (실제 DB는 V1·V3·V4·V5 마이그레이션이 만든다).
--   이 파일과 마이그레이션 결과가 다르면 마이그레이션이 기준이다.
-- 포함: 테이블·컬럼·키·인덱스·제약 + inspection_no_seq 초기 행 (V4에 있는 것)
-- 제외: V2 부품·검사항목 시드, seed-dev 시드(V3_1 계정, V4_1·V5_1~V5_5 모델·정책)
-- 컬럼 순서: 마이그레이션 적용 후 실제 순서와 같게 맞춤 (V4의 AFTER 위치 반영)
-- 11/05 갱신: 백엔드 적용 V5(10/28 이승규 수정본) 반영 — gradcam_status NO_ACTIVATION 추가, FAILED면 predicted_quality NULL
-- 상태: 이 파일 자체는 MySQL 실행 미확인 (V5·V6 마이그레이션은 백엔드 MySQL에서 적용 확인).
--       SQLite 대체 실행으로 마이그레이션과 컬럼·제약 일치만 확인
-- 대상: MySQL 8.0.19 이상 (백엔드 docker compose 기준 8.4)

-- =====================================================================
-- 계정·인증
-- =====================================================================
CREATE TABLE users (
    id                 CHAR(36)     NOT NULL PRIMARY KEY,
    login_id           VARCHAR(50)  NOT NULL UNIQUE,
    password_hash      VARCHAR(100) NOT NULL,
    role               VARCHAR(10)  NOT NULL,                  -- WORKER, ADMIN, DEVICE (V3)
    failed_login_count INT          NOT NULL DEFAULT 0,        -- 잠금 기준은 TBD-10
    locked             BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at         DATETIME(6)  NOT NULL,
    CONSTRAINT chk_users_role CHECK (role IN ('WORKER', 'ADMIN', 'DEVICE'))                           -- V3
);

-- V3: Refresh Token은 SHA-256 해시만 저장, 폐기 시 revoked_at 기록
CREATE TABLE refresh_token (
    id         CHAR(36)    NOT NULL PRIMARY KEY,
    user_id    CHAR(36)    NOT NULL,
    token_hash CHAR(64)    NOT NULL UNIQUE,
    expires_at DATETIME(6) NOT NULL,
    revoked_at DATETIME(6) NULL,
    created_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_refresh_user FOREIGN KEY (user_id) REFERENCES users (id),
    INDEX idx_refresh_user (user_id)
);

-- V4: 푸시 알림 기기 토큰 (알림 기록 테이블은 두지 않음)
CREATE TABLE device_token (
    id           CHAR(36)     NOT NULL PRIMARY KEY,
    user_id      CHAR(36)     NOT NULL,
    token        VARCHAR(200) NOT NULL UNIQUE,
    platform     VARCHAR(10)  NOT NULL,                        -- ANDROID, IOS
    created_at   DATETIME(6)  NOT NULL,
    last_seen_at DATETIME(6)  NOT NULL,
    CONSTRAINT fk_device_token_user FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT chk_device_token_platform CHECK (platform IN ('ANDROID', 'IOS'))
);

-- =====================================================================
-- 기준 정보: 부품·검사항목·모델·자동 통과 정책
-- =====================================================================
CREATE TABLE part (
    id        CHAR(36)    NOT NULL PRIMARY KEY,
    part_code VARCHAR(30) NOT NULL UNIQUE,                     -- DOOR 등 (V2 시드)
    name      VARCHAR(50) NOT NULL
);

CREATE TABLE inspection_item (
    id        CHAR(36)    NOT NULL PRIMARY KEY,
    part_id   CHAR(36)    NOT NULL,
    item_code VARCHAR(30) NOT NULL,                            -- 코드 이름은 TBD-04 (SCRATCH → APPEARANCE?)
    name      VARCHAR(50) NOT NULL,
    CONSTRAINT uq_item_part_code UNIQUE (part_id, item_code),
    CONSTRAINT uq_item_id_part UNIQUE (id, part_id),           -- V5: 복합 FK 대상
    CONSTRAINT fk_item_part FOREIGN KEY (part_id) REFERENCES part (id)
);

CREATE TABLE ai_model (
    id                         CHAR(36)     NOT NULL PRIMARY KEY,
    item_id                    CHAR(36)     NOT NULL,
    model_version              VARCHAR(100) NOT NULL UNIQUE,   -- mock- 접두어는 시연용
    pipeline_config_json       JSON         NOT NULL,
    checksum                   VARCHAR(128) NOT NULL,
    metrics_json               JSON         NULL,
    patch_inspection_supported BOOLEAN      NOT NULL,          -- 패치 검사는 범위 제외, 컬럼만 유지
    active                     BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at                 DATETIME(6)  NOT NULL,
    calibrator_version         VARCHAR(100) NULL,              -- V4
    active_item_key            CHAR(36)                        -- V5: active일 때만 item_id, 아니면 NULL
        GENERATED ALWAYS AS (CASE WHEN active = TRUE THEN item_id ELSE NULL END) STORED,
    CONSTRAINT fk_model_item FOREIGN KEY (item_id) REFERENCES inspection_item (id),
    CONSTRAINT uq_model_id_item UNIQUE (id, item_id),          -- V5: 복합 FK 대상
    CONSTRAINT uq_model_active_item UNIQUE (active_item_key)   -- V5: 검사항목당 active 모델 1개
);

-- 기준치 조정은 행 수정 대신 새 버전(based_on_policy_id). example- 접두어는 예시 정책
CREATE TABLE automation_policy (
    id                 CHAR(36)      NOT NULL PRIMARY KEY,
    model_id           CHAR(36)      NOT NULL,
    item_id            CHAR(36)      NOT NULL,
    calibrator_version VARCHAR(100)  NULL,                     -- V4: 호환 보정기 버전
    policy_version     VARCHAR(100)  NOT NULL UNIQUE,
    target_miss_rate   DECIMAL(6, 5) NULL,                     -- V4에서 NULL 허용 (과거 기록 보존용)
    pass_threshold     DECIMAL(7, 6) NULL,
    validated_min      DECIMAL(7, 6) NULL,                     -- V4: AI 검증 범위
    validated_max      DECIMAL(7, 6) NULL,
    metrics_json       JSON          NOT NULL,
    ready              BOOLEAN       NOT NULL,
    active             BOOLEAN       NOT NULL DEFAULT FALSE,
    created_at         DATETIME(6)   NOT NULL,
    based_on_policy_id CHAR(36)      NULL,                     -- V4: 조정 전 원래 정책
    activated_at       DATETIME(6)   NULL,                     -- V4
    active_model_key   CHAR(36)                                -- V5: active일 때만 model_id
        GENERATED ALWAYS AS (CASE WHEN active = TRUE THEN model_id ELSE NULL END) STORED,
    CONSTRAINT fk_policy_model FOREIGN KEY (model_id) REFERENCES ai_model (id),
    CONSTRAINT fk_policy_item FOREIGN KEY (item_id) REFERENCES inspection_item (id),
    CONSTRAINT fk_policy_based_on FOREIGN KEY (based_on_policy_id) REFERENCES automation_policy (id),
    CONSTRAINT fk_policy_model_item FOREIGN KEY (model_id, item_id) REFERENCES ai_model (id, item_id),   -- V5
    CONSTRAINT uq_policy_active_model UNIQUE (active_model_key),                                         -- V5
    -- V4
    CONSTRAINT chk_policy_active_ready CHECK (active = FALSE OR ready = TRUE),
    CONSTRAINT chk_policy_threshold_range CHECK (pass_threshold IS NULL OR validated_min IS NULL
        OR validated_max IS NULL OR (pass_threshold >= validated_min AND pass_threshold <= validated_max)),
    -- V5
    CONSTRAINT chk_policy_prob_range CHECK (
            (pass_threshold IS NULL OR (pass_threshold >= 0 AND pass_threshold <= 1))
        AND (validated_min IS NULL OR (validated_min >= 0 AND validated_min <= 1))
        AND (validated_max IS NULL OR (validated_max >= 0 AND validated_max <= 1))
        AND (target_miss_rate IS NULL OR (target_miss_rate >= 0 AND target_miss_rate <= 1))),
    CONSTRAINT chk_policy_valid_order CHECK (validated_min IS NULL OR validated_max IS NULL
        OR validated_min <= validated_max),
    CONSTRAINT chk_policy_ready_values CHECK (ready = FALSE OR (
            pass_threshold IS NOT NULL AND validated_min IS NOT NULL AND validated_max IS NOT NULL
        AND calibrator_version IS NOT NULL)),
    CONSTRAINT chk_policy_active_at CHECK (active = FALSE OR activated_at IS NOT NULL)
);

-- =====================================================================
-- 검사 기록
-- =====================================================================
-- V4: 표시용 검사 번호(INS-000001) 발급 카운터. 행 잠금으로 번호 중복 방지
CREATE TABLE inspection_no_seq (
    name     VARCHAR(20) NOT NULL PRIMARY KEY,
    last_val BIGINT      NOT NULL
);
INSERT INTO inspection_no_seq (name, last_val) VALUES ('INSPECTION', 0);

-- 상태: RECEIVED → ANALYZING → COMPLETED(AUTO_PASS / REVIEW) 또는 FAILED
CREATE TABLE inspection (
    id                            CHAR(36)      NOT NULL PRIMARY KEY,
    inspection_no                 VARCHAR(20)   NOT NULL,      -- V4: 화면 표시용 번호
    user_id                       CHAR(36)      NULL,          -- 접수 계정 (DEVICE 또는 ADMIN). V4에서 NULL 허용
    source                        VARCHAR(10)   NOT NULL DEFAULT 'DEVICE',   -- DEVICE, ADMIN, RETRY(V4), MANUAL(V6)
    part_id                       CHAR(36)      NOT NULL,
    item_id                       CHAR(36)      NOT NULL,
    line_code                     VARCHAR(30)   NULL,          -- V4: 향후 라인별 통계 대비
    model_id                      CHAR(36)      NOT NULL,
    policy_id                     CHAR(36)      NULL,          -- 적용 정책 (준비 안 됐으면 NULL)
    status                        VARCHAR(20)   NOT NULL,
    predicted_quality             VARCHAR(10)   NULL,          -- GOOD, DEFECT
    raw_defect_probability        DECIMAL(7, 6) NULL,          -- 보정 전 점수 (명칭 TBD-07)
    calibrated_defect_probability DECIMAL(7, 6) NULL,
    patch_inspection_supported    BOOLEAN       NULL,          -- 패치 검사 범위 제외, 컬럼만 유지
    automation_policy_ready       BOOLEAN       NOT NULL DEFAULT FALSE,
    recommended_action            VARCHAR(20)   NULL,          -- AUTO_PASS, REVIEW
    final_judgement               VARCHAR(10)   NULL,          -- PASS, FAIL
    inference_time_ms             INT           NULL,
    error_code                    VARCHAR(40)   NULL,          -- FAILED 사유 (AI_SERVER_TIMEOUT 등)
    received_at                   DATETIME(6)   NOT NULL,      -- V4: created_at에서 이름 변경
    completed_at                  DATETIME(6)   NULL,
    captured_at                   DATETIME(6)   NULL,          -- V4: 촬영(모사) 시각
    started_at                    DATETIME(6)   NULL,          -- V4: 분석 시작 시각
    calibrator_version            VARCHAR(100)  NULL,          -- V4
    review_reason                 VARCHAR(30)   NULL,          -- V4: REVIEW 사유 (계약 4장)
    judged_by                     VARCHAR(10)   NULL,          -- V4: SYSTEM, WORKER
    pass_threshold_applied        DECIMAL(7, 6) NULL,          -- V4: 판정 당시 기준치 스냅숏
    gradcam_status                VARCHAR(20)   NULL,          -- V4: GENERATED, NOT_REQUIRED, FAILED, NO_ACTIVATION(V5)
    retry_of_inspection_id        CHAR(36)      NULL,          -- V4: 재검사·수동 판정(V6)의 원본 FAILED 검사
    client_request_id             VARCHAR(100)  NULL,          -- V4: Idempotency-Key
    ai_response_json              JSON          NULL,          -- V4: AI 응답 원문 (이미지 데이터 제외)
    error_detail                  VARCHAR(1000) NULL,          -- V4
    trace_id                      VARCHAR(32)   NULL,          -- V4
    CONSTRAINT uq_insp_no UNIQUE (inspection_no),
    CONSTRAINT uq_insp_retry_of UNIQUE (retry_of_inspection_id),                 -- FAILED 1건당 재검사 또는 수동 전환 1건
    CONSTRAINT uq_insp_client_request UNIQUE (user_id, client_request_id),
    CONSTRAINT fk_insp_user FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT fk_insp_part FOREIGN KEY (part_id) REFERENCES part (id),
    CONSTRAINT fk_insp_item FOREIGN KEY (item_id) REFERENCES inspection_item (id),
    CONSTRAINT fk_insp_model FOREIGN KEY (model_id) REFERENCES ai_model (id),
    CONSTRAINT fk_insp_policy FOREIGN KEY (policy_id) REFERENCES automation_policy (id),
    CONSTRAINT fk_insp_retry_of FOREIGN KEY (retry_of_inspection_id) REFERENCES inspection (id),
    CONSTRAINT fk_insp_item_part FOREIGN KEY (item_id, part_id) REFERENCES inspection_item (id, part_id),   -- V5
    INDEX idx_insp_user_created (user_id, received_at),        -- V1 인덱스 (컬럼 이름 변경이 따라 반영됨)
    INDEX idx_insp_part_item_created (part_id, item_id, received_at),
    INDEX idx_insp_part_received (part_id, received_at),       -- V4
    INDEX idx_insp_queue (status, recommended_action, final_judgement, received_at),   -- V4

    -- ---- V4 상태 조합 (chk_insp_auto_pass는 V5에서 교체, chk_insp_completed는 V6에서 통합) ----
    CONSTRAINT chk_insp_status CHECK (status IN ('RECEIVED', 'ANALYZING', 'COMPLETED', 'FAILED')),
    CONSTRAINT chk_insp_failed CHECK (status <> 'FAILED'
        OR (recommended_action IS NULL AND final_judgement IS NULL)),
    CONSTRAINT chk_insp_review CHECK (recommended_action IS NULL OR recommended_action <> 'REVIEW'
        OR (review_reason IS NOT NULL
            AND (final_judgement IS NULL OR (judged_by IS NOT NULL AND judged_by = 'WORKER')))),
    CONSTRAINT chk_insp_judged_by CHECK (final_judgement IS NULL OR judged_by IS NOT NULL),

    -- ---- 허용값 (V5, V6에서 MANUAL·AI_UNAVAILABLE 추가)·범위 (V5) ----
    CONSTRAINT chk_insp_values CHECK (
            (predicted_quality IS NULL OR predicted_quality IN ('GOOD', 'DEFECT'))
        AND (recommended_action IS NULL OR recommended_action IN ('AUTO_PASS', 'REVIEW'))
        AND (final_judgement IS NULL OR final_judgement IN ('PASS', 'FAIL'))
        AND (judged_by IS NULL OR judged_by IN ('SYSTEM', 'WORKER'))
        AND (review_reason IS NULL OR review_reason IN
                ('DEFECT_PREDICTED', 'NO_ACTIVE_POLICY', 'CALIBRATION_UNAVAILABLE', 'ABOVE_THRESHOLD', 'AI_UNAVAILABLE'))
        AND (gradcam_status IS NULL OR gradcam_status IN ('GENERATED', 'NOT_REQUIRED', 'FAILED', 'NO_ACTIVATION'))
        AND source IN ('DEVICE', 'ADMIN', 'RETRY', 'MANUAL')),
    CONSTRAINT chk_insp_prob_range CHECK (
            (raw_defect_probability IS NULL OR (raw_defect_probability >= 0 AND raw_defect_probability <= 1))
        AND (calibrated_defect_probability IS NULL
             OR (calibrated_defect_probability >= 0 AND calibrated_defect_probability <= 1))
        AND (pass_threshold_applied IS NULL OR (pass_threshold_applied >= 0 AND pass_threshold_applied <= 1))),

    -- ---- V5 상태별 값 ----
    CONSTRAINT chk_insp_pending CHECK (status NOT IN ('RECEIVED', 'ANALYZING') OR (
            predicted_quality IS NULL AND raw_defect_probability IS NULL
        AND recommended_action IS NULL AND final_judgement IS NULL AND judged_by IS NULL
        AND review_reason IS NULL AND gradcam_status IS NULL AND completed_at IS NULL)),
    -- V6: V4 chk_insp_completed + V5 chk_insp_completed_v5 통합. MANUAL만 AI 결과 없이 완료 허용
    CONSTRAINT chk_insp_completed_v6 CHECK (status <> 'COMPLETED' OR (
            recommended_action IS NOT NULL AND completed_at IS NOT NULL AND error_code IS NULL
        AND (source = 'MANUAL' OR (
                predicted_quality IS NOT NULL AND raw_defect_probability IS NOT NULL
            AND gradcam_status IS NOT NULL)))),
    -- 실패 시 completed_at 기록, AI 응답 검증 실패여도 predicted_quality 저장 안 함 (10/28 백엔드 확인)
    CONSTRAINT chk_insp_failed_v5 CHECK (status <> 'FAILED' OR (
            error_code IS NOT NULL AND completed_at IS NOT NULL AND predicted_quality IS NULL
        AND judged_by IS NULL AND review_reason IS NULL AND gradcam_status IS NULL)),

    -- ---- V5 AUTO_PASS 조건 (V4 제약 교체) ----
    CONSTRAINT chk_insp_auto_pass CHECK (recommended_action IS NULL OR recommended_action <> 'AUTO_PASS' OR (
            predicted_quality IS NOT NULL AND predicted_quality = 'GOOD'
        AND automation_policy_ready = TRUE AND policy_id IS NOT NULL
        AND calibrated_defect_probability IS NOT NULL AND pass_threshold_applied IS NOT NULL
        AND calibrated_defect_probability <= pass_threshold_applied
        AND final_judgement IS NOT NULL AND final_judgement = 'PASS'
        AND judged_by IS NOT NULL AND judged_by = 'SYSTEM'
        AND review_reason IS NULL)),

    -- ---- V5 REVIEW 사유 ----
    CONSTRAINT chk_insp_reason_review_only CHECK (review_reason IS NULL
        OR (recommended_action IS NOT NULL AND recommended_action = 'REVIEW')),
    CONSTRAINT chk_insp_reason_defect CHECK (
            (recommended_action IS NULL OR recommended_action <> 'REVIEW'
             OR predicted_quality IS NULL OR predicted_quality <> 'DEFECT'
             OR (review_reason IS NOT NULL AND review_reason = 'DEFECT_PREDICTED'))
        AND (review_reason IS NULL OR review_reason <> 'DEFECT_PREDICTED'
             OR (predicted_quality IS NOT NULL AND predicted_quality = 'DEFECT'))),
    CONSTRAINT chk_insp_reason_no_policy CHECK (review_reason IS NULL OR review_reason <> 'NO_ACTIVE_POLICY'
        OR automation_policy_ready = FALSE),
    CONSTRAINT chk_insp_reason_calibration CHECK (review_reason IS NULL OR review_reason <> 'CALIBRATION_UNAVAILABLE'
        OR calibrated_defect_probability IS NULL),
    CONSTRAINT chk_insp_reason_above CHECK (review_reason IS NULL OR review_reason <> 'ABOVE_THRESHOLD' OR (
            automation_policy_ready = TRUE
        AND calibrated_defect_probability IS NOT NULL AND pass_threshold_applied IS NOT NULL
        AND calibrated_defect_probability > pass_threshold_applied)),

    -- ---- V5 판정 주체·Grad-CAM·보정기·정책 스냅숏 ----
    CONSTRAINT chk_insp_judged_by_null CHECK (judged_by IS NULL OR final_judgement IS NOT NULL),
    -- NO_ACTIVATION: 계산 성공·강조 반응 없음(0맵·상수맵), 이미지 행 없음 (10/28 합의)
    CONSTRAINT chk_insp_gradcam CHECK (gradcam_status IS NULL OR (predicted_quality IS NOT NULL AND (
            (predicted_quality = 'GOOD' AND gradcam_status = 'NOT_REQUIRED')
         OR (predicted_quality = 'DEFECT' AND gradcam_status IN ('GENERATED', 'FAILED', 'NO_ACTIVATION'))))),
    CONSTRAINT chk_insp_calibrator_pair CHECK (status <> 'COMPLETED'
        OR (calibrated_defect_probability IS NULL AND calibrator_version IS NULL)
        OR (calibrated_defect_probability IS NOT NULL AND calibrator_version IS NOT NULL)),
    CONSTRAINT chk_insp_policy_snapshot CHECK (automation_policy_ready = TRUE
        OR (policy_id IS NULL AND pass_threshold_applied IS NULL)),
    -- DEFECT 예측이어도 정책 준비됐으면 정책·기준치 기록 (10/28 백엔드 확인)
    CONSTRAINT chk_insp_policy_ready_snapshot CHECK (status <> 'COMPLETED' OR automation_policy_ready = FALSE
        OR (policy_id IS NOT NULL AND pass_threshold_applied IS NOT NULL)),

    -- ---- V6 수동 판정 (AI 무응답 시, 11/11 B안) ----
    -- MANUAL: 완료·REVIEW·AI_UNAVAILABLE, 원본 FAILED 연결 필수, AI 결과·정책 값 없음
    CONSTRAINT chk_insp_manual CHECK (source <> 'MANUAL' OR (
            status = 'COMPLETED' AND retry_of_inspection_id IS NOT NULL
        AND recommended_action IS NOT NULL AND recommended_action = 'REVIEW'
        AND review_reason IS NOT NULL AND review_reason = 'AI_UNAVAILABLE'
        AND predicted_quality IS NULL AND raw_defect_probability IS NULL
        AND calibrated_defect_probability IS NULL AND calibrator_version IS NULL
        AND gradcam_status IS NULL AND inference_time_ms IS NULL
        AND policy_id IS NULL AND automation_policy_ready = FALSE AND pass_threshold_applied IS NULL)),
    -- AI_UNAVAILABLE 사유는 수동 판정 건에만
    CONSTRAINT chk_insp_reason_ai_unavailable CHECK (review_reason IS NULL
        OR review_reason <> 'AI_UNAVAILABLE' OR source = 'MANUAL')
);

-- 패치 좌표 기록. 패치 검사 범위 제외로 신규 기록 중단, 과거 기록만 보존
CREATE TABLE defect_detection (
    id               CHAR(36)      NOT NULL PRIMARY KEY,
    inspection_id    CHAR(36)      NOT NULL,
    patch_id         VARCHAR(50)   NOT NULL,
    location_type    VARCHAR(20)   NOT NULL,
    coordinates_json JSON          NOT NULL,
    patch_score      DECIMAL(7, 6) NOT NULL,
    defect_type      VARCHAR(50)   NOT NULL,
    CONSTRAINT uq_detection_patch UNIQUE (inspection_id, patch_id),
    CONSTRAINT fk_detection_insp FOREIGN KEY (inspection_id) REFERENCES inspection (id)
);

-- REVIEW 건의 작업자 최종 판정. 검사당 최대 1건
CREATE TABLE worker_confirmation (
    id              CHAR(36)     NOT NULL PRIMARY KEY,
    inspection_id   CHAR(36)     NOT NULL UNIQUE,
    worker_id       CHAR(36)     NOT NULL,
    final_judgement VARCHAR(10)  NOT NULL,
    confirmed_at    DATETIME(6)  NOT NULL,
    comment         VARCHAR(200) NULL,                         -- V4: 작업자 메모 (선택)
    CONSTRAINT fk_confirm_insp FOREIGN KEY (inspection_id) REFERENCES inspection (id),
    CONSTRAINT fk_confirm_worker FOREIGN KEY (worker_id) REFERENCES users (id),
    CONSTRAINT chk_confirm_judgement CHECK (final_judgement IN ('PASS', 'FAIL'))                 -- V5
);

-- 원본·Grad-CAM 이미지 참조. 검사당 원본 1, Grad-CAM 최대 1
-- storage_uri는 저장소 상대 키 (예: original/2026/10/16/<id>.jpg). 만료되는 접근 주소는 저장하지 않음
CREATE TABLE image_storage (
    id               CHAR(36)     NOT NULL PRIMARY KEY,
    inspection_id    CHAR(36)     NOT NULL,                    -- V4: 단일 UNIQUE 제거
    image_type       VARCHAR(10)  NOT NULL DEFAULT 'ORIGINAL', -- V4: ORIGINAL, GRADCAM
    storage_uri      VARCHAR(500) NOT NULL,
    content_type     VARCHAR(50)  NOT NULL,
    size_bytes       BIGINT       NOT NULL,
    width            INT          NOT NULL,
    height           INT          NOT NULL,
    checksum         CHAR(64)     NOT NULL,                    -- SHA-256
    created_at       DATETIME(6)  NOT NULL,
    exif_orientation INT          NULL,                        -- V4
    CONSTRAINT uq_image_insp_type UNIQUE (inspection_id, image_type),
    CONSTRAINT fk_image_insp FOREIGN KEY (inspection_id) REFERENCES inspection (id),
    CONSTRAINT chk_image_type CHECK (image_type IN ('ORIGINAL', 'GRADCAM')),                     -- V4
    CONSTRAINT chk_image_size CHECK (width > 0 AND height > 0 AND size_bytes > 0),               -- V5
    CONSTRAINT chk_image_exif CHECK (exif_orientation IS NULL OR (exif_orientation >= 1 AND exif_orientation <= 8))  -- V5
);
