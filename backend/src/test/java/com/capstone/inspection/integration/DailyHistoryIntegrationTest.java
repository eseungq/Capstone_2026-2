package com.capstone.inspection.integration;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MvcResult;

import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.StreamSupport;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

// 관리자 날짜별 이력·기준 상세 (계약 6.13)
//   검사는 실제 흐름(가짜 AI)으로 만든 뒤 received_at만 2025년 전용 날짜로 옮김 → 다른 테스트의 오늘 검사와 섞이지 않음
//   received_at은 서버 기본 시간대 시각으로 저장되므로 KST 시각을 서버 시간대로 바꿔 넣음
//   정책 적용 상태는 IntegrationTestBase가 테스트마다 예시 정책(example-door-p1)으로 되돌림
class DailyHistoryIntegrationTest extends IntegrationTestBase {

    private static final String DAILY = "/api/v1/admin/automation/daily";
    private static final String DETAIL = DAILY + "/detail";
    private static final String POLICIES = "/api/v1/admin/policies";
    private static final ZoneId KST = ZoneId.of("Asia/Seoul");

    // ---- 준비 도우미 ----

    // 통과 0.03(검증 0.02~0.08)·불량 0.8(검증 0.7~0.9)·자동 불량 켠 정책을 적용
    private JsonNode activeAutoFailPolicy() throws Exception {
        Map<String, Object> body = new HashMap<>();
        body.put("modelVersion", MOCK_MODEL);
        body.put("calibratorVersion", "mock-cal-v1");
        body.put("policyVersion", unique("example-dh"));
        body.put("passThreshold", 0.03);
        body.put("validatedMin", 0.02);
        body.put("validatedMax", 0.08);
        body.put("metrics", Map.of("sampleCount", 10));
        String id = created(postJson(POLICIES, body, admin())).path("policyId").asText();
        String withFail = created(postJson(POLICIES + "/" + id + "/fail-threshold",
                Map.of("failThreshold", 0.8, "failValidatedMin", 0.7, "failValidatedMax", 0.9), admin()))
                .path("policyId").asText();
        JsonNode enabled = created(postJson(POLICIES + "/" + withFail + "/auto-fail", Map.of("enabled", true), admin()));
        assertThat(call(post(POLICIES + "/" + enabled.path("policyId").asText() + "/activate"), admin())
                .getResponse().getStatus()).isEqualTo(200);
        return enabled;
    }

    private JsonNode created(MvcResult result) throws Exception {
        assertThat(result.getResponse().getStatus()).isEqualTo(201);
        return json(result).path("data");
    }

    private String examplePolicyId() {
        return jdbc.queryForObject("select id from automation_policy where policy_version = 'example-door-p1'",
                String.class);
    }

    // 가짜 AI 응답을 정해 접수하고 기대한 표시 상태인지 확인
    private String inspect(String quality, double calibrated, String expectedState) throws Exception {
        ai = r -> response(r, quality, quality.equals("DEFECT") ? 0.9 : 0.1, calibrated);
        JsonNode detail = submitAndWait();
        assertThat(detail.path("displayState").asText()).isEqualTo(expectedState);
        return detail.path("inspectionId").asText();
    }

    private String failedInspection() throws Exception {
        ai = aiServerError();
        JsonNode detail = submitAndWait();
        assertThat(detail.path("status").asText()).isEqualTo("FAILED");
        return detail.path("inspectionId").asText();
    }

    private String manualOf(String failedId) throws Exception {
        MvcResult result = call(post("/api/v1/inspections/" + failedId + "/manual"), worker());
        assertThat(result.getResponse().getStatus()).isEqualTo(201);
        return json(result).at("/data/inspectionId").asText();
    }

    private void confirm(String id, String judgement) throws Exception {
        assertThat(postJson("/api/v1/inspections/" + id + "/confirm", Map.of("finalJudgement", judgement), worker())
                .getResponse().getStatus()).isEqualTo(200);
    }

    private String openRequest(String id, String claimed) throws Exception {
        MvcResult result = postJson("/api/v1/inspections/" + id + "/judgement-requests",
                Map.of("claimedJudgement", claimed, "reason", "실물 확인 결과 다름"), worker());
        assertThat(result.getResponse().getStatus()).isEqualTo(201);
        return json(result).at("/data/requestId").asText();
    }

