package com.capstone.inspection.integration;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MvcResult;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

// 계약 v4 6.9 관리자 정책, V5 제약 아래에서 동작 확인
class PolicyIntegrationTest extends IntegrationTestBase {

    private static final String POLICIES = "/api/v1/admin/policies";

    private Map<String, Object> body(String model, String calibrator, String version, double threshold, double min,
                                     double max) {
        Map<String, Object> body = new HashMap<>();
        body.put("modelVersion", model);
        body.put("calibratorVersion", calibrator);
        body.put("policyVersion", version);
        body.put("passThreshold", threshold);
        body.put("validatedMin", min);
        body.put("validatedMax", max);
        body.put("metrics", Map.of("sampleCount", 10));
        return body;
    }

    private JsonNode register(String model, String calibrator) throws Exception {
        MvcResult result = postJson(POLICIES, body(model, calibrator, unique("example-it"), 0.03, 0.02, 0.08), admin());
        assertThat(result.getResponse().getStatus()).isEqualTo(201);
        return json(result).path("data");
    }

    private JsonNode readyPolicy() throws Exception {
        JsonNode policy = register(MOCK_MODEL, "mock-cal-v1");
        assertThat(policy.path("ready").asBoolean()).isTrue();
        return policy;
    }

    private MvcResult threshold(String id, double value) throws Exception {
        return postJson(POLICIES + "/" + id + "/threshold", Map.of("passThreshold", value), admin());
    }

    private MvcResult activate(String id) throws Exception {
        return call(post(POLICIES + "/" + id + "/activate"), admin());
    }

    private List<String> activeVersions() {
        return jdbc.queryForList("select policy_version from automation_policy where active = true", String.class);
    }

    private String exampleId() {
        return jdbc.queryForObject("select id from automation_policy where policy_version = 'example-door-p1'",
                String.class);
    }

    @Test
    @DisplayName("등록: 기준치 범위 밖 400 (DB 제약 500 아님)")
    void registerOutOfRange() throws Exception {
        MvcResult result = postJson(POLICIES, body(MOCK_MODEL, "mock-cal-v1", unique("example-it"), 0.5, 0.02, 0.08), admin());
        assertThat(result.getResponse().getStatus()).isEqualTo(400);
        assertThat(errorCode(result)).isEqualTo("POLICY_THRESHOLD_OUT_OF_RANGE");
    }

    @Test
    @DisplayName("등록: validatedMin > validatedMax 400")
    void registerMinOverMax() throws Exception {
        MvcResult result = postJson(POLICIES, body(MOCK_MODEL, "mock-cal-v1", unique("example-it"), 0.05, 0.08, 0.02), admin());
        assertThat(result.getResponse().getStatus()).isEqualTo(400);
        assertThat(errorCode(result)).isEqualTo("INVALID_PARAMETER");
    }

    @Test
    @DisplayName("등록: 없는 모델 404, 같은 이름 409")
    void registerErrors() throws Exception {
        assertThat(errorCode(postJson(POLICIES, body("nope", "c", unique("example-it"), 0.03, 0.02, 0.08), admin())))
                .isEqualTo("MODEL_NOT_FOUND");
        MvcResult duplicate = postJson(POLICIES, body(MOCK_MODEL, "mock-cal-v1", "example-door-p1", 0.03, 0.02, 0.08), admin());
        assertThat(duplicate.getResponse().getStatus()).isEqualTo(409);
        assertThat(errorCode(duplicate)).isEqualTo("POLICY_VERSION_DUPLICATE");
    }

    @Test
    @DisplayName("보정기 null 모델에는 값을 보내도 ready 정책이 만들어지지 않고 적용 409")
    void modelWithoutCalibrator() throws Exception {
        assertThat(register(REAL_MODEL, null).path("ready").asBoolean()).isFalse();
        JsonNode policy = register(REAL_MODEL, "fake-cal");
        assertThat(policy.path("ready").asBoolean()).isFalse();
        MvcResult result = activate(policy.path("policyId").asText());
        assertThat(result.getResponse().getStatus()).isEqualTo(409);
        assertThat(errorCode(result)).isEqualTo("POLICY_NOT_READY");
    }

    @Test
    @DisplayName("보정기 불일치는 ready 아님, 적용 409")
    void notReady() throws Exception {
        JsonNode policy = register(MOCK_MODEL, "other-cal");
        assertThat(policy.path("ready").asBoolean()).isFalse();
        MvcResult result = activate(policy.path("policyId").asText());
        assertThat(result.getResponse().getStatus()).isEqualTo(409);
        assertThat(errorCode(result)).isEqualTo("POLICY_NOT_READY");
    }

    @Test
    @DisplayName("모델이 비활성이면 ready 정책도 적용 409")
    void inactiveModel() throws Exception {
        JsonNode policy = readyPolicy();
        jdbc.update("update ai_model set active = false where model_version = ?", MOCK_MODEL);
        assertThat(errorCode(activate(policy.path("policyId").asText()))).isEqualTo("POLICY_NOT_READY");
    }

    @Test
    @DisplayName("기준치 조정: 범위 밖 400, 없는 정책 404")
    void thresholdErrors() throws Exception {
        MvcResult outOfRange = threshold(exampleId(), 0.9);
        assertThat(outOfRange.getResponse().getStatus()).isEqualTo(400);
        assertThat(errorCode(outOfRange)).isEqualTo("POLICY_THRESHOLD_OUT_OF_RANGE");
        assertThat(errorCode(threshold("nope", 0.05))).isEqualTo("POLICY_NOT_FOUND");
    }

