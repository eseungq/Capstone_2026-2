package com.capstone.inspection.integration;

import com.capstone.inspection.common.time.Times;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

// 이력·CSV의 mismatch 필터: AI 예측과 작업자 판정이 엇갈린 REVIEW_DONE 건
class MismatchIntegrationTest extends IntegrationTestBase {

    private String from;
    private String defectPassed;
    private String goodFailed;
    private String defectFailed;
    private String goodPassed;
    private String defectPending;
    private String autoPass;
    private String manual;

    @BeforeEach
    void seed() throws Exception {
        // 이 테스트에서 만든 검사만 대상이 되도록 접수 직전 시각부터 조회
        from = OffsetDateTime.now(Times.ZONE).toString();
        autoPass = submitAndWait().path("inspectionId").asText();

        ai = r -> response(r, "DEFECT", 0.8, 0.8);
        defectPassed = reviewed("PASS");
        defectFailed = reviewed("FAIL");
        defectPending = submitAndWait().path("inspectionId").asText();

        ai = goodAboveThreshold();
        goodFailed = reviewed("FAIL");
        goodPassed = reviewed("PASS");

        // 수동 판정: AI 예측이 없어 어떤 판정이어도 제외
        ai = aiServerError();
        String failed = submitAndWait().path("inspectionId").asText();
        manual = json(call(post("/api/v1/inspections/" + failed + "/manual"), worker())).at("/data/inspectionId").asText();
        confirm(manual, "FAIL");
    }

    private String reviewed(String judgement) throws Exception {
        String id = submitAndWait().path("inspectionId").asText();
        confirm(id, judgement);
        return id;
    }

    private void confirm(String id, String judgement) throws Exception {
        MvcResult result = postJson("/api/v1/inspections/" + id + "/confirm", Map.of("finalJudgement", judgement), worker());
        assertThat(result.getResponse().getStatus()).isEqualTo(200);
    }

    // params: 이름, 값, 이름, 값 ... (from·size는 자동)
    private List<String> history(String token, String mismatch, String... params) throws Exception {
        MockHttpServletRequestBuilder request = get("/api/v1/inspections").param("from", from)
                .param("mismatch", mismatch).param("size", "100");
        for (int p = 0; p < params.length; p += 2) {
            request.param(params[p], params[p + 1]);
        }
        MvcResult result = call(request, token);
        assertThat(result.getResponse().getStatus()).isEqualTo(200);
        List<String> ids = new ArrayList<>();
        for (JsonNode item : json(result).at("/data/items")) {
            ids.add(item.path("inspectionId").asText());
        }
        return ids;
    }

    private String no(String inspectionId) {
        return jdbc.queryForObject("select inspection_no from inspection where id = ?", String.class, inspectionId);
    }

    @Test
    @DisplayName("ANY는 엇갈린 두 유형만, 일치·확인 전·AUTO_PASS·수동 판정은 제외")
    void anyMismatch() throws Exception {
        assertThat(history(admin(), "ANY")).containsExactlyInAnyOrder(defectPassed, goodFailed)
                .doesNotContain(defectFailed, goodPassed, defectPending, autoPass, manual);
        // 작업자도 이력과 같은 범위로 조회
        assertThat(history(worker(), "ANY")).containsExactlyInAnyOrder(defectPassed, goodFailed);
    }

    @Test
    @DisplayName("유형별: DEFECT_PASSED는 AI 불량→PASS, GOOD_FAILED는 AI 정상→FAIL")
    void byType() throws Exception {
        assertThat(history(admin(), "DEFECT_PASSED")).containsExactly(defectPassed);
        assertThat(history(admin(), "GOOD_FAILED")).containsExactly(goodFailed);
    }

    @Test
    @DisplayName("다른 조건과 함께: REVIEW_DONE은 결과 같음, 다른 displayState·부품은 빈 결과, 빈 값은 필터 없음")
    void withOtherFilters() throws Exception {
        assertThat(history(admin(), "ANY", "displayState", "REVIEW_DONE"))
                .containsExactlyInAnyOrder(defectPassed, goodFailed);
        assertThat(history(admin(), "ANY", "displayState", "AUTO_PASS")).isEmpty();
        assertThat(history(admin(), "ANY", "partCode", "FRAME")).isEmpty();
        assertThat(history(admin(), "")).contains(autoPass, defectPending, goodPassed);
    }

    @Test
    @DisplayName("CSV 내보내기에도 같은 필터")
    void exportMismatch() throws Exception {
        MvcResult result = call(get("/api/v1/admin/inspections/export").param("from", from).param("mismatch", "ANY"), admin());
        assertThat(result.getResponse().getStatus()).isEqualTo(200);
        String csv = new String(result.getResponse().getContentAsByteArray(), StandardCharsets.UTF_8);
        String[] lines = csv.substring(1).split("\r\n");
        assertThat(lines).hasSize(3); // 머리글 + 2건
        assertThat(csv).contains(no(defectPassed) + ",", no(goodFailed) + ",")
                .doesNotContain(no(defectFailed) + ",", no(goodPassed) + ",", no(manual) + ",");
    }

    @Test
    @DisplayName("없는 mismatch 값은 400")
    void invalidMismatch() throws Exception {
        for (String url : List.of("/api/v1/inspections", "/api/v1/admin/inspections/export")) {
            MvcResult result = call(get(url).param("mismatch", "WRONG"), admin());
            assertThat(result.getResponse().getStatus()).isEqualTo(400);
            assertThat(errorCode(result)).isEqualTo("INVALID_PARAMETER");
        }
    }
}
