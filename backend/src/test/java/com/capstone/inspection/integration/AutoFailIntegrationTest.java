package com.capstone.inspection.integration;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MvcResult;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

// 자동 불량 AUTO_FAIL (계약 4.1·6.9, V13)
//   정책은 테스트마다 새로 등록해 쓰고, 적용 상태는 IntegrationTestBase가 예시 정책(example-door-p1)으로 되돌림
//   재확인은 켜 둔 설정(RecheckConstraintIntegrationTest와 같은 값, 컨텍스트 공유)으로 AUTO_FAIL이 표본에 안 뽑히는지 확인
@TestPropertySource(properties = {"app.recheck.enabled=true", "app.recheck.near-rate=1.0", "app.recheck.mid-rate=1.0", "app.recheck.low-rate=0"})
class AutoFailIntegrationTest extends IntegrationTestBase {

    private static final String POLICIES = "/api/v1/admin/policies";

    // 자동 통과 0.03(검증 0.02~0.08) 정책 등록
    private JsonNode register() throws Exception {
        Map<String, Object> body = new HashMap<>();
        body.put("modelVersion", MOCK_MODEL);
        body.put("calibratorVersion", "mock-cal-v1");
        body.put("policyVersion", unique("example-af"));
        body.put("passThreshold", 0.03);
        body.put("validatedMin", 0.02);
        body.put("validatedMax", 0.08);
        body.put("metrics", Map.of("sampleCount", 10));
        MvcResult result = postJson(POLICIES, body, admin());
        assertThat(result.getResponse().getStatus()).isEqualTo(201);
        return json(result).path("data");
    }

    private MvcResult failThreshold(String id, Double value, Double min, Double max) throws Exception {
        Map<String, Object> body = new HashMap<>();
        body.put("failThreshold", value);
        body.put("failValidatedMin", min);
        body.put("failValidatedMax", max);
        return postJson(POLICIES + "/" + id + "/fail-threshold", body, admin());
    }

    private MvcResult autoFail(String id, boolean enabled) throws Exception {
        return postJson(POLICIES + "/" + id + "/auto-fail", Map.of("enabled", enabled), admin());
    }

    private JsonNode created(MvcResult result) throws Exception {
        assertThat(result.getResponse().getStatus()).isEqualTo(201);
        return json(result).path("data");
    }

    private void activate(String id) throws Exception {
        assertThat(call(post(POLICIES + "/" + id + "/activate"), admin()).getResponse().getStatus()).isEqualTo(200);
    }

    // 불량 기준 0.8(검증 0.7~0.9)을 넣고 자동 불량을 켠 정책을 적용
    private JsonNode activeAutoFailPolicy() throws Exception {
        JsonNode withFail = created(failThreshold(register().path("policyId").asText(), 0.8, 0.7, 0.9));
        JsonNode enabled = created(autoFail(withFail.path("policyId").asText(), true));
        activate(enabled.path("policyId").asText());
        return enabled;
    }

    private List<String> historyIds(String displayState) throws Exception {
        List<String> ids = new ArrayList<>();
        JsonNode items = json(call(get("/api/v1/inspections").param("displayState", displayState).param("size", "100"),
                worker())).at("/data/items");
        items.forEach(item -> ids.add(item.path("inspectionId").asText()));
        return ids;
    }

    // MySQL CHECK 위반(3819)은 Spring에서 UncategorizedSQLException으로 올라오므로 메시지의 제약 이름으로 확인
    private void assertRejectedBy(String constraint, String sql, Object... args) {
        assertThatThrownBy(() -> jdbc.update(sql, args)).hasMessageContaining("Check constraint '" + constraint + "'");
    }

