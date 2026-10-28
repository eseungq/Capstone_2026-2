-- 요구사항 명세서 8.1 속성 정의 기준 초기 스키마
-- 모든 식별자는 UUID 문자열(CHAR(36))

CREATE TABLE users (
    id                 CHAR(36)     NOT NULL PRIMARY KEY,
    login_id           VARCHAR(50)  NOT NULL UNIQUE,
    password_hash      VARCHAR(100) NOT NULL,
    role               VARCHAR(10)  NOT NULL,              -- WORKER, ADMIN
    failed_login_count INT          NOT NULL DEFAULT 0,    -- 잠금 기준은 TBD-10
    locked             BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at         DATETIME(6)  NOT NULL
);

CREATE TABLE part (
    id        CHAR(36)    NOT NULL PRIMARY KEY,
    part_code VARCHAR(30) NOT NULL UNIQUE,
    name      VARCHAR(50) NOT NULL
);

CREATE TABLE inspection_item (
    id        CHAR(36)    NOT NULL PRIMARY KEY,
    part_id   CHAR(36)    NOT NULL,
    item_code VARCHAR(30) NOT NULL,                        -- 코드표는 TBD-04
    name      VARCHAR(50) NOT NULL,
    CONSTRAINT uq_item_part_code UNIQUE (part_id, item_code),
    CONSTRAINT fk_item_part FOREIGN KEY (part_id) REFERENCES part (id)
);

-- 검사항목당 active 모델 1개는 서비스에서 보장
CREATE TABLE ai_model (
    id                         CHAR(36)     NOT NULL PRIMARY KEY,
    item_id                    CHAR(36)     NOT NULL,
    model_version              VARCHAR(100) NOT NULL UNIQUE,
    pipeline_config_json       JSON         NOT NULL,      -- 전처리·패치·집계·보정 설정
    checksum                   VARCHAR(128) NOT NULL,
    metrics_json               JSON         NULL,
    patch_inspection_supported BOOLEAN      NOT NULL,
    active                     BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at                 DATETIME(6)  NOT NULL,
    CONSTRAINT fk_model_item FOREIGN KEY (item_id) REFERENCES inspection_item (id)
);

-- 검사항목·모델 버전당 active 정책 1개, ready=true만 active는 서비스에서 보장
CREATE TABLE automation_policy (
    id               CHAR(36)     NOT NULL PRIMARY KEY,
    model_id         CHAR(36)     NOT NULL,
    item_id          CHAR(36)     NOT NULL,
    policy_version   VARCHAR(100) NOT NULL UNIQUE,
    target_miss_rate DECIMAL(6, 5) NOT NULL,
    pass_threshold   DECIMAL(7, 6) NULL,                   -- ready가 아니면 null 가능
    metrics_json     JSON         NOT NULL,                -- 관측 미검출률·신뢰 상한·자동화율·표본 수
    ready            BOOLEAN      NOT NULL,
    active           BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at       DATETIME(6)  NOT NULL,
    CONSTRAINT fk_policy_model FOREIGN KEY (model_id) REFERENCES ai_model (id),
    CONSTRAINT fk_policy_item FOREIGN KEY (item_id) REFERENCES inspection_item (id)
);

CREATE TABLE inspection (
    id                            CHAR(36)     NOT NULL PRIMARY KEY,
    user_id                       CHAR(36)     NOT NULL,
    part_id                       CHAR(36)     NOT NULL,
    item_id                       CHAR(36)     NOT NULL,
    model_id                      CHAR(36)     NOT NULL,
    policy_id                     CHAR(36)     NULL,       -- 적용 정책 없으면 null
    status                        VARCHAR(20)  NOT NULL,   -- ANALYZING, COMPLETED, FAILED
    predicted_quality             VARCHAR(10)  NULL,       -- GOOD, DEFECT
    raw_defect_probability        DECIMAL(7, 6) NULL,      -- 명칭은 TBD-07
    calibrated_defect_probability DECIMAL(7, 6) NULL,
    patch_inspection_supported    BOOLEAN      NULL,
    automation_policy_ready       BOOLEAN      NOT NULL DEFAULT FALSE,
    recommended_action            VARCHAR(20)  NULL,       -- AUTO_PASS, REVIEW (COMPLETED에서만)
    final_judgement               VARCHAR(10)  NULL,       -- PASS, FAIL
    inference_time_ms             INT          NULL,
    error_code                    VARCHAR(40)  NULL,       -- FAILED 사유
    created_at                    DATETIME(6)  NOT NULL,
    completed_at                  DATETIME(6)  NULL,
    CONSTRAINT fk_insp_user FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT fk_insp_part FOREIGN KEY (part_id) REFERENCES part (id),
    CONSTRAINT fk_insp_item FOREIGN KEY (item_id) REFERENCES inspection_item (id),
    CONSTRAINT fk_insp_model FOREIGN KEY (model_id) REFERENCES ai_model (id),
    CONSTRAINT fk_insp_policy FOREIGN KEY (policy_id) REFERENCES automation_policy (id),
    INDEX idx_insp_user_created (user_id, created_at),
    INDEX idx_insp_part_item_created (part_id, item_id, created_at)
);

CREATE TABLE defect_detection (
    id               CHAR(36)     NOT NULL PRIMARY KEY,
    inspection_id    CHAR(36)     NOT NULL,
    patch_id         VARCHAR(50)  NOT NULL,
    location_type    VARCHAR(20)  NOT NULL,                -- PATCH_BBOX
    coordinates_json JSON         NOT NULL,                -- 정규화 [x, y, w, h]
    patch_score      DECIMAL(7, 6) NOT NULL,
    defect_type      VARCHAR(50)  NOT NULL,
    CONSTRAINT uq_detection_patch UNIQUE (inspection_id, patch_id),
    CONSTRAINT fk_detection_insp FOREIGN KEY (inspection_id) REFERENCES inspection (id)
);

CREATE TABLE worker_confirmation (
    id              CHAR(36)    NOT NULL PRIMARY KEY,
    inspection_id   CHAR(36)    NOT NULL UNIQUE,           -- 검사당 최대 1건
    worker_id       CHAR(36)    NOT NULL,
    final_judgement VARCHAR(10) NOT NULL,
    confirmed_at    DATETIME(6) NOT NULL,
    CONSTRAINT fk_confirm_insp FOREIGN KEY (inspection_id) REFERENCES inspection (id),
    CONSTRAINT fk_confirm_worker FOREIGN KEY (worker_id) REFERENCES users (id)
);

CREATE TABLE image_storage (
    id            CHAR(36)     NOT NULL PRIMARY KEY,
    inspection_id CHAR(36)     NOT NULL UNIQUE,            -- 검사당 원본 1건
    storage_uri   VARCHAR(500) NOT NULL,
    content_type  VARCHAR(50)  NOT NULL,
    size_bytes    BIGINT       NOT NULL,
    width         INT          NOT NULL,
    height        INT          NOT NULL,
    checksum      CHAR(64)     NOT NULL,                   -- SHA-256
    created_at    DATETIME(6)  NOT NULL,
    CONSTRAINT fk_image_insp FOREIGN KEY (inspection_id) REFERENCES inspection (id)
);