    @Test
    @DisplayName("기준치 조정: 새 버전을 만들고 기존 행은 그대로, 재조정 이름은 -t2")
    void thresholdNewVersion() throws Exception {
        JsonNode root = readyPolicy();
        String rootId = root.path("policyId").asText();
        String rootVersion = root.path("policyVersion").asText();

        JsonNode first = json(threshold(rootId, 0.04)).path("data");
        assertThat(first.path("policyVersion").asText()).isEqualTo(rootVersion + "-t1");
        assertThat(first.path("basedOnPolicyId").asText()).isEqualTo(rootId);
        assertThat(first.path("active").asBoolean()).isFalse();
        assertThat(first.path("ready").asBoolean()).isTrue();
        assertThat(first.path("passThreshold").asDouble()).isEqualTo(0.04);

        JsonNode second = json(threshold(first.path("policyId").asText(), 0.05)).path("data");
        assertThat(second.path("policyVersion").asText()).isEqualTo(rootVersion + "-t2");
        assertThat(second.path("basedOnPolicyId").asText()).isEqualTo(first.path("policyId").asText());

        Double stored = jdbc.queryForObject("select pass_threshold from automation_policy where id = ?", Double.class, rootId);
        assertThat(stored).isEqualTo(0.03);
    }

    @Test
    @DisplayName("적용: 같은 모델의 기존 active 정책 중지 (V5 uq_policy_active_model)")
    void activateReplaces() throws Exception {
        JsonNode policy = readyPolicy();
        MvcResult result = activate(policy.path("policyId").asText());
        assertThat(result.getResponse().getStatus()).isEqualTo(200);
        assertThat(json(result).at("/data/active").asBoolean()).isTrue();
        assertThat(json(result).at("/data/activatedAt").isNull()).isFalse();
        assertThat(activeVersions()).containsExactly(policy.path("policyVersion").asText());
    }

    @Test
    @DisplayName("동시 적용: active는 1개만 남고 500 없음")
    void activateConcurrent() throws Exception {
        String a = readyPolicy().path("policyId").asText();
        String b = readyPolicy().path("policyId").asText();
        for (int round = 0; round < 5; round++) {
            CountDownLatch start = new CountDownLatch(1);
            ExecutorService pool = Executors.newFixedThreadPool(2);
            try {
                List<Future<Integer>> results = List.of(a, b).stream().map(id -> pool.submit(() -> {
                    start.await();
                    return activate(id).getResponse().getStatus();
                })).toList();
                start.countDown();
                assertThat(results.get(0).get()).isIn(200, 409);
                assertThat(results.get(1).get()).isIn(200, 409);
            } finally {
                pool.shutdownNow();
            }
            assertThat(activeVersions()).hasSize(1);
        }
    }

    @Test
    @DisplayName("중지 후 정책 없음: 다음 검사는 REVIEW(NO_ACTIVE_POLICY), /parts policyActive=false")
    void deactivate() throws Exception {
        MvcResult result = call(post(POLICIES + "/" + exampleId() + "/deactivate"), admin());
        assertThat(result.getResponse().getStatus()).isEqualTo(200);
        assertThat(activeVersions()).isEmpty();
        assertThat(submitAndWait().at("/policy/reviewReason").asText()).isEqualTo("NO_ACTIVE_POLICY");
        JsonNode door = doorItem();
        assertThat(door.path("policyActive").asBoolean()).isFalse();
    }

    @Test
    @DisplayName("기준을 바꿔도 과거 검사의 policy_id·pass_threshold_applied는 그대로, 새 검사는 새 기준")
    void pastInspectionUnchanged() throws Exception {
        String pastId = submitAndWait().path("inspectionId").asText();
        Map<String, Object> before = jdbc.queryForMap(
                "select policy_id, pass_threshold_applied from inspection where id = ?", pastId);

        JsonNode adjusted = json(threshold(exampleId(), 0.03)).path("data");
        assertThat(activate(adjusted.path("policyId").asText()).getResponse().getStatus()).isEqualTo(200);

        assertThat(jdbc.queryForMap("select policy_id, pass_threshold_applied from inspection where id = ?", pastId))
                .isEqualTo(before);
        JsonNode next = submitAndWait();
        assertThat(next.at("/policy/policyVersion").asText()).isEqualTo(adjusted.path("policyVersion").asText());
        assertThat(next.at("/policy/passThreshold").asDouble()).isEqualTo(0.03);
    }

    @Test
    @DisplayName("목록 필터: partCode·active, 없는 부품 400")
    void listFilter() throws Exception {
        JsonNode active = json(call(get(POLICIES).param("partCode", "DOOR").param("active", "true"), admin())).path("data");
        assertThat(active).hasSize(1);
        assertThat(active.get(0).path("policyVersion").asText()).isEqualTo("example-door-p1");
        assertThat(json(call(get(POLICIES).param("partCode", "BUMPER"), admin())).path("data")).isEmpty();
        assertThat(errorCode(call(get(POLICIES).param("partCode", "NOPE"), admin()))).isEqualTo("INVALID_PART_CODE");
    }

    private JsonNode doorItem() throws Exception {
        for (JsonNode part : json(call(get("/api/v1/parts"), worker())).path("data")) {
            if (part.path("partCode").asText().equals("DOOR")) {
                return part.path("items").get(0);
            }
        }
        throw new AssertionError("DOOR 없음");
    }
}