    @Test
    @DisplayName("자동 불량 켠 정책: DEFECT + 보정 ≥ 기준 → AUTO_FAIL·FAIL·SYSTEM, 작업자 확인·표본 대상 아님")
    void autoFailEndToEnd() throws Exception {
        JsonNode policy = activeAutoFailPolicy();
        ai = r -> response(r, "DEFECT", 0.95, 0.85);

        JsonNode detail = submitAndWait();
        String id = detail.path("inspectionId").asText();
        assertThat(detail.path("status").asText()).isEqualTo("COMPLETED");
        assertThat(detail.path("displayState").asText()).isEqualTo("AUTO_FAIL");
        assertThat(detail.at("/policy/recommendedAction").asText()).isEqualTo("AUTO_FAIL");
        assertThat(detail.at("/policy/reviewReason").isNull()).isTrue();
        assertThat(detail.at("/policy/policyVersion").asText()).isEqualTo(policy.path("policyVersion").asText());
        assertThat(detail.at("/policy/passThreshold").asDouble()).isEqualTo(0.03);
        assertThat(detail.at("/policy/failThreshold").asDouble()).isEqualTo(0.8);
        assertThat(detail.at("/judgement/finalJudgement").asText()).isEqualTo("FAIL");
        assertThat(detail.at("/judgement/judgedBy").asText()).isEqualTo("SYSTEM");
        assertThat(detail.at("/judgement/confirmedBy").isNull()).isTrue();
        // Grad-CAM은 DEFECT 예측이라 생성 시도 (가짜 AI는 이미지를 주지 않아 FAILED)
        assertThat(detail.at("/images/gradcamStatus").asText()).isNotEqualTo("NOT_REQUIRED");

        assertThat(jdbc.queryForObject("select count(*) from worker_confirmation where inspection_id = ?", Long.class, id))
                .isZero();
        assertThat(jdbc.queryForObject("select fail_threshold_applied from inspection where id = ?", Double.class, id))
                .isEqualTo(0.8);
        assertThat(jdbc.queryForObject("select recheck_rule_id from inspection where id = ?", String.class, id)).isNull();

        // 작업자 확인 대상이 아님
        MvcResult confirm = postJson("/api/v1/inspections/" + id + "/confirm", Map.of("finalJudgement", "PASS"), worker());
        assertThat(confirm.getResponse().getStatus()).isEqualTo(409);
        assertThat(errorCode(confirm)).isEqualTo("NOT_REVIEWABLE");

        // 이력 필터: AUTO_FAIL로만 잡히고 확인 대기·확인 완료·불일치에는 없음
        assertThat(historyIds("AUTO_FAIL")).contains(id);
        assertThat(historyIds("REVIEW_PENDING")).doesNotContain(id);
        assertThat(historyIds("REVIEW_DONE")).doesNotContain(id);
        assertThat(historyIds("AUTO_PASS")).doesNotContain(id);
        String mismatch = call(get("/api/v1/inspections").param("mismatch", "ANY").param("size", "100"), worker())
                .getResponse().getContentAsString();
        assertThat(mismatch).doesNotContain(id);
        String queue = call(get("/api/v1/monitoring/queue").param("size", "100"), worker())
                .getResponse().getContentAsString();
        assertThat(queue).doesNotContain(id);

        // 표본 재확인: 뒤이은 AUTO_PASS의 추출 결정이 끝난 뒤에도 AUTO_FAIL 건에는 결정 행이 없음
        ai = r -> response(r, "GOOD", 0.1, 0.025);
        assertThat(submitAndWaitForRecheckDecision().path("displayState").asText()).isEqualTo("AUTO_PASS");
        assertThat(jdbc.queryForObject("select count(*) from auto_pass_recheck where inspection_id = ?", Long.class, id))
                .isZero();
    }

