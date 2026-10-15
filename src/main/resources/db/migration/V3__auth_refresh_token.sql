-- V3: 인증 (명세서 FR-BE-01, 계약 v4 2장)
-- Refresh Token은 원문 대신 SHA-256 해시만 저장하고, 로그아웃·재발급 시 revoked_at으로 폐기
-- users.role 값: WORKER, ADMIN, DEVICE(사진 입력 프로그램, 검사 접수 전용)

CREATE TABLE refresh_token (
    id         CHAR(36)    NOT NULL PRIMARY KEY,
    user_id    CHAR(36)    NOT NULL,
    token_hash CHAR(64)    NOT NULL UNIQUE,              -- SHA-256 hex
    expires_at DATETIME(6) NOT NULL,
    revoked_at DATETIME(6) NULL,                         -- 폐기 시각, 사용 가능하면 null
    created_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_refresh_user FOREIGN KEY (user_id) REFERENCES users (id),
    INDEX idx_refresh_user (user_id)
);

ALTER TABLE users
    ADD CONSTRAINT chk_users_role CHECK (role IN ('WORKER', 'ADMIN', 'DEVICE'));
