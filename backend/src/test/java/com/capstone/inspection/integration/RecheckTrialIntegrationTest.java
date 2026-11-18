package com.capstone.inspection.integration;

import com.capstone.inspection.common.time.Times;
import com.capstone.inspection.inspection.RecheckSweeper;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MvcResult;

import java.time.OffsetDateTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.stream.StreamSupport;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

// 계약 6.11 공동시험 기록: 판정 당시 규칙 저장·재처리, 화면 체류 시간, 관리자 확인함, 요약
//   RecheckIntegrationTest와 같은 설정 (NEAR·MID 100%, LOW 0%) → 규칙 v1-b40-80-p100-100-0
//   예시 정책 example-door-p1 기준치 0.05: 0.045 → NEAR(r 0.9), 0.01 → LOW(r 0.2), 0.2 → REVIEW
@TestPropertySource(properties = {"app.recheck.enabled=true", "app.recheck.near-rate=1.0", "app.recheck.mid-rate=1.0", "app.recheck.low-rate=0"})
class RecheckTrialIntegrationTest extends IntegrationTestBase {

    private static final String RULE = "v1-b40-80-p100-100-0";

    @Autowired
    private RecheckSweeper sweeper;

    private String submitGood(double calibrated) throws Exception {
        ai = r -> response(r, "GOOD", 0.1, calibrated);
        return submitAndWaitForRecheckDecision().path("inspectionId").asText();
    }

    private static Map<String, Object> timing(long dwellMs, int openCount) {
        Map<String, Object> body = new HashMap<>();
        body.put("screenDwellMs", dwellMs);
        body.put("firstOpenedAt", "2026-11-19T10:02:11+09:00");
        body.put("openCount", openCount);
        return body;
    }

    private MvcResult recheck(String id, String result, Map<String, Object> extra) throws Exception {
        Map<String, Object> body = new HashMap<>(extra);
        body.put("result", result);
        return postJson("/api/v1/inspections/" + id + "/recheck", body, worker());
    }

    private MvcResult acknowledge(String id, String note, String token) throws Exception {
        return postJson("/api/v1/admin/rechecks/" + id + "/acknowledge", Map.of("note", note), token);
    }

    private boolean listed(String query, String inspectionId) throws Exception {
        JsonNode items = json(call(get("/api/v1/rechecks?" + query + "&size=100"), admin())).at("/data/items");
        return StreamSupport.stream(items.spliterator(), false)
                .anyMatch(n -> n.path("inspectionId").asText().equals(inspectionId));
    }

    private String ruleIdOf(String inspectionId) {
        return jdbc.queryForObject("select recheck_rule_id from inspection where id = ?", String.class, inspectionId);
    }

    // 결정 저장 실패 흉내: 결정 행을 지우고, 분석 직후 대기(SETTLE)가 지난 것처럼 완료 시각을 당김
    private void dropDecision(String inspectionId) {
        jdbc.update("delete from auto_pass_recheck where inspection_id = ?", inspectionId);
        jdbc.update("update inspection set completed_at = completed_at - interval 5 minute where id = ?", inspectionId);
    }

    @Test
    @DisplayName("판정 당시 규칙이 검사에 남고, 재처리는 지금 설정이 아니라 그 규칙으로 결정. 규칙이 없으면 결정하지 않음")
    void sweepUsesRuleStoredAtJudgement() throws Exception {
        String stored = submitGood(0.045);
        String noRule = submitGood(0.045);

        String currentRule = ruleIdOf(stored);
        assertThat(jdbc.queryForObject("select rule_version from recheck_rule where id = ?", String.class, currentRule))
                .isEqualTo(RULE);
        assertThat(jdbc.queryForObject("select rule_id from auto_pass_recheck where inspection_id = ?", String.class,
                stored)).isEqualTo(currentRule);

        // 판정 당시 규칙이 NEAR 0%였던 것처럼 바꿈 → 지금 설정(NEAR 100%)이면 뽑히지만 당시 규칙으로는 안 뽑혀야 함
        String oldRule = UUID.randomUUID().toString();
        jdbc.update("""
                insert into recheck_rule (id, rule_version, trial_name, near_ratio, mid_ratio, near_rate, mid_rate,
                                          low_rate, created_at)
                values (?, ?, null, 0.8, 0.4, 0, 1, 0, now(6))""", oldRule, "test-" + oldRule);
        dropDecision(stored);
        jdbc.update("update inspection set recheck_rule_id = ? where id = ?", oldRule, stored);
        dropDecision(noRule);
        jdbc.update("update inspection set recheck_rule_id = null where id = ?", noRule);

        sweeper.sweep();

        assertThat(jdbc.queryForMap("select sampled, rule_id from auto_pass_recheck where inspection_id = ?", stored))
                .containsEntry("sampled", false).containsEntry("rule_id", oldRule);
        assertThat(jdbc.queryForObject("select count(*) from auto_pass_recheck where inspection_id = ?", Long.class,
                noRule)).isZero();
        assertThat(ruleIdOf(submitGood(0.2))).isNull(); // REVIEW 건에는 규칙을 남기지 않음
    }

