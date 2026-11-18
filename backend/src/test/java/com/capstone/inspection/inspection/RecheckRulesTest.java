package com.capstone.inspection.inspection;

import com.capstone.inspection.config.AppProperties;
import com.capstone.inspection.domain.inspection.RecheckStratum;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.within;

class RecheckRulesTest {

    private static final AppProperties.Recheck CONFIG = new AppProperties.Recheck(true, 0.8, 0.4, 1.0, 0.3, 0.1);

    @Test
    @DisplayName("구간: 보정 확률 ÷ 기준치 0.8 이상 NEAR, 0.4 이상 MID, 나머지 LOW (경계 포함)")
    void stratum() {
        assertThat(RecheckRules.stratum(0.05, 0.05, CONFIG)).isEqualTo(RecheckStratum.NEAR);
        assertThat(RecheckRules.stratum(0.04, 0.05, CONFIG)).isEqualTo(RecheckStratum.NEAR);
        assertThat(RecheckRules.stratum(0.039, 0.05, CONFIG)).isEqualTo(RecheckStratum.MID);
        assertThat(RecheckRules.stratum(0.02, 0.05, CONFIG)).isEqualTo(RecheckStratum.MID);
        assertThat(RecheckRules.stratum(0.019, 0.05, CONFIG)).isEqualTo(RecheckStratum.LOW);
        assertThat(RecheckRules.stratum(0.0, 0.0, CONFIG)).isEqualTo(RecheckStratum.NEAR);
    }

    @Test
    @DisplayName("비율 1이면 항상, 0이면 절대 뽑지 않음. 같은 검사는 항상 같은 결과")
    void rateBounds() {
        String id = UUID.randomUUID().toString();
        assertThat(RecheckRules.decide(id, 0.045, 0.05, CONFIG).sampled()).isTrue();
        AppProperties.Recheck none = new AppProperties.Recheck(true, 0.8, 0.4, 0, 0, 0);
        assertThat(RecheckRules.decide(id, 0.045, 0.05, none).sampled()).isFalse();
        assertThat(RecheckRules.draw(id)).isEqualTo(RecheckRules.draw(id)).isBetween(0.0, 1.0);
    }

    @Test
    @DisplayName("잘못된 설정은 생성 시 실패: 비율 1 초과·음수·0 근처, 구간 순서 뒤바뀜")
    void invalidConfig() {
        assertThatThrownBy(() -> new AppProperties.Recheck(true, 0.8, 0.4, 1.5, 0.3, 0.1))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new AppProperties.Recheck(true, 0.8, 0.4, 1.0, -0.1, 0.1))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new AppProperties.Recheck(true, 0.8, 0.4, 1.0, 0.3, 1e-7))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new AppProperties.Recheck(true, 0.4, 0.8, 1.0, 0.3, 0.1))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    @DisplayName("검사 ID로 뽑은 비율이 설정 비율에 가까움 (MID 0.3)")
    void rateApproximatelyHonored() {
        int n = 4000;
        int sampled = 0;
        for (int k = 0; k < n; k++) {
            RecheckRules.Decision d = RecheckRules.decide(UUID.randomUUID().toString(), 0.03, 0.05, CONFIG);
            assertThat(d.stratum()).isEqualTo(RecheckStratum.MID);
            assertThat(d.rate()).isEqualTo(0.3);
            sampled += d.sampled() ? 1 : 0;
        }
        assertThat(sampled / (double) n).isCloseTo(0.3, within(0.04));
    }
}
