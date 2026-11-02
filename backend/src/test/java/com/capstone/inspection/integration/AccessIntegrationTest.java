package com.capstone.inspection.integration;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MvcResult;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

// 계약 v4 6.1 권한, 8장 기기 토큰
class AccessIntegrationTest extends IntegrationTestBase {

    private static final String TOKEN = "ExponentPushToken[integration]";
    private static final String DEVICES = "/api/v1/notifications/devices";

    private void assertDenied(MvcResult result) throws Exception {
        assertThat(result.getResponse().getStatus()).isEqualTo(403);
        assertThat(errorCode(result)).isEqualTo("ACCESS_DENIED");
    }

    @Test
    @DisplayName("WORKER의 관리자 API는 403")
    void workerAdminApi() throws Exception {
        assertDenied(call(get("/api/v1/admin/models"), worker()));
        assertDenied(call(get("/api/v1/admin/policies"), worker()));
        assertDenied(call(post("/api/v1/admin/policies/x/activate"), worker()));
    }

    @Test
    @DisplayName("ADMIN의 confirm은 403")
    void adminConfirm() throws Exception {
        ai = goodAboveThreshold();
        String id = submitAndWait().path("inspectionId").asText();
        assertDenied(postJson("/api/v1/inspections/" + id + "/confirm", Map.of("finalJudgement", "PASS"), admin()));
    }

    @Test
    @DisplayName("DEVICE의 조회·알림·관리자 API는 403")
    void deviceReadApi() throws Exception {
        assertDenied(call(get("/api/v1/inspections"), device()));
        assertDenied(call(get("/api/v1/parts"), device()));
        assertDenied(call(get("/api/v1/monitoring/parts"), device()));
        assertDenied(call(get("/api/v1/admin/policies"), device()));
        assertDenied(postJson(DEVICES, Map.of("token", TOKEN, "platform", "IOS"), device()));
    }

    @Test
    @DisplayName("토큰 없으면 401")
    void noToken() throws Exception {
        assertThat(mvc.perform(get("/api/v1/admin/models")).andReturn().getResponse().getStatus()).isEqualTo(401);
    }

    private long tokenCount() {
        return jdbc.queryForObject("select count(*) from device_token where token = ?", Long.class, TOKEN);
    }

    @Test
    @DisplayName("기기 토큰: 같은 토큰 재등록은 행 1개로 소유자·플랫폼 갱신, 형식 오류 400")
    void deviceRegister() throws Exception {
        assertThat(postJson(DEVICES, Map.of("token", TOKEN, "platform", "IOS"), worker()).getResponse().getStatus())
                .isEqualTo(204);
        assertThat(postJson(DEVICES, Map.of("token", TOKEN, "platform", "ANDROID"), admin()).getResponse().getStatus())
                .isEqualTo(204);
        Map<String, Object> row = jdbc.queryForMap("""
                select u.login_id, d.platform from device_token d join users u on u.id = d.user_id where d.token = ?""", TOKEN);
        assertThat(row).containsEntry("login_id", "admin01").containsEntry("platform", "ANDROID");
        assertThat(tokenCount()).isEqualTo(1);

        MvcResult invalid = postJson(DEVICES, Map.of("token", "not-a-token", "platform", "IOS"), worker());
        assertThat(invalid.getResponse().getStatus()).isEqualTo(400);
        assertThat(errorCode(invalid)).isEqualTo("INVALID_DEVICE_TOKEN");
    }

    @Test
    @DisplayName("기기 토큰 해제: 본인 것만 지워지고 없어도 204")
    void deviceDelete() throws Exception {
        postJson(DEVICES, Map.of("token", TOKEN, "platform", "IOS"), worker());
        assertThat(call(delete(DEVICES + "/{token}", TOKEN), admin()).getResponse().getStatus()).isEqualTo(204);
        assertThat(tokenCount()).isEqualTo(1);
        assertThat(call(delete(DEVICES + "/{token}", TOKEN), worker()).getResponse().getStatus()).isEqualTo(204);
        assertThat(tokenCount()).isZero();
        assertThat(call(delete(DEVICES + "/{token}", TOKEN), worker()).getResponse().getStatus()).isEqualTo(204);
    }

    @Test
    @DisplayName("로그아웃의 deviceToken으로 함께 해제")
    void logoutReleases() throws Exception {
        postJson(DEVICES, Map.of("token", TOKEN, "platform", "IOS"), worker());
        assertThat(postJson("/api/v1/auth/logout", Map.of("deviceToken", TOKEN), worker()).getResponse().getStatus())
                .isEqualTo(204);
        assertThat(tokenCount()).isZero();
    }
}
