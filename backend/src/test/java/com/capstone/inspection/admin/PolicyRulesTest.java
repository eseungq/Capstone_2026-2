package com.capstone.inspection.admin;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

// 계약 v4 6.9 ready 판정(TBD-03 임시)과 조정 버전 이름
class PolicyRulesTest {

    private static JsonNode metrics(String json) throws Exception {
        return new ObjectMapper().readTree(json);
    }

    @Test
    @DisplayName("보정기가 모델과 일치하고 표본 수가 기준 이상이면 ready")
    void ready() throws Exception {
        assertThat(PolicyRules.isReady("cal", "cal", metrics("{\"sampleCount\":10}"), 10)).isTrue();
    }

    @Test
    @DisplayName("모델 보정기가 null이면 어떤 값을 보내도 ready 아님")
    void modelWithoutCalibrator() throws Exception {
        assertThat(PolicyRules.isReady("cal", null, metrics("{\"sampleCount\":10}"), 0)).isFalse();
        assertThat(PolicyRules.isReady(null, null, metrics("{\"sampleCount\":10}"), 0)).isFalse();
    }

    @Test
    @DisplayName("보정기 불일치, 표본 부족, 표본 수 없음은 ready 아님")
    void notReady() throws Exception {
        assertThat(PolicyRules.isReady("other", "cal", metrics("{\"sampleCount\":10}"), 0)).isFalse();
        assertThat(PolicyRules.isReady("cal", "cal", metrics("{\"sampleCount\":9}"), 10)).isFalse();
        assertThat(PolicyRules.isReady("cal", "cal", metrics("{}"), 0)).isFalse();
        assertThat(PolicyRules.isReady("cal", "cal", metrics("{\"sampleCount\":\"10\"}"), 0)).isFalse();
        assertThat(PolicyRules.isReady("cal", "cal", null, 0)).isFalse();
    }

    @Test
    @DisplayName("조정 버전은 원본 이름 기준으로 번호가 늘어남")
    void nextVersion() {
        assertThat(PolicyRules.nextVersion("example-door-p1", List.of())).isEqualTo("example-door-p1-t1");
        assertThat(PolicyRules.nextVersion("example-door-p1", List.of("example-door-p1-t1", "example-door-p1-t3",
                "example-door-p1-trial", "example-door-p1-t2-x"))).isEqualTo("example-door-p1-t4");
    }
}
