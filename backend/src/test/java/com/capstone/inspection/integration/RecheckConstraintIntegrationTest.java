package com.capstone.inspection.integration;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.test.context.TestPropertySource;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

// V10 표본 재확인 CHECK 보강 (김남균 점검 I18·I20·I21·I22)
//   MySQL CHECK는 결과가 NULL이면 통과하므로, 비교 대상이 NULL인 행도 DB가 거절하는지 직접 확인
//   각 UPDATE는 V9까지의 다른 CHECK는 모두 통과하는 값이라 V10 제약만으로 거절됨
@TestPropertySource(properties = {"app.recheck.enabled=true", "app.recheck.near-rate=1.0", "app.recheck.mid-rate=1.0", "app.recheck.low-rate=0"})
class RecheckConstraintIntegrationTest extends IntegrationTestBase {

    private String submitNear() throws Exception {
        ai = r -> response(r, "GOOD", 0.1, 0.045);
        return submitAndWaitForRecheckDecision().path("inspectionId").asText();
    }

    // MySQL CHECK 위반(3819)은 Spring에서 UncategorizedSQLException으로 올라오므로 메시지의 제약 이름으로 확인
    private void assertRejectedBy(String constraint, String sql, Object... args) {
        assertThatThrownBy(() -> jdbc.update(sql, args)).hasMessageContaining("Check constraint '" + constraint + "'");
    }

    private String ruleIdOf(String inspectionId) {
        return jdbc.queryForObject("select recheck_rule_id from inspection where id = ?", String.class, inspectionId);
    }

    @Test
    @DisplayName("재확인 규칙은 AUTO_PASS 판정 건에만. 판정 값이 없는 분석 실패 건에도 넣을 수 없음")
    void ruleOnlyOnAutoPass() throws Exception {
        String rule = ruleIdOf(submitNear());
        ai = aiServerError();
        String failed = submitAndWait().path("inspectionId").asText();
        assertThat(jdbc.queryForObject("select status from inspection where id = ?", String.class, failed))
                .isEqualTo("FAILED");

        assertRejectedBy("chk_insp_recheck_rule", "update inspection set recheck_rule_id = ? where id = ?", rule, failed);
    }

    @Test
    @DisplayName("관리자 확인함은 재확인 결과가 FAIL일 때만. 결과가 아직 없는 행에도 남길 수 없음")
    void acknowledgeOnlyOnFail() throws Exception {
        String pending = submitNear();
        String adminId = jdbc.queryForObject("select id from users where login_id = 'admin01'", String.class);

        assertRejectedBy("chk_recheck_ack", """
                update auto_pass_recheck set acknowledged_by = ?, acknowledged_at = sampled_at + interval 1 minute
                where inspection_id = ?""", adminId, pending);
    }

    @Test
    @DisplayName("규칙이 있는 결정 행은 뽑힘 = 추출 값 < 구간 비율")
    void sampledMatchesDraw() throws Exception {
        String near = submitNear();
        assertThat(jdbc.queryForObject("select sampled from auto_pass_recheck where inspection_id = ?", Boolean.class,
                near)).isTrue();

        assertRejectedBy("chk_recheck_draw", "update auto_pass_recheck set sampled = false where inspection_id = ?", near);
    }

    @Test
    @DisplayName("재확인 시각은 추출 결정 뒤, 확인함 시각은 재확인 뒤")
    void timestampsInOrder() throws Exception {
        String fail = submitNear();
        assertThat(postJson("/api/v1/inspections/" + fail + "/recheck", Map.of("result", "FAIL"), worker())
                .getResponse().getStatus()).isEqualTo(200);
        assertRejectedBy("chk_recheck_order", """
                update auto_pass_recheck set rechecked_at = sampled_at - interval 1 second
                where inspection_id = ?""", fail);

        assertThat(postJson("/api/v1/admin/rechecks/" + fail + "/acknowledge", Map.of("note", "확인"), admin())
                .getResponse().getStatus()).isEqualTo(200);
        assertRejectedBy("chk_recheck_order", """
                update auto_pass_recheck set acknowledged_at = rechecked_at - interval 1 second
                where inspection_id = ?""", fail);
    }
}