    @Test
    @DisplayName("재확인 FAIL은 관리자 확인함 가능(해결 완료와 별개), PASS·ADMIN 외는 거절, 목록 필터와 상세에 함께 표시")
    void acknowledgeFail() throws Exception {
        String fail = submitGood(0.045);
        String pass = submitGood(0.045);
        assertThat(recheck(fail, "FAIL", timing(18250, 2)).getResponse().getStatus()).isEqualTo(200);
        assertThat(recheck(pass, "PASS", Map.of()).getResponse().getStatus()).isEqualTo(200);
        assertThat(listed("status=DONE&result=FAIL&acknowledged=false", fail)).isTrue();
        assertThat(listed("status=DONE&result=FAIL&acknowledged=false", pass)).isFalse();

        assertThat(acknowledge(fail, "라인 담당자에게 전달", worker()).getResponse().getStatus()).isEqualTo(403);
        MvcResult acked = acknowledge(fail, "라인 담당자에게 전달", admin());
        assertThat(acked.getResponse().getStatus()).isEqualTo(200);
        JsonNode data = json(acked).path("data");
        assertThat(data.path("finalJudgement").asText()).isEqualTo("PASS");
        assertThat(data.path("judgedBy").asText()).isEqualTo("SYSTEM");
        assertThat(data.at("/recheck/acknowledgedBy").asText()).isNotBlank();
        assertThat(data.at("/recheck/acknowledgeNote").asText()).isEqualTo("라인 담당자에게 전달");

        // 다시 보내도 처음 기록 그대로
        assertThat(json(acknowledge(fail, "다른 메모", admin())).at("/data/recheck/acknowledgeNote").asText())
                .isEqualTo("라인 담당자에게 전달");
        assertThat(listed("status=DONE&result=FAIL&acknowledged=false", fail)).isFalse();
        assertThat(listed("status=DONE&acknowledged=true", fail)).isTrue();
        assertThat(errorCode(acknowledge(pass, "확인", admin()))).isEqualTo("NOT_ACKNOWLEDGEABLE");
        assertThat(errorCode(call(get("/api/v1/rechecks?status=PENDING&result=FAIL"), admin())))
                .isEqualTo("INVALID_PARAMETER");

        JsonNode detail = json(call(get("/api/v1/inspections/" + fail), worker())).path("data");
        assertThat(detail.at("/judgement/finalJudgement").asText()).isEqualTo("PASS");
        assertThat(detail.at("/recheck/result").asText()).isEqualTo("FAIL");
        assertThat(detail.at("/recheck/ruleVersion").asText()).isEqualTo(RULE);
        assertThat(detail.at("/recheck/acknowledgedAt").isNull()).isFalse();
        assertThat(jdbc.queryForMap("select screen_dwell_ms, open_count from auto_pass_recheck where inspection_id = ?",
                fail)).containsEntry("screen_dwell_ms", 18250L).containsEntry("open_count", 2);
    }