    private void resolve(String requestId, String decision) throws Exception {
        assertThat(postJson("/api/v1/admin/judgement-requests/" + requestId + "/resolve",
                Map.of("decision", decision, "note", "확인함"), admin()).getResponse().getStatus()).isEqualTo(200);
    }

    // 접수 시각을 KST 시각으로 옮김 (저장 값은 서버 기본 시간대)
    private void receivedAtKst(String id, String kstDateTime) {
        LocalDateTime serverLocal = ZonedDateTime.of(LocalDateTime.parse(kstDateTime), KST)
                .withZoneSameInstant(ZoneId.systemDefault()).toLocalDateTime();
        jdbc.update("update inspection set received_at = ? where id = ?", serverLocal, id);
    }

    private MvcResult daily(String from, String to) throws Exception {
        var request = get(DAILY).param("partCode", "DOOR").param("from", from);
        return call(to == null ? request : request.param("to", to), admin());
    }

    private List<JsonNode> rows(String from, String to) throws Exception {
        MvcResult result = daily(from, to);
        assertThat(result.getResponse().getStatus()).isEqualTo(200);
        return StreamSupport.stream(json(result).path("data").spliterator(), false).toList();
    }

    private static JsonNode row(List<JsonNode> rows, String date, String policyId, String calibratorVersion) {
        return rows.stream()
                .filter(r -> r.path("date").asText().equals(date))
                .filter(r -> policyId == null ? r.path("policyId").isNull() : r.path("policyId").asText().equals(policyId))
                .filter(r -> calibratorVersion == null ? r.path("calibratorVersion").isNull()
                        : r.path("calibratorVersion").asText().equals(calibratorVersion))
                .findFirst().orElseThrow(() -> new AssertionError("행 없음: " + date + " " + policyId));
    }

    private static void assertCounts(JsonNode row, int total, int autoPass, int autoFail, int reviewDone,
                                     int reviewTotal, int manualDone, int manualTotal, int failed) {
        assertThat(row.path("total").asInt()).as("total").isEqualTo(total);
        assertThat(row.path("autoPass").asInt()).as("autoPass").isEqualTo(autoPass);
        assertThat(row.path("autoFail").asInt()).as("autoFail").isEqualTo(autoFail);
        assertThat(row.at("/review/done").asInt()).as("review.done").isEqualTo(reviewDone);
        assertThat(row.at("/review/total").asInt()).as("review.total").isEqualTo(reviewTotal);
        assertThat(row.at("/manual/done").asInt()).as("manual.done").isEqualTo(manualDone);
        assertThat(row.at("/manual/total").asInt()).as("manual.total").isEqualTo(manualTotal);
        assertThat(row.path("failed").asInt()).as("failed").isEqualTo(failed);
    }

    private static void assertOpposite(JsonNode row, int passThenFail, int failThenPass, int resolved, int open) {
        assertThat(row.at("/confirmedOpposite/autoPassThenFail").asInt()).as("autoPassThenFail").isEqualTo(passThenFail);
        assertThat(row.at("/confirmedOpposite/autoFailThenPass").asInt()).as("autoFailThenPass").isEqualTo(failThenPass);
        assertThat(row.at("/confirmedOpposite/resolvedRequests").asInt()).as("resolvedRequests").isEqualTo(resolved);
        assertThat(row.path("openRequests").asInt()).as("openRequests").isEqualTo(open);
    }

    // ---- 날짜별 이력 ----

