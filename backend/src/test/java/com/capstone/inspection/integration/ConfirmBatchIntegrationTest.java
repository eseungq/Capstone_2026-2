package com.capstone.inspection.integration;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MvcResult;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.stream.IntStream;

import static org.assertj.core.api.Assertions.assertThat;

// 계약 v4 6.7.1 일괄 FAIL
class ConfirmBatchIntegrationTest extends IntegrationTestBase {

    private static final String BATCH_URL = "/api/v1/inspections/confirm-batch";

    private String reviewPending() throws Exception {
        ai = goodAboveThreshold();
        JsonNode detail = submitAndWait();
        assertThat(detail.path("displayState").asText()).isEqualTo("REVIEW_PENDING");
        return detail.path("inspectionId").asText();
    }

    private String autoPass() throws Exception {
        ai = goodBelowThreshold();
        JsonNode detail = submitAndWait();
        assertThat(detail.path("displayState").asText()).isEqualTo("AUTO_PASS");
        return detail.path("inspectionId").asText();
    }

    private MvcResult confirm(String id, String judgement) throws Exception {
        return postJson("/api/v1/inspections/" + id + "/confirm", Map.of("finalJudgement", judgement), worker());
    }

    private static Map<String, Object> item(String id) {
        return Map.of("inspectionId", id);
    }

    private static Map<String, Object> body(String judgement, List<?> items) {
        Map<String, Object> body = new HashMap<>();
        body.put("finalJudgement", judgement);
        body.put("comment", "고정핀 들뜸");
        body.put("items", items);
        return body;
    }

    private MvcResult batch(List<?> items, String token) throws Exception {
        return postJson(BATCH_URL, body("FAIL", items), token);
    }

    private long confirmations(String id) {
        return jdbc.queryForObject("select count(*) from worker_confirmation where inspection_id = ?", Long.class, id);
    }

    private String batchIdOf(String id) {
        return jdbc.queryForObject("select batch_id from worker_confirmation where inspection_id = ?", String.class, id);
    }

    @Test
    @DisplayName("섞인 일괄 FAIL: 요청 순서대로 CONFIRMED·ALREADY_CONFIRMED·CONFLICT·NOT_REVIEWABLE·NOT_FOUND")
    void mixedBatch() throws Exception {
        String pending = reviewPending();
        String alreadyFail = reviewPending();
        String alreadyPass = reviewPending();
        String auto = autoPass();
        String missing = UUID.randomUUID().toString();
        assertThat(confirm(alreadyFail, "FAIL").getResponse().getStatus()).isEqualTo(200);
        assertThat(confirm(alreadyPass, "PASS").getResponse().getStatus()).isEqualTo(200);

        MvcResult result = batch(List.of(item(pending), item(alreadyFail), item(alreadyPass), item(auto), item(missing)),
                worker());

        assertThat(result.getResponse().getStatus()).isEqualTo(200);
        JsonNode data = json(result).path("data");
        String batchId = data.path("batchId").asText();
        assertThat(UUID.fromString(batchId)).isNotNull();
        JsonNode results = data.path("results");
        assertThat(results).hasSize(5);

        JsonNode confirmed = results.get(0);
        assertThat(confirmed.path("inspectionId").asText()).isEqualTo(pending);
        assertThat(confirmed.path("inspectionNo").asText()).startsWith("INS-");
        assertThat(confirmed.path("result").asText()).isEqualTo("CONFIRMED");
        assertThat(confirmed.path("finalJudgement").asText()).isEqualTo("FAIL");
        assertThat(confirmed.path("judgedBy").asText()).isEqualTo("WORKER");
        assertThat(confirmed.path("confirmedBy").asText()).isEqualTo("worker01");
        assertThat(confirmed.path("confirmedAt").isNull()).isFalse();
        assertThat(confirmed.path("errorCode").isNull()).isTrue();

        JsonNode already = results.get(1);
        assertThat(already.path("inspectionId").asText()).isEqualTo(alreadyFail);
        assertThat(already.path("result").asText()).isEqualTo("ALREADY_CONFIRMED");
        assertThat(already.path("finalJudgement").asText()).isEqualTo("FAIL");
        assertThat(already.path("confirmedBy").asText()).isEqualTo("worker01");
        assertThat(already.path("errorCode").isNull()).isTrue();

        JsonNode conflict = results.get(2);
        assertThat(conflict.path("inspectionId").asText()).isEqualTo(alreadyPass);
        assertThat(conflict.path("result").asText()).isEqualTo("CONFLICT");
        assertThat(conflict.path("finalJudgement").asText()).isEqualTo("PASS"); // 덮어쓰지 않은 현재 값
        assertThat(conflict.path("judgedBy").asText()).isEqualTo("WORKER");
        assertThat(conflict.path("confirmedBy").asText()).isEqualTo("worker01");
        assertThat(conflict.path("errorCode").asText()).isEqualTo("ALREADY_CONFIRMED");

        JsonNode notReviewable = results.get(3);
        assertThat(notReviewable.path("inspectionId").asText()).isEqualTo(auto);
        assertThat(notReviewable.path("inspectionNo").asText()).startsWith("INS-");
        assertThat(notReviewable.path("result").asText()).isEqualTo("NOT_REVIEWABLE");
        assertThat(notReviewable.path("finalJudgement").asText()).isEqualTo("PASS"); // AUTO_PASS 현재 값
        assertThat(notReviewable.path("judgedBy").asText()).isEqualTo("SYSTEM");
        assertThat(notReviewable.path("confirmedBy").isNull()).isTrue();
        assertThat(notReviewable.path("errorCode").asText()).isEqualTo("NOT_REVIEWABLE");

        JsonNode notFound = results.get(4);
        assertThat(notFound.path("inspectionId").asText()).isEqualTo(missing);
        assertThat(notFound.path("result").asText()).isEqualTo("NOT_FOUND");
        assertThat(notFound.path("inspectionNo").isNull()).isTrue();
        assertThat(notFound.path("errorCode").asText()).isEqualTo("INSPECTION_NOT_FOUND");

        // 저장 확인: 이번 요청으로 저장된 건만 batch_id, 기존 단건 확인은 NULL·덮어쓰기 없음
        assertThat(batchIdOf(pending)).isEqualTo(batchId);
        assertThat(jdbc.queryForObject("select comment from worker_confirmation where inspection_id = ?",
                String.class, pending)).isEqualTo("고정핀 들뜸");
        assertThat(batchIdOf(alreadyFail)).isNull();
        assertThat(batchIdOf(alreadyPass)).isNull();
        assertThat(jdbc.queryForObject("select final_judgement from worker_confirmation where inspection_id = ?",
                String.class, alreadyPass)).isEqualTo("PASS");
        assertThat(confirmations(auto)).isZero();
        JsonNode detail = waitFinished(pending);
        assertThat(detail.path("displayState").asText()).isEqualTo("REVIEW_DONE");
        assertThat(detail.at("/judgement/finalJudgement").asText()).isEqualTo("FAIL");
    }

