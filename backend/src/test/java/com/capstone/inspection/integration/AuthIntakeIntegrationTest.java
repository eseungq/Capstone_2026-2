package com.capstone.inspection.integration;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MvcResult;

import java.util.Map;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

// 계약 v4 6.1 로그인 잠금·관리자 해제·토큰 회전, 6.2 사진 접수 검증·Idempotency-Key
class AuthIntakeIntegrationTest extends IntegrationTestBase {

    @Autowired
    private PasswordEncoder passwordEncoder;

    // 공용 시드 계정은 다른 테스트가 쓰므로 잠금 시험용 WORKER를 따로 만듦
    private String createWorker(String password) {
        String loginId = unique("lock");
        jdbc.update("""
                insert into users (id, login_id, password_hash, role, failed_login_count, locked, created_at)
                values (?, ?, ?, 'WORKER', 0, false, now(6))""",
                UUID.randomUUID().toString(), loginId, passwordEncoder.encode(password));
        return loginId;
    }

    // 토큰 없이 호출하는 공개 API (로그인·재발급)
    private MvcResult postPublic(String url, Object body) throws Exception {
        return mvc.perform(post(url).contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsString(body)))
                .andReturn();
    }

    private MvcResult login(String loginId, String password) throws Exception {
        return postPublic("/api/v1/auth/login", Map.of("loginId", loginId, "password", password));
    }

    @Test
    @DisplayName("로그인 5회 실패 시 423 잠금, 맞는 비밀번호도 거절 → ADMIN 해제 후 로그인 성공")
    void lockAndUnlock() throws Exception {
        String loginId = createWorker("Right1234!");
        for (int i = 1; i <= 4; i++) {
            assertThat(login(loginId, "wrong").getResponse().getStatus()).isEqualTo(401);
        }
        MvcResult fifth = login(loginId, "wrong");
        assertThat(fifth.getResponse().getStatus()).isEqualTo(423);
        assertThat(errorCode(fifth)).isEqualTo("AUTH_ACCOUNT_LOCKED");
        assertThat(login(loginId, "Right1234!").getResponse().getStatus()).isEqualTo(423);

        assertThat(postJson("/api/v1/admin/users/" + loginId + "/unlock", Map.of(), worker()).getResponse().getStatus())
                .isEqualTo(403);
        MvcResult unlocked = postJson("/api/v1/admin/users/" + loginId + "/unlock", Map.of(), admin());
        assertThat(unlocked.getResponse().getStatus()).isEqualTo(200);
        assertThat(json(unlocked).at("/data/locked").asBoolean()).isFalse();
        assertThat(json(unlocked).at("/data/failedLoginCount").asInt()).isZero();

        assertThat(login(loginId, "Right1234!").getResponse().getStatus()).isEqualTo(200);
    }

    @Test
    @DisplayName("없는 계정 잠금 해제는 404 USER_NOT_FOUND")
    void unlockUnknownUser() throws Exception {
        MvcResult result = postJson("/api/v1/admin/users/no-such-user/unlock", Map.of(), admin());
        assertThat(result.getResponse().getStatus()).isEqualTo(404);
        assertThat(errorCode(result)).isEqualTo("USER_NOT_FOUND");
    }

    @Test
    @DisplayName("토큰 재발급은 회전: 새 토큰 발급, 이미 쓴 리프레시 토큰 재사용은 401")
    void refreshRotation() throws Exception {
        String loginId = createWorker("Right1234!");
        String refresh = json(login(loginId, "Right1234!")).at("/data/refreshToken").asText();

        MvcResult first = postPublic("/api/v1/auth/refresh", Map.of("refreshToken", refresh));
        assertThat(first.getResponse().getStatus()).isEqualTo(200);
        String rotated = json(first).at("/data/refreshToken").asText();
        assertThat(rotated).isNotEqualTo(refresh);

        MvcResult reused = postPublic("/api/v1/auth/refresh", Map.of("refreshToken", refresh));
        assertThat(reused.getResponse().getStatus()).isEqualTo(401);
        assertThat(errorCode(reused)).isEqualTo("AUTH_TOKEN_INVALID");

        assertThat(postPublic("/api/v1/auth/refresh", Map.of("refreshToken", rotated)).getResponse().getStatus())
                .isEqualTo(200);
    }

    private MvcResult submitBytes(byte[] bytes, String partCode, String idempotencyKey) throws Exception {
        var request = multipart("/api/v1/inspections")
                .file(new MockMultipartFile("image", "t.png", "image/png", bytes)).param("partCode", partCode);
        if (idempotencyKey != null) {
            request.header("Idempotency-Key", idempotencyKey);
        }
        return call(request, device());
    }

    @Test
    @DisplayName("사진이 아니면 400 INVALID_IMAGE_FORMAT, 없는 부품이면 400 INVALID_PART_CODE. 둘 다 검사 기록 없음")
    void intakeValidation() throws Exception {
        long before = inspectionCount();

        MvcResult notImage = submitBytes("not an image".getBytes(), "DOOR", null);
        assertThat(notImage.getResponse().getStatus()).isEqualTo(400);
        assertThat(errorCode(notImage)).isEqualTo("INVALID_IMAGE_FORMAT");

        byte[] image = imageBytes();
        MvcResult badPart = submitBytes(image, "NO_SUCH_PART", null);
        assertThat(badPart.getResponse().getStatus()).isEqualTo(400);
        assertThat(errorCode(badPart)).isEqualTo("INVALID_PART_CODE");

        assertThat(inspectionCount()).isEqualTo(before);
    }

    @Test
    @DisplayName("같은 Idempotency-Key·같은 사진 재전송은 200 기존 검사, 다른 부품이면 422")
    void idempotency() throws Exception {
        String key = unique("idem");
        byte[] image = imageBytes();

        MvcResult first = submitBytes(image, "DOOR", key);
        assertThat(first.getResponse().getStatus()).isEqualTo(202);
        String id = json(first).at("/data/inspectionId").asText();
        long count = inspectionCount();

        MvcResult replay = submitBytes(image, "DOOR", key);
        assertThat(replay.getResponse().getStatus()).isEqualTo(200);
        assertThat(json(replay).at("/data/inspectionId").asText()).isEqualTo(id);
        assertThat(inspectionCount()).isEqualTo(count);

        String otherPart = jdbc.queryForObject("select part_code from part where part_code <> 'DOOR' limit 1", String.class);
        MvcResult mismatch = submitBytes(image, otherPart, key);
        assertThat(mismatch.getResponse().getStatus()).isEqualTo(422);
        assertThat(errorCode(mismatch)).isEqualTo("IDEMPOTENCY_KEY_MISMATCH");

        JsonNode done = waitFinished(id);
        assertThat(done.path("status").asText()).isEqualTo("COMPLETED");
    }
}
