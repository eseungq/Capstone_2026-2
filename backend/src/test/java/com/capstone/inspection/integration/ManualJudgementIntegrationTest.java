package com.capstone.inspection.integration;

import com.capstone.inspection.ai.AiCallException;
import com.capstone.inspection.common.error.ErrorCode;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MvcResult;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

// 수동 판정 (docs/수동판정_결정안.md B안, 계약 v4 6.10, V6): FAILED → 새 MANUAL 검사 → 기존 confirm
class ManualJudgementIntegrationTest extends IntegrationTestBase {

    private String failedId() throws Exception {
        ai = aiServerError();
        JsonNode failed = submitAndWait();
        assertThat(failed.path("status").asText()).isEqualTo("FAILED");
        return failed.path("inspectionId").asText();
    }

    private MvcResult manual(String id, String token) throws Exception {
        return call(post("/api/v1/inspections/" + id + "/manual"), token);
    }

    private JsonNode detail(String id) throws Exception {
        return json(call(get("/api/v1/inspections/" + id), worker())).path("data");
    }

    @Test
    @DisplayName("FAILED → 수동 전환 201(MANUAL·REVIEW_PENDING·AI_UNAVAILABLE) → confirm PASS → 원본 FAILED 유지·연결 표시")
    void convertAndConfirm() throws Exception {
        String failedId = failedId();
        String failedNo = detail(failedId).path("inspectionNo").asText();

        MvcResult created = manual(failedId, worker());
        assertThat(created.getResponse().getStatus()).isEqualTo(201);
        JsonNode data = json(created).path("data");
        String manualId = data.path("inspectionId").asText();
        assertThat(manualId).isNotEqualTo(failedId);
        assertThat(data.path("source").asText()).isEqualTo("MANUAL");
        assertThat(data.path("status").asText()).isEqualTo("COMPLETED");
        assertThat(data.path("displayState").asText()).isEqualTo("REVIEW_PENDING");
        assertThat(data.path("reviewReason").asText()).isEqualTo("AI_UNAVAILABLE");
        assertThat(data.path("manualOf").asText()).isEqualTo(failedId);
        assertThat(data.path("manualOfInspectionNo").asText()).isEqualTo(failedNo);
        assertThat(data.path("manualOfErrorCode").asText()).isEqualTo("AI_SERVER_ERROR");

        // 새 검사 상세: AI 결과 없음, 원래 FAILED와 실패 사유, 원본 사진 있음
        JsonNode m = detail(manualId);
        assertThat(m.path("source").asText()).isEqualTo("MANUAL");
        assertThat(m.path("ai").isNull()).isTrue();
        assertThat(m.path("retryOf").isNull()).isTrue();
        assertThat(m.at("/manualOf/inspectionId").asText()).isEqualTo(failedId);
        assertThat(m.at("/manualOf/errorCode").asText()).isEqualTo("AI_SERVER_ERROR");
        assertThat(m.at("/policy/reviewReason").asText()).isEqualTo("AI_UNAVAILABLE");
        assertThat(m.at("/images/original/url").asText()).isNotBlank();
        assertThat(m.at("/images/gradcam").isNull()).isTrue();

        // 원래 FAILED: 그대로, 후속 검사 표시, 재검사 불가 표시
        JsonNode f = detail(failedId);
        assertThat(f.path("status").asText()).isEqualTo("FAILED");
        assertThat(f.at("/followUp/inspectionId").asText()).isEqualTo(manualId);
        assertThat(f.at("/followUp/source").asText()).isEqualTo("MANUAL");
        assertThat(f.at("/error/retryable").asBoolean()).isFalse();

        // 판정은 기존 confirm
        MvcResult confirmed = postJson("/api/v1/inspections/" + manualId + "/confirm",
                Map.of("finalJudgement", "FAIL", "comment", "AI 없이 육안 확인"), worker());
        assertThat(confirmed.getResponse().getStatus()).isEqualTo(200);
        JsonNode done = detail(manualId);
        assertThat(done.path("displayState").asText()).isEqualTo("REVIEW_DONE");
        assertThat(done.at("/judgement/finalJudgement").asText()).isEqualTo("FAIL");
        assertThat(done.at("/judgement/judgedBy").asText()).isEqualTo("WORKER");
        assertThat(done.at("/judgement/confirmedAt").asText()).isNotBlank();

        // 같은 사진 파일 재사용
        assertThat(jdbc.queryForObject("""
                select count(*) from image_storage a join image_storage b on a.storage_uri = b.storage_uri
                where a.inspection_id = ? and b.inspection_id = ? and a.image_type = 'ORIGINAL' and b.image_type = 'ORIGINAL'""",
                Long.class, manualId, failedId)).isEqualTo(1L);

        // 이력에 출처 표시
        JsonNode items = json(call(get("/api/v1/inspections?size=100"), worker())).at("/data/items");
        boolean found = false;
        for (JsonNode item : items) {
            if (item.path("inspectionId").asText().equals(manualId)) {
                assertThat(item.path("source").asText()).isEqualTo("MANUAL");
                assertThat(item.path("reviewReason").asText()).isEqualTo("AI_UNAVAILABLE");
                found = true;
            }
        }
        assertThat(found).isTrue();
    }

