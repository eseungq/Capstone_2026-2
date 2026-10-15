-- 개발·시연용 테스트 계정 (운영 배포 시 db/seed-dev 위치를 flyway.locations에서 제외)
-- 비밀번호: worker01 / Worker1234!, admin01 / Admin1234!, device-door / Device1234!
INSERT INTO users (id, login_id, password_hash, role, failed_login_count, locked, created_at) VALUES
    (UUID(), 'worker01',    '$2a$10$gk7qN/4tZxlTFMjzFsFV7emONIp0IHRQF/i3CVCfld.Ui11LtP7UK', 'WORKER', 0, FALSE, NOW(6)),
    (UUID(), 'admin01',     '$2a$10$dCG0c4aGp00jboN0dNMVoukFTDVANituFSAWalvuqKSERoAtK6Kg2', 'ADMIN',  0, FALSE, NOW(6)),
    (UUID(), 'device-door', '$2a$10$VjUAg0BXOwwVQXsUT.c2ZeXGMBEwzH37nm370CVsYxzpJ/UrQ.jW2', 'DEVICE', 0, FALSE, NOW(6));
