package com.capstone.inspection.inspection;

import com.capstone.inspection.domain.inspection.PredictedQuality;
import com.capstone.inspection.domain.inspection.RecommendedAction;
import com.capstone.inspection.domain.inspection.ReviewReason;
import com.capstone.inspection.domain.model.AutomationPolicy;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.BeanUtils;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

// 계약 v4 4장 AUTO_PASS 규칙과 reviewReason 우선순위
class PolicyEvaluatorTest {

    private static AutomationPolicy policy(String calibratorVersion, Double passThreshold) {
        AutomationPolicy p = BeanUtils.instantiateClass(AutomationPolicy.class);
        ReflectionTestUtils.setField(p, "calibratorVersion", calibratorVersion);
        ReflectionTestUtils.setField(p, "passThreshold", passThreshold);
        ReflectionTestUtils.setField(p, "policyVersion", "example-door-p1");
        ReflectionTestUtils.setField(p, "ready", true);
        ReflectionTestUtils.setField(p, "active", true);
        return p;
    }

    private static final List<AutomationPolicy> ACTIVE = List.of(policy("cal-v1", 0.05));

    @Test
    @DisplayName("GOOD + 호환 정책 + 보정 확률 ≤ 기준 → AUTO_PASS, 기준치 스냅숏 기록")
    void autoPass() {
        var d = PolicyEvaluator.evaluate(PredictedQuality.GOOD, 0.02, "cal-v1", ACTIVE);
        assertThat(d.action()).isEqualTo(RecommendedAction.AUTO_PASS);
        assertThat(d.reviewReason()).isNull();
        assertThat(d.passThreshold()).isEqualTo(0.05);
        assertThat(d.policy()).isNotNull();
    }

    @Test
    @DisplayName("기준과 같은 값도 AUTO_PASS (≤)")
    void autoPassAtBoundary() {
        var d = PolicyEvaluator.evaluate(PredictedQuality.GOOD, 0.05, "cal-v1", ACTIVE);
        assertThat(d.action()).isEqualTo(RecommendedAction.AUTO_PASS);
    }

    @Test
    @DisplayName("DEFECT 예측은 보정 확률이 낮아도 REVIEW(DEFECT_PREDICTED). 자동 FAIL 없음")
    void defectAlwaysReview() {
        var d = PolicyEvaluator.evaluate(PredictedQuality.DEFECT, 0.01, "cal-v1", ACTIVE);
        assertThat(d.action()).isEqualTo(RecommendedAction.REVIEW);
        assertThat(d.reviewReason()).isEqualTo(ReviewReason.DEFECT_PREDICTED);
    }

    @Test
    @DisplayName("DEFECT + 정책 없음 → 우선순위가 높은 DEFECT_PREDICTED 하나만")
    void defectAndNoPolicy() {
        var d = PolicyEvaluator.evaluate(PredictedQuality.DEFECT, null, null, List.of());
        assertThat(d.reviewReason()).isEqualTo(ReviewReason.DEFECT_PREDICTED);
    }

    @Test
    @DisplayName("ready·active 정책 없음 → NO_ACTIVE_POLICY")
    void noPolicy() {
        var d = PolicyEvaluator.evaluate(PredictedQuality.GOOD, 0.01, "cal-v1", List.of());
        assertThat(d.reviewReason()).isEqualTo(ReviewReason.NO_ACTIVE_POLICY);
        assertThat(d.passThreshold()).isNull();
    }

    @Test
    @DisplayName("정책은 있지만 보정 확률 null → CALIBRATION_UNAVAILABLE")
    void calibrationUnavailable() {
        var d = PolicyEvaluator.evaluate(PredictedQuality.GOOD, null, null, ACTIVE);
        assertThat(d.reviewReason()).isEqualTo(ReviewReason.CALIBRATION_UNAVAILABLE);
    }

    @Test
    @DisplayName("보정기 버전이 정책과 다르면 → NO_ACTIVE_POLICY")
    void calibratorMismatch() {
        var d = PolicyEvaluator.evaluate(PredictedQuality.GOOD, 0.01, "cal-v2", ACTIVE);
        assertThat(d.reviewReason()).isEqualTo(ReviewReason.NO_ACTIVE_POLICY);
    }

    @Test
    @DisplayName("보정 확률 > 기준 → ABOVE_THRESHOLD, 기준치 스냅숏은 기록")
    void aboveThreshold() {
        var d = PolicyEvaluator.evaluate(PredictedQuality.GOOD, 0.2, "cal-v1", ACTIVE);
        assertThat(d.reviewReason()).isEqualTo(ReviewReason.ABOVE_THRESHOLD);
        assertThat(d.passThreshold()).isEqualTo(0.05);
    }
}