    @Test
    @DisplayName("응답을 못 받은 재전송: 새 batchId, 이미 저장된 건은 ALREADY_CONFIRMED이고 batch_id는 처음 값 유지")
    void resendKeepsFirstBatch() throws Exception {
        String id = reviewPending();
        JsonNode first = json(batch(List.of(item(id)), worker())).path("data");
        JsonNode second = json(batch(List.of(item(id)), worker())).path("data");

        assertThat(second.path("batchId").asText()).isNotEqualTo(first.path("batchId").asText());
        assertThat(second.at("/results/0/result").asText()).isEqualTo("ALREADY_CONFIRMED");
        assertThat(second.at("/results/0/confirmedAt").asText()).isEqualTo(first.at("/results/0/confirmedAt").asText());
        assertThat(confirmations(id)).isEqualTo(1);
        assertThat(batchIdOf(id)).isEqualTo(first.path("batchId").asText());
    }

    @Test
    @DisplayName("단건 confirm은 batch_id NULL")
    void singleConfirmHasNoBatch() throws Exception {
        String id = reviewPending();
        assertThat(confirm(id, "FAIL").getResponse().getStatus()).isEqualTo(200);
        assertThat(batchIdOf(id)).isNull();
    }

    @Test
    @DisplayName("건별 화면 체류 시간 저장, 보내지 않은 건은 NULL")
    void dwellPerItem() throws Exception {
        String timed = reviewPending();
        String plain = reviewPending();
        Map<String, Object> timedItem = new HashMap<>();
        timedItem.put("inspectionId", timed);
        timedItem.put("screenDwellMs", 8200L);
        timedItem.put("firstOpenedAt", "2026-11-24T10:01:02+09:00");
        timedItem.put("openCount", 2);

        MvcResult result = batch(List.of(timedItem, item(plain)), worker());

        assertThat(result.getResponse().getStatus()).isEqualTo(200);
        assertThat(jdbc.queryForMap("select screen_dwell_ms, open_count from worker_confirmation where inspection_id = ?",
                timed)).containsEntry("screen_dwell_ms", 8200L).containsEntry("open_count", 2);
        assertThat(jdbc.queryForMap("select screen_dwell_ms, first_opened_at from worker_confirmation where inspection_id = ?",
                plain)).containsEntry("screen_dwell_ms", null).containsEntry("first_opened_at", null);
    }

