package com.capstone.inspection.integration;

import com.capstone.inspection.common.time.Times;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MvcResult;

import java.time.OffsetDateTime;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

// 계약 6.9.1 정책 후보 비교: 예시 정책 example-door-p1(0.05)과 같은 모델·보정기의 검사로 계산
class PolicySimulationIntegrationTest extends IntegrationTestBase {

    private String exampleId() {
        return jdbc.queryForObject("select id from automation_policy where policy_version = 'example-door-p1'",
                String.class);
    }

    private String submitGood(double calibrated) throws Exception {
        ai = r -> response(r, "GOOD", 0.1, calibrated);
        return submitAndWait().path("inspectionId").asText();
    }

    private void confirm(String id, String judgement) throws Exception {
        assertThat(postJson("/api/v1/inspections/" + id + "/confirm", Map.of("finalJudgement", judgement), worker())
                .getResponse().getStatus()).isEqualTo(200);
    }

    private MvcResult simulate(String policyId, String candidate, String from, String token) throws Exception {
        return call(get("/api/v1/admin/policies/" + policyId + "/simulation")
                .param("candidateThreshold", candidate).param("from", from), token);
    }

    @Test
    @DisplayName("기준 상향 후보: 새로 통과할 건의 작업자 PASS·FAIL·미확인, 기존 기록은 바뀌지 않음")
    void raiseCandidate() throws Exception {
        String from = OffsetDateTime.now(Times.ZONE).toString();
        submitGood(0.021);                       // AUTO_PASS
        String pass = submitGood(0.06);          // REVIEW → 작업자 PASS
        String fail = submitGood(0.07);          // REVIEW → 작업자 FAIL
        submitGood(0.075);                       // REVIEW 판정 전
        submitGood(0.2);                         // 후보에서도 REVIEW
        confirm(pass, "PASS");
        confirm(fail, "FAIL");
        long before = jdbc.queryForObject("select count(*) from inspection where final_judgement is not null",
                Long.class);

        MvcResult result = simulate(exampleId(), "0.08", from, admin());

        assertThat(result.getResponse().getStatus()).isEqualTo(200);
        JsonNode data = json(result).path("data");
        assertThat(data.path("policyVersion").asText()).isEqualTo("example-door-p1");
        assertThat(data.path("currentThreshold").asDouble()).isEqualTo(0.05);
        assertThat(data.path("candidateWithinValidatedRange").asBoolean()).isTrue();
        assertThat(data.path("evaluatedCount").asLong()).isEqualTo(5);
        assertThat(data.at("/current/autoPassCount").asLong()).isEqualTo(1);
        assertThat(data.at("/candidate/autoPassCount").asLong()).isEqualTo(4);
        JsonNode change = data.path("change");
        assertThat(change.path("direction").asText()).isEqualTo("REVIEW_TO_AUTO_PASS");
        assertThat(change.path("count").asLong()).isEqualTo(3);
        assertThat(change.path("workerPass").asLong()).isEqualTo(1);
        assertThat(change.path("workerFail").asLong()).isEqualTo(1);
        assertThat(change.path("unverified").asLong()).isEqualTo(1);
        assertThat(change.at("/items/0/calibratedDefectProbability").asDouble()).isEqualTo(0.075);
        assertThat(change.at("/items/1/label").asText()).isEqualTo("WORKER_FAIL");
        // 조회만 함
        assertThat(jdbc.queryForObject("select count(*) from inspection where final_judgement is not null",
                Long.class)).isEqualTo(before);
    }

    @Test
    @DisplayName("기준 하향 후보: 새로 REVIEW가 되는 AUTO_PASS 건은 미확인, 검증 범위 밖 표시")
    void lowerCandidate() throws Exception {
        String from = OffsetDateTime.now(Times.ZONE).toString();
        submitGood(0.021);
        submitGood(0.04);

        JsonNode data = json(simulate(exampleId(), "0.01", from, admin())).path("data");

        assertThat(data.at("/change/direction").asText()).isEqualTo("AUTO_PASS_TO_REVIEW");
        assertThat(data.at("/change/count").asLong()).isEqualTo(2);
        assertThat(data.at("/change/unverified").asLong()).isEqualTo(2);
        assertThat(data.path("candidateWithinValidatedRange").asBoolean()).isFalse();
    }

    @Test
    @DisplayName("오류: 없는 정책 404, 후보 1 초과·기간 역순 400, WORKER 403")
    void errors() throws Exception {
        String from = OffsetDateTime.now(Times.ZONE).toString();
        assertThat(errorCode(simulate("nope", "0.05", from, admin()))).isEqualTo("POLICY_NOT_FOUND");
        MvcResult outOfRange = simulate(exampleId(), "1.5", from, admin());
        assertThat(outOfRange.getResponse().getStatus()).isEqualTo(400);
        assertThat(errorCode(outOfRange)).isEqualTo("INVALID_PARAMETER");
        MvcResult reversed = call(get("/api/v1/admin/policies/" + exampleId() + "/simulation")
                .param("candidateThreshold", "0.05").param("from", from)
                .param("to", OffsetDateTime.now(Times.ZONE).minusDays(1).toString()), admin());
        assertThat(errorCode(reversed)).isEqualTo("INVALID_PARAMETER");
        assertThat(simulate(exampleId(), "0.05", from, worker()).getResponse().getStatus()).isEqualTo(403);
    }
}