    @Test
    @DisplayName("날짜별 이력: KST 날짜·정책 버전별 행, 다음 날 판정 반영, 수동 전환·FAILED·판정 확인 요청 집계")
    void dailyRows() throws Exception {
        String example = examplePolicyId();
        // 예시 정책(통과 0.05, 자동 불량 꺼짐)
        String a1 = inspect("GOOD", 0.021, "AUTO_PASS");
        String r1 = inspect("GOOD", 0.2, "REVIEW_PENDING");
        // 자동 불량 켠 정책
        String autoFailPolicy = activeAutoFailPolicy().path("policyId").asText();
        String f1 = inspect("DEFECT", 0.85, "AUTO_FAIL");
        String f2 = inspect("DEFECT", 0.9, "AUTO_FAIL");
        String a2 = inspect("GOOD", 0.025, "AUTO_PASS");
        String r2 = inspect("DEFECT", 0.5, "REVIEW_PENDING");
        // 적용 정책 없음 → REVIEW(NO_ACTIVE_POLICY)
        jdbc.update("update automation_policy set active = false");
        String n1 = inspect("GOOD", 0.01, "REVIEW_PENDING");
        // 분석 실패 2건, 그중 1건은 수동 전환
        String x1 = failedInspection();
        String x2 = failedInspection();
        String m1 = manualOf(x1);

        for (String id : List.of(a1, r1, f1, f2, a2, r2)) {
            receivedAtKst(id, "2025-01-10T23:30:00");
        }
        receivedAtKst(n1, "2025-01-11T00:30:00");   // 자정 넘어 다음 날
        receivedAtKst(x1, "2025-01-10T10:00:00");
        receivedAtKst(x2, "2025-01-10T11:00:00");
        receivedAtKst(m1, "2025-01-11T09:00:00");   // 수동 전환은 새 검사가 생긴 날짜

        // 판정·요청은 지금(나중 날짜) 하지만 원래 날짜 행에 반영
        confirm(r1, "PASS");
        confirm(m1, "FAIL");
        resolve(openRequest(a1, "FAIL"), "CORRECT");   // 자동 통과 후 불량
        resolve(openRequest(f1, "PASS"), "KEEP");      // 유지: 처리된 요청만 셈
        resolve(openRequest(f2, "PASS"), "CORRECT");   // 자동 불량 후 정상
        openRequest(a2, "FAIL");                       // 대기

        List<JsonNode> rows = rows("2025-01-10", "2025-01-12");
        assertThat(rows).hasSize(5);
        // 최신 날짜부터, 날짜 안에서는 정책 행 먼저
        assertThat(rows.stream().map(r -> r.path("date").asText()).toList())
                .containsExactly("2025-01-11", "2025-01-11", "2025-01-10", "2025-01-10", "2025-01-10");
        assertThat(rows.get(4).path("policyId").isNull()).isTrue();

        JsonNode exampleRow = row(rows, "2025-01-10", example, "mock-cal-v1");
        assertThat(exampleRow.path("policyVersion").asText()).isEqualTo("example-door-p1");
        assertThat(exampleRow.path("modelVersion").asText()).isEqualTo(MOCK_MODEL);
        assertThat(exampleRow.path("passThreshold").asDouble()).isEqualTo(0.05);
        assertThat(exampleRow.path("failThreshold").isNull()).isTrue();
        assertThat(exampleRow.path("autoFailEnabled").asBoolean()).isFalse();
        assertCounts(exampleRow, 2, 1, 0, 1, 1, 0, 0, 0);
        assertOpposite(exampleRow, 1, 0, 1, 0);

        JsonNode autoFailRow = row(rows, "2025-01-10", autoFailPolicy, "mock-cal-v1");
        assertThat(autoFailRow.path("passThreshold").asDouble()).isEqualTo(0.03);
        assertThat(autoFailRow.path("failThreshold").asDouble()).isEqualTo(0.8);
        assertThat(autoFailRow.path("autoFailEnabled").asBoolean()).isTrue();
        assertCounts(autoFailRow, 4, 1, 2, 0, 1, 0, 0, 0);
        assertOpposite(autoFailRow, 0, 1, 2, 1);

        // 분석 실패는 total에 넣지 않는 장애 기록 (정책·보정기 없는 행)
        JsonNode failedRow = row(rows, "2025-01-10", null, null);
        assertThat(failedRow.path("policyVersion").isNull()).isTrue();
        assertThat(failedRow.path("passThreshold").isNull()).isTrue();
        assertCounts(failedRow, 0, 0, 0, 0, 0, 0, 0, 2);

        // 정책 없음 REVIEW와 수동 전환은 각각 정책 없는 행
        JsonNode noPolicyRow = row(rows, "2025-01-11", null, "mock-cal-v1");
        assertCounts(noPolicyRow, 1, 0, 0, 0, 1, 0, 0, 0);
        JsonNode manualRow = row(rows, "2025-01-11", null, null);
        assertThat(manualRow.path("modelVersion").asText()).isEqualTo(MOCK_MODEL);
        // 수동 전환은 total·REVIEW에 포함하고 그중 몇 건인지 manual로 따로 (합의 11/23 김도현·홍승인)
        assertCounts(manualRow, 1, 0, 0, 1, 1, 1, 1, 0);
        assertOpposite(manualRow, 0, 0, 0, 0);

        // to는 포함하지 않음
        assertThat(rows("2025-01-10", "2025-01-11")).allMatch(r -> r.path("date").asText().equals("2025-01-10"))
                .hasSize(3);
        assertThat(rows("2025-01-12", "2025-01-13")).isEmpty();
    }

