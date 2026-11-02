package com.capstone.inspection.integration;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MvcResult;

import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

// 계약 v4 6.7 작업자 확인, 6.8 재검사
class ConfirmRetryIntegrationTest extends IntegrationTestBase {

    private MvcResult confirm(String id, String judgement) throws Exception {
        return postJson("/api/v1/inspections/" + id + "/confirm", Map.of("finalJudgement", judgement), worker());
    }

    private String reviewPending() throws Exception {
        ai = goodAboveThreshold();
        JsonNode detail = submitAndWait();
        assertThat(detail.path("displayState").asText()).isEqualTo("REVIEW_PENDING");
        return detail.path("inspectionId").asText();
    }

    private String failed() throws Exception {
        ai = aiServerError();
        JsonNode detail = submitAndWait();
        assertThat(detail.path("status").asText()).isEqualTo("FAILED");
        return detail.path("inspectionId").asText();
    }

    private MvcResult retry(String id) throws Exception {
        return call(post("/api/v1/inspections/" + id + "/retry"), worker());
    }

    @Test
    @DisplayName("confirm 정상: 200, 최종 판정과 REVIEW_DONE 기록")
    void confirmOk() throws Exception {
        String id = reviewPending();
        assertThat(confirm(id, "FAIL").getResponse().getStatus()).isEqualTo(200);
        JsonNode detail = waitFinished(id);
        assertThat(detail.path("displayState").asText()).isEqualTo("REVIEW_DONE");
        assertThat(detail.at("/judgement/finalJudgement").asText()).isEqualTo("FAIL");
        assertThat(detail.at("/judgement/judgedBy").asText()).isEqualTo("WORKER");
    }

    @Test
    @DisplayName("confirm 재전송: 같은 값 200, 다른 값 409")
    void confirmResend() throws Exception {
        String id = reviewPending();
        confirm(id, "PASS");
        assertThat(confirm(id, "PASS").getResponse().getStatus()).isEqualTo(200);
        MvcResult other = confirm(id, "FAIL");
        assertThat(other.getResponse().getStatus()).isEqualTo(409);
        assertThat(errorCode(other)).isEqualTo("ALREADY_CONFIRMED");
    }

    @Test
    @DisplayName("AUTO_PASS 건 confirm은 409")
    void confirmAutoPass() throws Exception {
        JsonNode detail = submitAndWait();
        assertThat(detail.path("displayState").asText()).isEqualTo("AUTO_PASS");
        MvcResult result = confirm(detail.path("inspectionId").asText(), "PASS");
        assertThat(result.getResponse().getStatus()).isEqualTo(409);
        assertThat(errorCode(result)).isEqualTo("NOT_REVIEWABLE");
    }

    @Test
    @DisplayName("동시 confirm 2건: 판정은 1건만 저장, 진 쪽은 409 (500 없음)")
    void confirmConcurrent() throws Exception {
        String id = reviewPending();
        CountDownLatch start = new CountDownLatch(1);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            List<Future<Integer>> results = List.of("PASS", "FAIL").stream().map(judgement -> pool.submit(() -> {
                start.await();
                return confirm(id, judgement).getResponse().getStatus();
            })).toList();
            start.countDown();
            assertThat(List.of(results.get(0).get(), results.get(1).get())).containsExactlyInAnyOrder(200, 409);
        } finally {
            pool.shutdownNow();
        }
        assertThat(jdbc.queryForObject("select count(*) from worker_confirmation where inspection_id = ?", Long.class, id))
                .isEqualTo(1);
    }

    @Test
    @DisplayName("retry 정상: 202, 새 검사 COMPLETED, 원래 FAILED 불변, 확인 목록에서 제외")
    void retryOk() throws Exception {
        String id = failed();
        String errorBefore = jdbc.queryForObject("select error_code from inspection where id = ?", String.class, id);
        ai = goodBelowThreshold();

        MvcResult result = retry(id);
        assertThat(result.getResponse().getStatus()).isEqualTo(202);
        assertThat(json(result).at("/data/retryOf").asText()).isEqualTo(id);
        JsonNode retried = waitFinished(json(result).at("/data/inspectionId").asText());
        assertThat(retried.path("status").asText()).isEqualTo("COMPLETED");
        assertThat(retried.path("retryOf").asText()).isEqualTo(id);

        JsonNode original = waitFinished(id);
        assertThat(original.path("status").asText()).isEqualTo("FAILED");
        assertThat(original.at("/error/code").asText()).isEqualTo(errorBefore);
        String queue = call(get("/api/v1/monitoring/queue").param("size", "100"), worker())
                .getResponse().getContentAsString();
        assertThat(queue).doesNotContain(id);
    }

    @Test
    @DisplayName("FAILED가 아니면 retry 409")
    void retryNotFailed() throws Exception {
        JsonNode detail = submitAndWait();
        MvcResult result = retry(detail.path("inspectionId").asText());
        assertThat(result.getResponse().getStatus()).isEqualTo(409);
        assertThat(errorCode(result)).isEqualTo("NOT_RETRYABLE");
    }

    @Test
    @DisplayName("같은 FAILED 건 두 번째 retry는 409")
    void retryTwice() throws Exception {
        String id = failed();
        ai = goodBelowThreshold();
        assertThat(retry(id).getResponse().getStatus()).isEqualTo(202);
        MvcResult second = retry(id);
        assertThat(second.getResponse().getStatus()).isEqualTo(409);
        assertThat(errorCode(second)).isEqualTo("ALREADY_RETRIED");
    }
}