    @Test
    @DisplayName("AI 상태를 확인할 수 없어도, 요청 거절(4xx)로 실패했어도 수동 전환 가능")
    void allowedWhenAiUnknownAndRejected() throws Exception {
        ai = r -> {
            throw new AiCallException(ErrorCode.AI_REQUEST_REJECTED, "가짜 422", false);
        };
        String failedId = submitAndWait().path("inspectionId").asText();
        aiModels = () -> {
            throw new IllegalStateException("AI 꺼짐");
        };
        MvcResult created = manual(failedId, worker());
        assertThat(created.getResponse().getStatus()).isEqualTo(201);
        assertThat(json(created).at("/data/manualOfErrorCode").asText()).isEqualTo("AI_REQUEST_REJECTED");
    }

    @Test
    @DisplayName("FAILED 1건당 후속 1건: 수동 후 수동·재검사 409, 재검사 후 수동 409")
    void oneFollowUpOnly() throws Exception {
        String a = failedId();
        assertThat(manual(a, worker()).getResponse().getStatus()).isEqualTo(201);
        MvcResult again = manual(a, worker());
        assertThat(again.getResponse().getStatus()).isEqualTo(409);
        assertThat(errorCode(again)).isEqualTo("ALREADY_RETRIED");
        MvcResult retry = call(post("/api/v1/inspections/" + a + "/retry"), worker());
        assertThat(retry.getResponse().getStatus()).isEqualTo(409);
        assertThat(errorCode(retry)).isEqualTo("ALREADY_RETRIED");

        String b = failedId();
        ai = goodBelowThreshold();
        assertThat(call(post("/api/v1/inspections/" + b + "/retry"), worker()).getResponse().getStatus()).isEqualTo(202);
        MvcResult afterRetry = manual(b, worker());
        assertThat(afterRetry.getResponse().getStatus()).isEqualTo(409);
        assertThat(errorCode(afterRetry)).isEqualTo("ALREADY_RETRIED");
        assertThat(jdbc.queryForObject("select count(*) from inspection where retry_of_inspection_id in (?, ?)",
                Long.class, a, b)).isEqualTo(2L);
    }

    @Test
    @DisplayName("FAILED가 아니면 409 NOT_MANUAL_CONVERTIBLE, 없는 검사 404")
    void notConvertible() throws Exception {
        String completed = submitAndWait().path("inspectionId").asText();
        MvcResult result = manual(completed, worker());
        assertThat(result.getResponse().getStatus()).isEqualTo(409);
        assertThat(errorCode(result)).isEqualTo("NOT_MANUAL_CONVERTIBLE");
        assertThat(manual("00000000-0000-0000-0000-000000000000", worker()).getResponse().getStatus()).isEqualTo(404);
    }

    @Test
    @DisplayName("전환은 WORKER만: ADMIN·DEVICE 403")
    void workerOnly() throws Exception {
        String failedId = failedId();
        assertThat(manual(failedId, admin()).getResponse().getStatus()).isEqualTo(403);
        assertThat(manual(failedId, device()).getResponse().getStatus()).isEqualTo(403);
        assertThat(jdbc.queryForObject("select count(*) from inspection where retry_of_inspection_id = ?",
                Long.class, failedId)).isZero();
    }

    @Test
    @DisplayName("모니터링: 전환한 FAILED는 실패 건수에서 빠지고, 수동 건은 확인 필요 대기열에 들어감")
    void monitoringCounts() throws Exception {
        String failedId = failedId();
        long failedBefore = doorCount("failedCount");
        long reviewBefore = doorCount("pendingReviewCount");
        String manualId = json(manual(failedId, worker())).at("/data/inspectionId").asText();
        assertThat(doorCount("failedCount")).isEqualTo(failedBefore - 1);
        assertThat(doorCount("pendingReviewCount")).isEqualTo(reviewBefore + 1);

        boolean inQueue = false;
        boolean failedInQueue = false;
        for (JsonNode item : json(call(get("/api/v1/monitoring/queue?size=100"), worker())).at("/data/items")) {
            inQueue |= item.path("inspectionId").asText().equals(manualId);
            failedInQueue |= item.path("inspectionId").asText().equals(failedId);
        }
        assertThat(inQueue).isTrue();
        assertThat(failedInQueue).isFalse();
    }

    private long doorCount(String field) throws Exception {
        for (JsonNode part : json(call(get("/api/v1/monitoring/parts"), worker())).path("data")) {
            if (part.path("partCode").asText().equals("DOOR")) {
                return part.path(field).asLong();
            }
        }
        throw new AssertionError("DOOR 없음");
    }
}