    @Test
    @DisplayName("날짜 경계는 KST: 23:59:59는 그날, 00:00:00은 다음 날")
    void kstBoundary() throws Exception {
        String before = inspect("GOOD", 0.021, "AUTO_PASS");
        String after = inspect("GOOD", 0.021, "AUTO_PASS");
        receivedAtKst(before, "2025-03-01T23:59:59");
        receivedAtKst(after, "2025-03-02T00:00:00");

        List<JsonNode> rows = rows("2025-03-01", "2025-03-03");
        assertThat(rows.stream().map(r -> r.path("date").asText() + ":" + r.path("autoPass").asInt()).toList())
                .containsExactly("2025-03-02:1", "2025-03-01:1");
    }

    // ---- 기준 상세 ----

    @Test
    @DisplayName("기준 상세: 통과 기준 위(초과~이하)·불량 기준 아래(이상~미만) REVIEW, 판정 결과별 건수, 같은 날짜·정책만")
    void detailBands() throws Exception {
        String policyId = activeAutoFailPolicy().path("policyId").asText();
        String p05 = inspect("GOOD", 0.05, "REVIEW_PENDING");
        String p06 = inspect("GOOD", 0.06, "REVIEW_PENDING");
        String p08 = inspect("GOOD", 0.08, "REVIEW_PENDING");        // 통과 기준 + band: 포함
        String p0801 = inspect("GOOD", 0.0801, "REVIEW_PENDING");    // 밖
        String d75 = inspect("DEFECT", 0.75, "REVIEW_PENDING");      // 불량 기준 − band: 포함
        String d7999 = inspect("DEFECT", 0.7999, "REVIEW_PENDING");
        String d7499 = inspect("DEFECT", 0.7499, "REVIEW_PENDING");  // 밖
        String d80 = inspect("DEFECT", 0.8, "AUTO_FAIL");            // 불량 기준: 자동 불량이라 제외
        String dLow = inspect("DEFECT", 0.05, "REVIEW_PENDING"); // DEFECT 예측은 통과 구간에 넣지 않음
        String otherDay = inspect("GOOD", 0.07, "REVIEW_PENDING");
        for (String id : List.of(p05, p06, p08, p0801, d75, d7999, d7499, d80, dLow)) {
            receivedAtKst(id, "2025-02-05T12:00:00");
        }
        receivedAtKst(otherDay, "2025-02-06T12:00:00");
        confirm(p05, "PASS");
        confirm(p06, "FAIL");
        confirm(d75, "FAIL");

        MvcResult result = call(get(DETAIL).param("partCode", "DOOR").param("date", "2025-02-05")
                .param("policyId", policyId), admin());
        assertThat(result.getResponse().getStatus()).isEqualTo(200);
        JsonNode data = json(result).path("data");
        assertThat(data.path("date").asText()).isEqualTo("2025-02-05");
        assertThat(data.path("policyId").asText()).isEqualTo(policyId);
        assertThat(data.path("modelVersion").asText()).isEqualTo(MOCK_MODEL);
        assertThat(data.path("band").asDouble()).isEqualTo(0.05);
        assertThat(data.has("reference")).isTrue();
        assertThat(data.path("reference").isNull()).isTrue();

        JsonNode pass = data.path("passBand");
        assertThat(pass.path("from").asDouble()).isEqualTo(0.03);
        assertThat(pass.path("to").asDouble()).isEqualTo(0.08);
        assertThat(bandCounts(pass)).containsExactly(3, 1, 1, 1);
        assertThat(itemIds(pass)).containsExactly(p05, p06, p08);
        JsonNode first = pass.path("items").get(0);
        assertThat(first.path("inspectionNo").asText()).startsWith("INS-");
        assertThat(first.path("calibratedDefectProbability").asDouble()).isEqualTo(0.05);
        assertThat(first.path("finalJudgement").asText()).isEqualTo("PASS");
        assertThat(first.path("correctedJudgement").isNull()).isTrue();
        assertThat(pass.path("items").get(2).path("finalJudgement").isNull()).isTrue();

        JsonNode fail = data.path("failBand");
        assertThat(fail.path("from").asDouble()).isEqualTo(0.75);
        assertThat(fail.path("to").asDouble()).isEqualTo(0.8);
        assertThat(bandCounts(fail)).containsExactly(2, 0, 1, 1);
        assertThat(itemIds(fail)).containsExactly(d75, d7999);

        // band 조정: 통과 구간 (0.03, 0.06]
        JsonNode narrow = json(call(get(DETAIL).param("partCode", "DOOR").param("date", "2025-02-05")
                .param("policyId", policyId).param("band", "0.03"), admin())).path("data");
        assertThat(itemIds(narrow.path("passBand"))).containsExactly(p05, p06);

        // 불량 기준이 없는 정책은 불량 구간 null
        JsonNode example = json(call(get(DETAIL).param("partCode", "DOOR").param("date", "2025-02-05")
                .param("policyId", examplePolicyId()), admin())).path("data");
        assertThat(example.path("failBand").isNull()).isTrue();
        assertThat(bandCounts(example.path("passBand"))).containsExactly(0, 0, 0, 0);
    }