    @Test
    @DisplayName("기준과 같은 보정 확률도 AUTO_FAIL, 기준 미만은 REVIEW(DEFECT_PREDICTED)에 불량 기준 스냅숏")
    void boundaryAndBelow() throws Exception {
        activeAutoFailPolicy();
        ai = r -> response(r, "DEFECT", 0.9, 0.8);
        assertThat(submitAndWait().path("displayState").asText()).isEqualTo("AUTO_FAIL");

        ai = r -> response(r, "DEFECT", 0.9, 0.79);
        JsonNode review = submitAndWait();
        assertThat(review.path("displayState").asText()).isEqualTo("REVIEW_PENDING");
        assertThat(review.at("/policy/reviewReason").asText()).isEqualTo("DEFECT_PREDICTED");
        assertThat(review.at("/policy/failThreshold").asDouble()).isEqualTo(0.8);
    }

    @Test
    @DisplayName("기본은 꺼짐: 새 정책은 autoFailEnabled=false·failThreshold=null, 기준만 넣고 켜지 않으면 REVIEW 그대로")
    void defaultOff() throws Exception {
        JsonNode root = register();
        assertThat(root.path("autoFailEnabled").asBoolean()).isFalse();
        assertThat(root.path("failThreshold").isNull()).isTrue();
        assertThat(root.path("failValidatedMin").isNull()).isTrue();
        assertThat(root.path("failValidatedMax").isNull()).isTrue();

        JsonNode withFail = created(failThreshold(root.path("policyId").asText(), 0.8, 0.7, 0.9));
        assertThat(withFail.path("autoFailEnabled").asBoolean()).isFalse();
        activate(withFail.path("policyId").asText());
        ai = r -> response(r, "DEFECT", 0.99, 0.99);
        JsonNode detail = submitAndWait();
        assertThat(detail.path("displayState").asText()).isEqualTo("REVIEW_PENDING");
        assertThat(detail.at("/policy/reviewReason").asText()).isEqualTo("DEFECT_PREDICTED");
        assertThat(detail.at("/policy/failThreshold").isNull()).isTrue();
    }

    @Test
    @DisplayName("시드 예시 정책도 꺼진 채라 DEFECT 예측은 지금처럼 REVIEW")
    void seedPolicyUnchanged() throws Exception {
        ai = r -> response(r, "DEFECT", 0.99, 0.99);
        JsonNode detail = submitAndWait();
        assertThat(detail.path("displayState").asText()).isEqualTo("REVIEW_PENDING");
        assertThat(detail.at("/policy/policyVersion").asText()).isEqualTo("example-door-p1");
        assertThat(jdbc.queryForObject(
                "select count(*) from automation_policy where auto_fail_enabled = true and policy_version not like 'example-af-%'",
                Long.class)).isZero();
    }

