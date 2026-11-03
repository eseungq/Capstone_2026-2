package com.capstone.inspection.integration;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MvcResult;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

// 계약 v4 6.1, 6.2 모델 로드 확인 결과별 접수·표시
class ModelCheckIntegrationTest extends IntegrationTestBase {

    private JsonNode partsDoor() throws Exception {
        for (JsonNode part : json(call(get("/api/v1/parts"), worker())).path("data")) {
            if (part.path("partCode").asText().equals("DOOR")) {
                return part.path("items").get(0);
            }
        }
        throw new AssertionError("DOOR 없음");
    }

    private boolean monitoringDoorAvailable() throws Exception {
        for (JsonNode part : json(call(get("/api/v1/monitoring/parts"), worker())).path("data")) {
            if (part.path("partCode").asText().equals("DOOR")) {
                return part.path("modelAvailable").asBoolean();
            }
        }
        throw new AssertionError("DOOR 없음");
    }

    @Test
    @DisplayName("AVAILABLE: 접수 202, /parts·모니터링 모두 true")
    void available() throws Exception {
        assertThat(partsDoor().path("modelAvailable").asBoolean()).isTrue();
        assertThat(partsDoor().path("policyActive").asBoolean()).isTrue();
        assertThat(partsDoor().has("patchInspectionSupported")).isFalse();
        assertThat(monitoringDoorAvailable()).isTrue();
        assertThat(submit().getResponse().getStatus()).isEqualTo(202);
    }

    @Test
    @DisplayName("NOT_LOADABLE(loadable=false): 접수 422, 기록 없음, /parts·모니터링 false")
    void notLoadable() throws Exception {
        aiModels = () -> Map.of(MOCK_MODEL, false);
        long before = inspectionCount();
        MvcResult result = submit();
        assertThat(result.getResponse().getStatus()).isEqualTo(422);
        assertThat(errorCode(result)).isEqualTo("MODEL_NOT_AVAILABLE");
        assertThat(inspectionCount()).isEqualTo(before);
        assertThat(partsDoor().path("modelAvailable").asBoolean()).isFalse();
        assertThat(monitoringDoorAvailable()).isFalse();
    }

    @Test
    @DisplayName("NOT_LOADABLE(목록에 없음): 접수 422")
    void notListed() throws Exception {
        aiModels = () -> Map.of(REAL_MODEL, true);
        assertThat(submit().getResponse().getStatus()).isEqualTo(422);
    }

    @Test
    @DisplayName("UNKNOWN(조회 실패): 접수 202 → AI 오류면 FAILED, /parts false, 사진 기록 남음")
    void unknown() throws Exception {
        aiModels = () -> {
            throw new IllegalStateException("AI 꺼짐");
        };
        ai = aiServerError();
        JsonNode detail = submitAndWait();
        assertThat(detail.path("status").asText()).isEqualTo("FAILED");
        assertThat(detail.at("/error/code").asText()).isEqualTo("AI_SERVER_ERROR");
        assertThat(detail.at("/images/original/url").asText()).isNotEmpty();
        assertThat(partsDoor().path("modelAvailable").asBoolean()).isFalse();
    }

    @Test
    @DisplayName("재검사도 같은 판단: NOT_LOADABLE 422, UNKNOWN 202")
    void retry() throws Exception {
        ai = aiServerError();
        String id = submitAndWait().path("inspectionId").asText();

        aiModels = () -> Map.of(MOCK_MODEL, false);
        MvcResult rejected = call(post("/api/v1/inspections/" + id + "/retry"), worker());
        assertThat(rejected.getResponse().getStatus()).isEqualTo(422);
        assertThat(errorCode(rejected)).isEqualTo("MODEL_NOT_AVAILABLE");

        aiModels = () -> {
            throw new IllegalStateException("AI 꺼짐");
        };
        ai = goodBelowThreshold();
        assertThat(call(post("/api/v1/inspections/" + id + "/retry"), worker()).getResponse().getStatus()).isEqualTo(202);
    }

    @Test
    @DisplayName("관리자 모델 목록: 확인되면 true·false, 확인 불가면 null")
    void adminModels() throws Exception {
        aiModels = () -> Map.of(MOCK_MODEL, true, REAL_MODEL, false);
        JsonNode models = json(call(get("/api/v1/admin/models"), admin())).path("data");
        assertThat(models).hasSize(3); // Mock·e20·e02 (seed-dev V4_1·V5_1·V5_2)
        for (JsonNode model : models) {
            boolean mock = model.path("modelVersion").asText().equals(MOCK_MODEL);
            assertThat(model.path("loadable").asBoolean()).isEqualTo(mock);
            assertThat(model.path("active").asBoolean()).isEqualTo(mock);
        }
        aiModels = () -> {
            throw new IllegalStateException("AI 꺼짐");
        };
        JsonNode unknown = json(call(get("/api/v1/admin/models"), admin())).path("data");
        assertThat(unknown.get(0).path("loadable").isNull()).isTrue();
    }
}