    private static List<Integer> bandCounts(JsonNode band) {
        return List.of(band.path("total").asInt(), band.path("pass").asInt(), band.path("fail").asInt(),
                band.path("pending").asInt());
    }

    private static List<String> itemIds(JsonNode band) {
        List<String> ids = new ArrayList<>();
        band.path("items").forEach(i -> ids.add(i.path("inspectionId").asText()));
        return ids;
    }

    // ---- 오류 ----

    @Test
    @DisplayName("검증: partCode·날짜·기간·band 400, 없는 정책 404, 관리자 외 403")
    void validation() throws Exception {
        assertThat(errorCode(call(get(DAILY).param("from", "2025-01-01").param("to", "2025-01-02"), admin())))
                .isEqualTo("INVALID_PARAMETER");
        assertThat(errorCode(call(get(DAILY).param("partCode", "NOPE").param("from", "2025-01-01")
                .param("to", "2025-01-02"), admin()))).isEqualTo("INVALID_PART_CODE");
        assertBadRequest(daily("2025-1-01", "2025-01-02"));
        assertBadRequest(daily("2025-01-02", "2025-01-02"));   // from < to
        assertBadRequest(daily("2025-01-03", "2025-01-02"));
        assertBadRequest(daily("2025-01-01", null));
        assertBadRequest(daily("2025-01-01", "2025-04-04"));   // 93일
        assertThat(daily("2025-01-01", "2025-04-03").getResponse().getStatus()).isEqualTo(200); // 92일

        String policyId = examplePolicyId();
        for (String band : List.of("0.0009", "0.51", "abc", "NaN")) {
            assertBadRequest(call(get(DETAIL).param("partCode", "DOOR").param("date", "2025-01-01")
                    .param("policyId", policyId).param("band", band), admin()));
        }
        assertThat(call(get(DETAIL).param("partCode", "DOOR").param("date", "2025-01-01")
                .param("policyId", policyId).param("band", "0.5"), admin()).getResponse().getStatus()).isEqualTo(200);
        assertBadRequest(call(get(DETAIL).param("partCode", "DOOR").param("policyId", policyId), admin()));
        assertBadRequest(call(get(DETAIL).param("partCode", "DOOR").param("date", "2025-01-01"), admin()));
        MvcResult missing = call(get(DETAIL).param("partCode", "DOOR").param("date", "2025-01-01")
                .param("policyId", "00000000-0000-0000-0000-000000000000"), admin());
        assertThat(missing.getResponse().getStatus()).isEqualTo(404);
        assertThat(errorCode(missing)).isEqualTo("POLICY_NOT_FOUND");

        assertThat(call(get(DAILY).param("partCode", "DOOR").param("from", "2025-01-01").param("to", "2025-01-02"),
                worker()).getResponse().getStatus()).isEqualTo(403);
        assertThat(call(get(DETAIL).param("partCode", "DOOR").param("date", "2025-01-01").param("policyId", policyId),
                worker()).getResponse().getStatus()).isEqualTo(403);
    }

    private void assertBadRequest(MvcResult result) throws Exception {
        assertThat(result.getResponse().getStatus()).isEqualTo(400);
        assertThat(errorCode(result)).isEqualTo("INVALID_PARAMETER");
    }
}
