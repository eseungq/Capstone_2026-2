package com.capstone.inspection.integration;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MvcResult;

import java.util.Map;
import java.util.stream.StreamSupport;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

// 계약 6.11 AUTO_PASS 표본 재확인. 결과가 정해지도록 NEAR·MID는 항상, LOW는 뽑지 않게 설정
//   예시 정책 example-door-p1 기준치 0.05: 0.045 → NEAR(r 0.9), 0.01 → LOW(r 0.2)
@TestPropertySource(properties = {"app.recheck.near-rate=1.0", "app.recheck.mid-rate=1.0", "app.recheck.low-rate=0"})
class RecheckIntegrationTest extends IntegrationTestBase {

    private String submitGood(double calibrated) throws Exception {
        ai = r -> response(r, "GOOD", 0.1, calibrated);
        return submitAndWait().path("inspectionId").asText();
    }

    private JsonNode detail(String id) throws Exception {
        return json(call(get("/api/v1/inspections/" + id), worker())).path("data");
    }

    private MvcResult recheck(String id, String result, String token) throws Exception {
        return postJson("/api/v1/inspections/" + id + "/recheck", Map.of("result", result, "comment", "고정핀 들뜸"),
                token);
    }

    private boolean listed(String status, String inspectionId) throws Exception {
        JsonNode items = json(call(get("/api/v1/rechecks").param("status", status).param("size", "100"), worker()))
                .at("/data/items");
        return StreamSupport.stream(items.spliterator(), false)
                .anyMatch(n -> n.path("inspectionId").asText().equals(inspectionId));
    }

    @Test
    @DisplayName("기준 근처 AUTO_PASS는 표본으로 뽑혀 목록·상세에 보이고, 재확인 FAIL이어도 시스템 판정은 PASS·SYSTEM 그대로")
    void sampledAndRechecked() throws Exception {
        String id = submitGood(0.045);

        JsonNode before = detail(id);
        assertThat(before.path("displayState").asText()).isEqualTo("AUTO_PASS");
        assertThat(before.at("/recheck/stratum").asText()).isEqualTo("NEAR");
        assertThat(before.at("/recheck/samplingRate").asDouble()).isEqualTo(1.0);
        assertThat(before.at("/recheck/result").isNull()).isTrue();
        assertThat(listed("PENDING", id)).isTrue();

        MvcResult result = recheck(id, "FAIL", worker());
        assertThat(result.getResponse().getStatus()).isEqualTo(200);
        JsonNode data = json(result).path("data");
        assertThat(data.path("finalJudgement").asText()).isEqualTo("PASS");
        assertThat(data.path("judgedBy").asText()).isEqualTo("SYSTEM");
        assertThat(data.at("/recheck/result").asText()).isEqualTo("FAIL");
        assertThat(data.at("/recheck/recheckedBy").asText()).isEqualTo("worker01");

        JsonNode after = detail(id);
        assertThat(after.path("displayState").asText()).isEqualTo("AUTO_PASS");
        assertThat(after.at("/judgement/finalJudgement").asText()).isEqualTo("PASS");
        assertThat(after.at("/recheck/result").asText()).isEqualTo("FAIL");
        assertThat(after.at("/recheck/comment").asText()).isEqualTo("고정핀 들뜸");
        assertThat(jdbc.queryForObject("select final_judgement from inspection where id = ?", String.class, id))
                .isEqualTo("PASS");
        assertThat(listed("PENDING", id)).isFalse();
        assertThat(listed("DONE", id)).isTrue();

        // 재전송 규칙
        assertThat(recheck(id, "FAIL", worker()).getResponse().getStatus()).isEqualTo(200);
        MvcResult changed = recheck(id, "PASS", worker());
        assertThat(changed.getResponse().getStatus()).isEqualTo(409);
        assertThat(errorCode(changed)).isEqualTo("ALREADY_RECHECKED");
    }

    @Test
    @DisplayName("비율 0인 구간(LOW)과 REVIEW 건은 뽑히지 않고, 재확인 요청은 409 NOT_RECHECKABLE")
    void notSampled() throws Exception {
        String low = submitGood(0.01);
        String review = submitGood(0.2);

        assertThat(detail(low).path("recheck").isNull()).isTrue();
        assertThat(detail(review).path("recheck").isNull()).isTrue();
        assertThat(errorCode(recheck(low, "PASS", worker()))).isEqualTo("NOT_RECHECKABLE");
        assertThat(errorCode(recheck(review, "PASS", worker()))).isEqualTo("NOT_RECHECKABLE");
        assertThat(jdbc.queryForObject("select count(*) from auto_pass_recheck where inspection_id in (?, ?)",
                Long.class, low, review)).isZero();
    }

    @Test
    @DisplayName("권한: 재확인 제출은 WORKER만(ADMIN 403), 목록은 DEVICE 403, 없는 검사 404")
    void access() throws Exception {
        String id = submitGood(0.045);
        assertThat(recheck(id, "PASS", admin()).getResponse().getStatus()).isEqualTo(403);
        assertThat(call(get("/api/v1/rechecks"), device()).getResponse().getStatus()).isEqualTo(403);
        assertThat(call(get("/api/v1/rechecks"), admin()).getResponse().getStatus()).isEqualTo(200);
        assertThat(errorCode(recheck("nope", "PASS", worker()))).isEqualTo("INSPECTION_NOT_FOUND");
    }
}
