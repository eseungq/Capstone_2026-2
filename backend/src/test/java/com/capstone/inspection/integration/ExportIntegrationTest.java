package com.capstone.inspection.integration;

import com.capstone.inspection.common.time.Times;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

// 관리자 검사 기록 CSV 내보내기
class ExportIntegrationTest extends IntegrationTestBase {

    private static final String EXPORT = "/api/v1/admin/inspections/export";

    // 이 테스트에서 만든 검사만 대상이 되도록 접수 직전 시각부터 조회 (앞 테스트의 재검사·수동 판정 건 제외)
    private String since() {
        return OffsetDateTime.now(Times.ZONE).toString();
    }

    private String no(String inspectionId) {
        return jdbc.queryForObject("select inspection_no from inspection where id = ?", String.class, inspectionId);
    }

    // params: 이름, 값, 이름, 값 ...
    private MvcResult export(String token, String... params) throws Exception {
        MockHttpServletRequestBuilder request = get(EXPORT);
        for (int p = 0; p < params.length; p += 2) {
            request.param(params[p], params[p + 1]);
        }
        return call(request, token);
    }

    private static String body(MvcResult result) {
        return new String(result.getResponse().getContentAsByteArray(), StandardCharsets.UTF_8);
    }

    // 검사번호로 행 찾기 (머리글 순서대로 값)
    private static Map<String, String> rowOf(String csv, String inspectionNo) {
        String[] lines = csv.substring(1).split("\r\n");
        List<String> header = Arrays.asList(lines[0].split(",", -1));
        for (String line : lines) {
            if (line.startsWith(inspectionNo + ",")) {
                String[] cells = line.split(",", -1);
                assertThat(cells).hasSize(header.size());
                Map<String, String> row = new HashMap<>();
                for (int c = 0; c < cells.length; c++) {
                    row.put(header.get(c), cells[c]);
                }
                return row;
            }
        }
        throw new AssertionError("CSV에 없음: " + inspectionNo);
    }

    @Test
    @DisplayName("ADMIN: BOM·머리글, AUTO_PASS·작업자 확인 건 값")
    void exportRows() throws Exception {
        String from = since();
        String autoPass = no(submitAndWait().path("inspectionId").asText());
        ai = goodAboveThreshold();
        String reviewId = submitAndWait().path("inspectionId").asText();
        postJson("/api/v1/inspections/" + reviewId + "/confirm", Map.of("finalJudgement", "FAIL"), worker());

        MvcResult result = export(admin(), "partCode", "DOOR", "from", from);
        assertThat(result.getResponse().getStatus()).isEqualTo(200);
        assertThat(result.getResponse().getContentType()).startsWith("text/csv");
        assertThat(result.getResponse().getHeader("Content-Disposition")).contains("attachment", ".csv");
        byte[] bytes = result.getResponse().getContentAsByteArray();
        assertThat(Arrays.copyOf(bytes, 3)).containsExactly(0xEF, 0xBB, 0xBF);

        String csv = body(result);
        assertThat(csv.substring(1)).startsWith("inspectionNo,partCode,");
        // 일반 검사만 있는 결과 (원본 검사 조회 없음)에서도 200
        assertThat(csv).doesNotContain(",RETRY,", ",MANUAL,");
        Map<String, String> pass = rowOf(csv, autoPass);
        assertThat(pass).containsEntry("displayState", "AUTO_PASS").containsEntry("finalJudgement", "PASS")
                .containsEntry("judgedBy", "SYSTEM").containsEntry("policyVersion", "example-door-p1")
                .containsEntry("calibratedDefectProbability", "0.021").containsEntry("workerLoginId", "");
        Map<String, String> review = rowOf(csv, no(reviewId));
        assertThat(review).containsEntry("displayState", "REVIEW_DONE").containsEntry("reviewReason", "ABOVE_THRESHOLD")
                .containsEntry("finalJudgement", "FAIL").containsEntry("workerLoginId", "worker01");
        // 초까지 고정 형식 (초 0 생략·소수점 이하 없음)
        assertThat(review.get("confirmedAt")).matches("\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}\\+09:00");
        assertThat(review.get("receivedAt")).matches("\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}\\+09:00");
    }

    @Test
    @DisplayName("수동 판정 건: 원래 FAILED 번호, AI 칸 비움")
    void exportManual() throws Exception {
        String from = since();
        ai = aiServerError();
        String failedId = submitAndWait().path("inspectionId").asText();
        String manualId = json(call(post("/api/v1/inspections/" + failedId + "/manual"), worker())).at("/data/inspectionId").asText();

        String csv = body(export(admin(), "from", from));
        assertThat(rowOf(csv, no(failedId))).containsEntry("displayState", "FAILED")
                .containsEntry("errorCode", "AI_SERVER_ERROR");
        assertThat(rowOf(csv, no(manualId))).containsEntry("source", "MANUAL")
                .containsEntry("originInspectionNo", no(failedId)).containsEntry("modelVersion", "")
                .containsEntry("rawDefectProbability", "");
    }

    @Test
    @DisplayName("수식처럼 보이는 lineCode는 앞에 '를 붙이고, 쉼표는 따옴표로 감쌈")
    void exportEscapesCells() throws Exception {
        String from = since();
        MvcResult submitted = call(multipart("/api/v1/inspections")
                .file(new MockMultipartFile("image", "t.png", "image/png", imageBytes()))
                .param("partCode", "DOOR").param("lineCode", "=1+1,L2"), device());
        String id = json(submitted).at("/data/inspectionId").asText();
        waitFinished(id);

        String csv = body(export(admin(), "from", from));
        assertThat(csv).contains(no(id) + ",DOOR,\"'=1+1,L2\",");
    }

    @Test
    @DisplayName("WORKER는 403, 잘못된 시각·부품은 400")
    void exportDenied() throws Exception {
        MvcResult denied = export(worker());
        assertThat(denied.getResponse().getStatus()).isEqualTo(403);
        assertThat(errorCode(denied)).isEqualTo("ACCESS_DENIED");

        MvcResult badTime = export(admin(), "from", "yesterday");
        assertThat(badTime.getResponse().getStatus()).isEqualTo(400);
        assertThat(errorCode(badTime)).isEqualTo("INVALID_PARAMETER");
        assertThat(export(admin(), "partCode", "NOPE").getResponse().getStatus()).isEqualTo(400);
    }
}