    @Test
    @DisplayName("요청 오류는 전체 400 INVALID_PARAMETER, 아무것도 저장 안 함 (PASS·0건·51건·중복·체류 시간 일부·comment 201자)")
    void invalidRequests() throws Exception {
        String id = reviewPending();
        String other = reviewPending();
        Map<String, Object> partialTiming = new HashMap<>();
        partialTiming.put("inspectionId", other);
        partialTiming.put("screenDwellMs", 100L);
        List<Map<String, Object>> fiftyOne = new ArrayList<>(List.of(item(id)));
        IntStream.range(0, 50).forEach(n -> fiftyOne.add(item(UUID.randomUUID().toString())));
        Map<String, Object> longComment = body("FAIL", List.of(item(id)));
        longComment.put("comment", "가".repeat(201));

        List<Map<String, Object>> bodies = List.of(
                body("PASS", List.of(item(id))),
                body("MAYBE", List.of(item(id))),
                body("FAIL", List.of()),
                body("FAIL", fiftyOne),
                body("FAIL", List.of(item(id), item(id))),
                body("FAIL", List.of(item(id), partialTiming)),
                longComment);
        for (Map<String, Object> b : bodies) {
            MvcResult result = postJson(BATCH_URL, b, worker());
            assertThat(result.getResponse().getStatus()).as(b.toString().substring(0, 40)).isEqualTo(400);
            assertThat(errorCode(result)).isEqualTo("INVALID_PARAMETER");
        }
        Map<String, Object> noItems = new HashMap<>(body("FAIL", List.of()));
        noItems.remove("items");
        assertThat(postJson(BATCH_URL, noItems, worker()).getResponse().getStatus()).isEqualTo(400);

        assertThat(confirmations(id)).isZero();
        assertThat(confirmations(other)).isZero();
    }

    @Test
    @DisplayName("ADMIN·DEVICE는 403 ACCESS_DENIED")
    void onlyWorker() throws Exception {
        String id = reviewPending();
        for (String token : List.of(admin(), device())) {
            MvcResult result = batch(List.of(item(id)), token);
            assertThat(result.getResponse().getStatus()).isEqualTo(403);
            assertThat(errorCode(result)).isEqualTo("ACCESS_DENIED");
        }
        assertThat(confirmations(id)).isZero();
    }

    @Test
    @DisplayName("같은 건 단건 PASS와 일괄 FAIL 동시 제출: 판정은 1건만 저장, 응답은 저장된 값과 일치 (500 없음)")
    void concurrentSingleAndBatch() throws Exception {
        for (int round = 0; round < 3; round++) {
            String id = reviewPending();
            CyclicBarrier start = new CyclicBarrier(2);
            ExecutorService pool = Executors.newFixedThreadPool(2);
            try {
                Future<MvcResult> single = pool.submit(() -> {
                    start.await();
                    return confirm(id, "PASS");
                });
                Future<MvcResult> batched = pool.submit(() -> {
                    start.await();
                    return batch(List.of(item(id)), worker());
                });
                MvcResult singleResult = single.get();
                MvcResult batchResult = batched.get();
                assertThat(batchResult.getResponse().getStatus()).isEqualTo(200);
                String saved = jdbc.queryForObject(
                        "select final_judgement from worker_confirmation where inspection_id = ?", String.class, id);
                String batchOutcome = json(batchResult).at("/data/results/0/result").asText();
                if (saved.equals("FAIL")) {
                    assertThat(batchOutcome).isEqualTo("CONFIRMED");
                    assertThat(singleResult.getResponse().getStatus()).isEqualTo(409);
                } else {
                    assertThat(batchOutcome).isEqualTo("CONFLICT");
                    assertThat(singleResult.getResponse().getStatus()).isEqualTo(200);
                }
            } finally {
                pool.shutdownNow();
            }
            assertThat(confirmations(id)).isEqualTo(1);
        }
    }

    @Test
    @DisplayName("같은 건이 든 일괄 두 개 동시 제출: 1건만 저장, 한쪽 CONFIRMED·다른 쪽 ALREADY_CONFIRMED")
    void concurrentBatches() throws Exception {
        String shared = reviewPending();
        String onlyA = reviewPending();
        CyclicBarrier start = new CyclicBarrier(2);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<MvcResult> a = pool.submit(() -> {
                start.await();
                return batch(List.of(item(onlyA), item(shared)), worker());
            });
            Future<MvcResult> b = pool.submit(() -> {
                start.await();
                return batch(List.of(item(shared)), worker());
            });
            JsonNode resultA = json(a.get()).path("data");
            JsonNode resultB = json(b.get()).path("data");
            assertThat(resultA.at("/results/0/result").asText()).isEqualTo("CONFIRMED");
            assertThat(List.of(resultA.at("/results/1/result").asText(), resultB.at("/results/0/result").asText()))
                    .containsExactlyInAnyOrder("CONFIRMED", "ALREADY_CONFIRMED");
            String winner = resultA.at("/results/1/result").asText().equals("CONFIRMED")
                    ? resultA.path("batchId").asText() : resultB.path("batchId").asText();
            assertThat(batchIdOf(shared)).isEqualTo(winner);
        } finally {
            pool.shutdownNow();
        }
        assertThat(confirmations(shared)).isEqualTo(1);
        assertThat(confirmations(onlyA)).isEqualTo(1);
    }
}