    @Test
    @DisplayName("확인함 동시 요청: 두 응답 모두 확인 기록을 담고, DB에는 처음 기록 1건만 남음")
    void acknowledgeConcurrently() throws Exception {
        String fail = submitGood(0.045);
        assertThat(recheck(fail, "FAIL", Map.of()).getResponse().getStatus()).isEqualTo(200);

        CyclicBarrier start = new CyclicBarrier(2);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            List<Future<MvcResult>> calls = List.of("메모 A", "메모 B").stream()
                    .map(note -> pool.submit(() -> {
                        start.await();
                        return acknowledge(fail, note, admin());
                    })).toList();
            for (Future<MvcResult> call : calls) {
                MvcResult result = call.get();
                assertThat(result.getResponse().getStatus()).isEqualTo(200);
                JsonNode recheck = json(result).at("/data/recheck");
                // 진 요청도 이긴 요청이 남긴 기록을 돌려받음 (확인 전 상태가 아님)
                assertThat(recheck.path("acknowledgedAt").isNull()).isFalse();
                assertThat(recheck.path("acknowledgeNote").asText()).isIn("메모 A", "메모 B");
            }
        } finally {
            pool.shutdown();
        }
        assertThat(jdbc.queryForObject("""
                select count(*) from auto_pass_recheck where inspection_id = ? and acknowledged_at is not null""",
                Long.class, fail)).isEqualTo(1);
    }

    @Test
    @DisplayName("화면 체류 시간: REVIEW 확인·재확인 모두 셋 다 보내거나 생략, 일부만·범위 밖이면 400")
    void screenTiming() throws Exception {
        String review = submitGood(0.2);
        Map<String, Object> partial = new HashMap<>(timing(5000, 1));
        partial.remove("openCount");
        partial.put("finalJudgement", "PASS");
        assertThat(errorCode(postJson("/api/v1/inspections/" + review + "/confirm", partial, worker())))
                .isEqualTo("INVALID_PARAMETER");

        Map<String, Object> body = new HashMap<>(timing(24300, 1));
        body.put("finalJudgement", "FAIL");
        assertThat(postJson("/api/v1/inspections/" + review + "/confirm", body, worker()).getResponse().getStatus())
                .isEqualTo(200);
        assertThat(jdbc.queryForMap("select screen_dwell_ms, open_count from worker_confirmation where inspection_id = ?",
                review)).containsEntry("screen_dwell_ms", 24300L).containsEntry("open_count", 1);

        String near = submitGood(0.045);
        assertThat(errorCode(recheck(near, "PASS", timing(-1, 1)))).isEqualTo("INVALID_PARAMETER");
    }

    @Test
    @DisplayName("요약: 규칙별 구간 건수, 누락은 규칙이 남은 건(구간에 포함)과 없는 건을 나눔, 완료 없는 구간이 있으면 추정 null, 가상 비교")
    void summary() throws Exception {
        String from = OffsetDateTime.now(Times.ZONE).toString();
        String sampledFail = submitGood(0.045);  // NEAR, 뽑힘 → FAIL
        submitGood(0.01);                        // LOW, 비율 0이라 안 뽑힘
        String undecided = submitGood(0.045);    // NEAR, 결정 저장 실패 (규칙은 남음)
        String withoutRule = submitGood(0.045);  // 규칙도 결정도 없음
        submitGood(0.2);                         // REVIEW, 확인 대기
        recheck(sampledFail, "FAIL", timing(9000, 1));
        jdbc.update("delete from auto_pass_recheck where inspection_id in (?, ?)", undecided, withoutRule);
        jdbc.update("update inspection set recheck_rule_id = null where id = ?", withoutRule);

        JsonNode s = json(call(get("/api/v1/admin/rechecks/summary").param("from", from)
                .param("compareNearRate", "0.5").param("compareMidRate", "1").param("compareLowRate", "0"), admin()))
                .path("data");

        assertThat(s.path("autoPassCount").asLong()).isEqualTo(4);
        assertThat(s.path("decidedCount").asLong()).isEqualTo(2);
        assertThat(s.path("undecidedCount").asLong()).isEqualTo(2);
        assertThat(s.path("undecidedWithoutRuleCount").asLong()).isEqualTo(1);
        assertThat(s.path("rules")).hasSize(1);
        JsonNode rule = s.at("/rules/0");
        assertThat(rule.path("ruleVersion").asText()).isEqualTo(RULE);
        assertThat(rule.path("autoPassCount").asLong()).isEqualTo(3);
        assertThat(rule.path("undecidedCount").asLong()).isEqualTo(1);
        JsonNode near = rule.at("/strata/0");
        assertThat(near.path("stratum").asText()).isEqualTo("NEAR");
        assertThat(near.path("autoPassCount").asLong()).isEqualTo(2);
        assertThat(near.path("undecidedCount").asLong()).isEqualTo(1);
        assertThat(near.path("completedCount").asLong()).isEqualTo(1);
        assertThat(near.path("failRateAmongCompleted").asDouble()).isEqualTo(1.0);
        assertThat(near.path("completionRate").asDouble()).isEqualTo(1.0);
        assertThat(rule.path("partial").asBoolean()).isTrue(); // 결정 누락 1건이 남음
        assertThat(rule.at("/strata/2/autoPassCount").asLong()).isEqualTo(1); // LOW
        // LOW에 AUTO_PASS가 있는데 완료 0건 → 전체 추정은 비움 (대기·미선정을 정상으로 세지 않음)
        assertThat(rule.path("estimatedDefectRateInAutoPass").isNull()).isTrue();
        assertThat(rule.at("/compare/computable").asBoolean()).isTrue();
        assertThat(rule.at("/compare/sampledCount").asLong()).isBetween(0L, 1L);

        assertThat(s.at("/waits/recheck/count").asLong()).isEqualTo(1);
        assertThat(s.at("/waits/recheck/pendingCount").asLong()).isZero();
        assertThat(s.at("/waits/review/pendingCount").asLong()).isEqualTo(1);
        assertThat(s.at("/dwell/recheck/averageMs").asLong()).isEqualTo(9000);

        // 비교 비율이 실제보다 크면(LOW 0% → 50%) 같은 기록으로 계산 불가
        JsonNode higher = json(call(get("/api/v1/admin/rechecks/summary").param("from", from)
                .param("compareNearRate", "1").param("compareMidRate", "1").param("compareLowRate", "0.5"), admin()))
                .at("/data/rules/0/compare");
        assertThat(higher.path("computable").asBoolean()).isFalse();
        assertThat(higher.path("sampledCount").isNull()).isTrue();
        assertThat(errorCode(call(get("/api/v1/admin/rechecks/summary").param("compareNearRate", "0.5"), admin())))
                .isEqualTo("INVALID_PARAMETER");
        assertThat(call(get("/api/v1/admin/rechecks/summary"), worker()).getResponse().getStatus()).isEqualTo(403);
    }
}
