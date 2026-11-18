package com.capstone.inspection.integration;

import com.capstone.inspection.inspection.RecheckSweeper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

// 계약 6.11 기본값: 표본 재확인은 꺼 둠 (설정을 고정한 뒤 켜도록). 기본 설정 그대로 실행
class RecheckDisabledIntegrationTest extends IntegrationTestBase {

    @Autowired
    private RecheckSweeper sweeper;

    @Test
    @DisplayName("기본 설정에서는 AUTO_PASS여도 추출 결정을 남기지 않고, 재처리도 하지 않음")
    void disabledByDefault() throws Exception {
        ai = r -> response(r, "GOOD", 0.1, 0.045); // 켜져 있으면 NEAR(비율 1.0)로 뽑히는 값
        String id = submitAndWait().path("inspectionId").asText();

        assertThat(json(call(get("/api/v1/inspections/" + id), worker())).at("/data/displayState").asText())
                .isEqualTo("AUTO_PASS");
        assertThat(json(call(get("/api/v1/inspections/" + id), worker())).at("/data/recheck").isNull()).isTrue();
        assertThat(jdbc.queryForObject("select count(*) from auto_pass_recheck where inspection_id = ?",
                Long.class, id)).isZero();
        jdbc.update("update inspection set completed_at = completed_at - interval 5 minute where id = ?", id);
        assertThat(sweeper.sweep()).isZero();
    }
}