    @Test
    @DisplayName("새 버전 이름: 원본 이름 + -f·-a·-t 번호, 직전 정책 연결, active=false, 자동 불량 값 승계")
    void versionsAndCarryOver() throws Exception {
        JsonNode root = register();
        String rootId = root.path("policyId").asText();
        String name = root.path("policyVersion").asText();

        JsonNode f1 = created(failThreshold(rootId, 0.8000004, 0.7, 0.9));
        assertThat(f1.path("policyVersion").asText()).isEqualTo(name + "-f1");
        assertThat(f1.path("basedOnPolicyId").asText()).isEqualTo(rootId);
        assertThat(f1.path("active").asBoolean()).isFalse();
        assertThat(f1.path("ready").asBoolean()).isTrue();
        assertThat(f1.path("passThreshold").asDouble()).isEqualTo(0.03);
        assertThat(f1.path("failThreshold").asDouble()).isEqualTo(0.8); // 소수 6자리 반올림
        assertThat(f1.path("failValidatedMin").asDouble()).isEqualTo(0.7);
        assertThat(f1.path("failValidatedMax").asDouble()).isEqualTo(0.9);

        JsonNode a1 = created(autoFail(f1.path("policyId").asText(), true));
        assertThat(a1.path("policyVersion").asText()).isEqualTo(name + "-a1");
        assertThat(a1.path("basedOnPolicyId").asText()).isEqualTo(f1.path("policyId").asText());
        assertThat(a1.path("active").asBoolean()).isFalse();
        assertThat(a1.path("autoFailEnabled").asBoolean()).isTrue();
        assertThat(a1.path("failThreshold").asDouble()).isEqualTo(0.8);

        // 기준치 조정도 자동 불량 값을 이어받음
        JsonNode t1 = created(postJson(POLICIES + "/" + a1.path("policyId").asText() + "/threshold",
                Map.of("passThreshold", 0.04), admin()));
        assertThat(t1.path("policyVersion").asText()).isEqualTo(name + "-t1");
        assertThat(t1.path("passThreshold").asDouble()).isEqualTo(0.04);
        assertThat(t1.path("autoFailEnabled").asBoolean()).isTrue();
        assertThat(t1.path("failThreshold").asDouble()).isEqualTo(0.8);
        assertThat(t1.path("failValidatedMin").asDouble()).isEqualTo(0.7);
        assertThat(t1.path("failValidatedMax").asDouble()).isEqualTo(0.9);

        // 불량 기준을 다시 바꿔도 켜짐 여부는 이어받고, 이름은 원본 기준 -f2
        JsonNode f2 = created(failThreshold(t1.path("policyId").asText(), 0.75, 0.7, 0.9));
        assertThat(f2.path("policyVersion").asText()).isEqualTo(name + "-f2");
        assertThat(f2.path("autoFailEnabled").asBoolean()).isTrue();
        assertThat(f2.path("passThreshold").asDouble()).isEqualTo(0.04);

        // 끄기: 기준은 남기고 꺼진 새 버전
        JsonNode a2 = created(autoFail(f2.path("policyId").asText(), false));
        assertThat(a2.path("policyVersion").asText()).isEqualTo(name + "-a2");
        assertThat(a2.path("autoFailEnabled").asBoolean()).isFalse();
        assertThat(a2.path("failThreshold").asDouble()).isEqualTo(0.75);

        // 기존 행은 그대로
        Map<String, Object> stored = jdbc.queryForMap(
                "select auto_fail_enabled, fail_threshold from automation_policy where id = ?", rootId);
        assertThat(stored.get("auto_fail_enabled")).isIn(false, 0, Boolean.FALSE);
        assertThat(stored.get("fail_threshold")).isNull();
    }

    @Test
    @DisplayName("불량 기준 검증: 범위 밖 400 OUT_OF_RANGE, min>max·기준 ≤ 통과 기준·0~1 밖·누락 400 INVALID_PARAMETER, 없는 정책 404")
    void failThresholdErrors() throws Exception {
        String id = register().path("policyId").asText();

        MvcResult outOfRange = failThreshold(id, 0.95, 0.7, 0.9);
        assertThat(outOfRange.getResponse().getStatus()).isEqualTo(400);
        assertThat(errorCode(outOfRange)).isEqualTo("POLICY_THRESHOLD_OUT_OF_RANGE");

        MvcResult minOverMax = failThreshold(id, 0.8, 0.9, 0.7);
        assertThat(minOverMax.getResponse().getStatus()).isEqualTo(400);
        assertThat(errorCode(minOverMax)).isEqualTo("INVALID_PARAMETER");

        MvcResult equalToPass = failThreshold(id, 0.03, 0.01, 0.5);
        assertThat(equalToPass.getResponse().getStatus()).isEqualTo(400);
        assertThat(errorCode(equalToPass)).isEqualTo("INVALID_PARAMETER");

        MvcResult belowPass = failThreshold(id, 0.02, 0.01, 0.5);
        assertThat(errorCode(belowPass)).isEqualTo("INVALID_PARAMETER");

        MvcResult overOne = failThreshold(id, 1.2, 0.7, 1.5);
        assertThat(overOne.getResponse().getStatus()).isEqualTo(400);
        assertThat(errorCode(overOne)).isEqualTo("INVALID_PARAMETER");

        MvcResult missing = failThreshold(id, 0.8, null, 0.9);
        assertThat(missing.getResponse().getStatus()).isEqualTo(400);
        assertThat(errorCode(missing)).isEqualTo("INVALID_PARAMETER");

        assertThat(errorCode(failThreshold("nope", 0.8, 0.7, 0.9))).isEqualTo("POLICY_NOT_FOUND");
        assertThat(errorCode(autoFail("nope", true))).isEqualTo("POLICY_NOT_FOUND");
        // 실패한 요청은 새 버전을 남기지 않음
        assertThat(jdbc.queryForObject("select count(*) from automation_policy where based_on_policy_id = ?",
                Long.class, id)).isZero();
    }

