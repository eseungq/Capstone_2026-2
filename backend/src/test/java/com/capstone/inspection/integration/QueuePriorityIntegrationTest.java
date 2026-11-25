package com.capstone.inspection.integration;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MvcResult;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

// 계약 6.4 REVIEW 정렬·필터 [제안 11/23]: sort=PRIORITY, predictedQuality
//   예시 정책 example-door-p1 기준치 0.05: GOOD 0.2 → REVIEW(ABOVE_THRESHOLD), DEFECT → REVIEW(DEFECT_PREDICTED)
//   테스트끼리 DB를 같이 쓰므로 이 테스트가 만든 검사만 골라 순서를 비교
class QueuePriorityIntegrationTest extends IntegrationTestBase {

    private String submitWith(String quality, double calibrated) throws Exception {
        ai = r -> response(r, quality, calibrated, calibrated);
        return submitAndWait().path("inspectionId").asText();
    }

    private String submitFailed() throws Exception {
        ai = aiServerError();
        return submitAndWait().path("inspectionId").asText();
    }

    private MvcResult queue(String query) throws Exception {
        return call(get("/api/v1/monitoring/queue?" + query), worker());
    }

    // 커서를 따라 끝까지 읽고 지정한 검사만 순서대로 남김
    private List<String> readAll(String query, Set<String> mine) throws Exception {
        List<String> order = new ArrayList<>();
        String cursor = null;
        do {
            String q = query + (cursor == null ? "" : "&cursor=" + cursor);
            JsonNode data = json(queue(q)).path("data");
            for (JsonNode item : data.path("items")) {
                String id = item.path("inspectionId").asText();
                if (mine.contains(id)) {
                    order.add(id);
                }
            }
            cursor = data.path("nextCursor").isNull() ? null : data.path("nextCursor").asText();
        } while (cursor != null);
        return order;
    }

    @Test
    @DisplayName("PRIORITY는 GOOD·기준 초과 REVIEW를 먼저, 나머지를 뒤에. 그룹 안은 오래된 순이고 페이지 경계를 넘어도 유지")
    void priorityOrderAcrossPages() throws Exception {
        String defect1 = submitWith("DEFECT", 0.95);
        String above1 = submitWith("GOOD", 0.2);
        String failed = submitFailed();
        String above2 = submitWith("GOOD", 0.3);
        String defect2 = submitWith("DEFECT", 0.99);
        Set<String> mine = Set.of(defect1, above1, failed, above2, defect2);

        assertThat(readAll("sort=PRIORITY&size=2", mine)).containsExactly(above1, above2, defect1, failed, defect2);
        // 기본은 지금과 같은 오래된 순
        assertThat(readAll("size=2", mine)).containsExactly(defect1, above1, failed, above2, defect2);
        assertThat(readAll("sort=RECEIVED&size=2", mine)).containsExactly(defect1, above1, failed, above2, defect2);
    }

    @Test
    @DisplayName("predictedQuality=DEFECT는 REVIEW에 남은 불량 예측만. 예측이 없는 FAILED는 나오지 않음")
    void filterByPredictedQuality() throws Exception {
        String defect = submitWith("DEFECT", 0.97);
        String above = submitWith("GOOD", 0.2);
        String failed = submitFailed();
        Set<String> mine = Set.of(defect, above, failed);

        assertThat(readAll("predictedQuality=DEFECT&size=100", mine)).containsExactly(defect);
        assertThat(readAll("type=REVIEW&predictedQuality=GOOD&size=100", mine)).containsExactly(above);
        assertThat(readAll("sort=PRIORITY&predictedQuality=DEFECT&size=100", mine)).containsExactly(defect);
    }

    @Test
    @DisplayName("항목에 보정 확률과 적용 기준치. FAILED는 둘 다 null")
    void itemShowsProbabilityAndThreshold() throws Exception {
        String above = submitWith("GOOD", 0.2);
        String failed = submitFailed();

        JsonNode items = json(queue("size=100")).at("/data/items");
        for (JsonNode item : items) {
            String id = item.path("inspectionId").asText();
            if (id.equals(above)) {
                assertThat(item.path("calibratedDefectProbability").asDouble()).isEqualTo(0.2);
                assertThat(item.path("passThresholdApplied").asDouble()).isEqualTo(0.05);
            }
            if (id.equals(failed)) {
                assertThat(item.path("calibratedDefectProbability").isNull()).isTrue();
                assertThat(item.path("passThresholdApplied").isNull()).isTrue();
            }
        }
        assertThat(items.findValuesAsText("inspectionId")).contains(above, failed);
    }

    @Test
    @DisplayName("잘못된 sort·predictedQuality, 다른 정렬의 커서는 400 INVALID_PARAMETER")
    void invalidParameters() throws Exception {
        submitWith("GOOD", 0.2);
        submitWith("GOOD", 0.3);

        assertThat(errorCode(queue("sort=NEWEST"))).isEqualTo("INVALID_PARAMETER");
        assertThat(errorCode(queue("predictedQuality=MAYBE"))).isEqualTo("INVALID_PARAMETER");

        String receivedCursor = json(queue("size=1")).at("/data/nextCursor").asText();
        String priorityCursor = json(queue("sort=PRIORITY&size=1")).at("/data/nextCursor").asText();
        assertThat(errorCode(queue("sort=PRIORITY&size=1&cursor=" + receivedCursor))).isEqualTo("INVALID_PARAMETER");
        assertThat(errorCode(queue("size=1&cursor=" + priorityCursor))).isEqualTo("INVALID_PARAMETER");
    }
}
