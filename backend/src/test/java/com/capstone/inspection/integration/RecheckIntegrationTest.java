package com.capstone.inspection.integration;

import com.capstone.inspection.inspection.RecheckSweeper;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MvcResult;

import java.util.Map;
import java.util.stream.StreamSupport;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

// 계약 6.11 AUTO_PASS 표본 재확인. 결과가 정해지도록 NEAR·MID는 항상, LOW는 뽑지 않게 설정
//   예시 정책 example-door-p1 기준치 0.05: 0.045 → NEAR(r 0.9), 0.01 → LOW(r 0.2)
@TestPropertySource(properties = {"app.recheck.enabled=true", "app.recheck.near-rate=1.0", "app.recheck.mid-rate=1.0", "app.recheck.low-rate=0"})
class RecheckIntegrationTest extends IntegrationTestBase {

    @Autowired
    private RecheckSweeper sweeper;

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
        // LOW는 뽑히지 않았다는 결정이 남고(재처리 대상과 구분), REVIEW는 결정 자체가 없음
        assertThat(sampledFlag(low)).isFalse();
        assertThat(jdbc.queryForObject("select count(*) from auto_pass_recheck where inspection_id = ?",
                Long.class, review)).isZero();
        assertThat(listed("PENDING", low)).isFalse();
    }

    @Test
    @DisplayName("추출 결정 저장이 빠진 AUTO_PASS는 재처리로 같은 결정이 다시 남고, 결정이 있는 건·1일 지난 건은 건드리지 않음")
    void sweepRestoresMissingDecisions() throws Exception {
        String near = submitGood(0.045);
        String low = submitGood(0.01);
        String old = submitGood(0.045);
        // 저장 실패 흉내: 결정 행을 지우고, 분석 직후 대기(SETTLE)가 지난 것처럼 완료 시각을 당김 (DB 시간대와 무관하게 기존 값 기준)
        jdbc.update("delete from auto_pass_recheck where inspection_id in (?, ?, ?)", near, low, old);
        jdbc.update("update inspection set completed_at = completed_at - interval 5 minute where id in (?, ?)", near, low);
        jdbc.update("update inspection set completed_at = completed_at - interval 2 day where id = ?", old);

        assertThat(sweeper.sweep()).isEqualTo(2);
        assertThat(sampledFlag(near)).isTrue();
        assertThat(sampledFlag(low)).isFalse();
        assertThat(jdbc.queryForObject("select count(*) from auto_pass_recheck where inspection_id = ?",
                Long.class, old)).isZero();
        assertThat(listed("PENDING", near)).isTrue();

        // 한 번 결정되면 다시 처리하지 않음
        assertThat(sweeper.sweep()).isZero();
    }

    private boolean sampledFlag(String inspectionId) {
        return jdbc.queryForObject("select sampled from auto_pass_recheck where inspection_id = ?", Boolean.class,
                inspectionId);
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