    @Test
    @DisplayName("불량 기준 없이 켜기 409 AUTO_FAIL_NOT_CONFIGURED, 끄기는 기준 없어도 가능, 작업자는 403")
    void autoFailNotConfigured() throws Exception {
        String id = register().path("policyId").asText();
        MvcResult result = autoFail(id, true);
        assertThat(result.getResponse().getStatus()).isEqualTo(409);
        assertThat(errorCode(result)).isEqualTo("AUTO_FAIL_NOT_CONFIGURED");

        assertThat(created(autoFail(id, false)).path("autoFailEnabled").asBoolean()).isFalse();

        MvcResult byWorker = postJson(POLICIES + "/" + id + "/auto-fail", Map.of("enabled", true), worker());
        assertThat(byWorker.getResponse().getStatus()).isEqualTo(403);
        MvcResult noBody = postJson(POLICIES + "/" + id + "/auto-fail", Map.of(), admin());
        assertThat(errorCode(noBody)).isEqualTo("INVALID_PARAMETER");
    }

    @Test
    @DisplayName("기준치 조정: 통과 기준이 불량 기준 이상이면 400 INVALID_PARAMETER")
    void passThresholdMustStayBelowFail() throws Exception {
        String id = register().path("policyId").asText();
        String withFail = created(failThreshold(id, 0.05, 0.04, 0.06)).path("policyId").asText();
        MvcResult result = postJson(POLICIES + "/" + withFail + "/threshold", Map.of("passThreshold", 0.05), admin());
        assertThat(result.getResponse().getStatus()).isEqualTo(400);
        assertThat(errorCode(result)).isEqualTo("INVALID_PARAMETER");
        assertThat(postJson(POLICIES + "/" + withFail + "/threshold", Map.of("passThreshold", 0.049), admin())
                .getResponse().getStatus()).isEqualTo(201);
    }

    @Test
    @DisplayName("V13 CHECK: AUTO_FAIL은 불량 기준 스냅숏 필수·보정 확률 ≥ 스냅숏, 정책은 켜면 기준 필수·불량 기준 > 통과 기준")
    void dbChecks() throws Exception {
        activeAutoFailPolicy();
        ai = r -> response(r, "DEFECT", 0.95, 0.85);
        String id = submitAndWait().path("inspectionId").asText();

        assertRejectedBy("chk_insp_auto_fail", "update inspection set fail_threshold_applied = null where id = ?", id);
        assertRejectedBy("chk_insp_auto_fail", "update inspection set calibrated_defect_probability = 0.5 where id = ?", id);
        assertRejectedBy("chk_insp_auto_fail", "update inspection set judged_by = 'WORKER' where id = ?", id);

        String policyId = register().path("policyId").asText();
        assertRejectedBy("chk_policy_auto_fail_configured",
                "update automation_policy set auto_fail_enabled = true where id = ?", policyId);
        assertRejectedBy("chk_policy_fail_above_pass", """
                update automation_policy set fail_threshold = 0.03, fail_validated_min = 0.01, fail_validated_max = 0.5
                where id = ?""", policyId);
        assertRejectedBy("chk_policy_fail_threshold_range", """
                update automation_policy set fail_threshold = 0.95, fail_validated_min = 0.7, fail_validated_max = 0.9
                where id = ?""", policyId);
    }
}
