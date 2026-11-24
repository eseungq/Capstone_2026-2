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

    // 도어 e02 캡스톤 시연 기준 30% (ai/VALIDATION.md, 11/07 선정). GOOD + 보정 확률 ≤ 0.30만 AUTO_PASS
    private static final List<AutomationPolicy> DEMO_30 = List.of(policy("cal-v1", 0.30));

    @Test
    @DisplayName("시연 30%: GOOD + 0.21 → AUTO_PASS")
    void demoAutoPass() {
        var d = PolicyEvaluator.evaluate(PredictedQuality.GOOD, 0.21, "cal-v1", DEMO_30);
        assertThat(d.action()).isEqualTo(RecommendedAction.AUTO_PASS);
        assertThat(d.passThreshold()).isEqualTo(0.30);
    }

    @Test
    @DisplayName("시연 30%: GOOD + 0.30 경계 → AUTO_PASS (≤)")
    void demoAutoPassAtBoundary() {
        var d = PolicyEvaluator.evaluate(PredictedQuality.GOOD, 0.30, "cal-v1", DEMO_30);
        assertThat(d.action()).isEqualTo(RecommendedAction.AUTO_PASS);
    }

    @Test
    @DisplayName("시연 30%: GOOD + 0.35 → REVIEW(ABOVE_THRESHOLD)")
    void demoAboveThreshold() {
        var d = PolicyEvaluator.evaluate(PredictedQuality.GOOD, 0.35, "cal-v1", DEMO_30);
        assertThat(d.reviewReason()).isEqualTo(ReviewReason.ABOVE_THRESHOLD);
        assertThat(d.passThreshold()).isEqualTo(0.30);
    }

    @Test
    @DisplayName("시연 30%: DEFECT는 보정 확률이 낮아도 REVIEW(DEFECT_PREDICTED)")
    void demoDefectReview() {
        var d = PolicyEvaluator.evaluate(PredictedQuality.DEFECT, 0.10, "cal-v1", DEMO_30);
        assertThat(d.reviewReason()).isEqualTo(ReviewReason.DEFECT_PREDICTED);
    }

    @Test
    @DisplayName("관리자 조정 시연: 보정 0.32는 30%에서 REVIEW, 35%로 조정한 정책에서는 AUTO_PASS")
    void demoAdjustTo35() {
        var before = PolicyEvaluator.evaluate(PredictedQuality.GOOD, 0.32, "cal-v1", DEMO_30);
        assertThat(before.reviewReason()).isEqualTo(ReviewReason.ABOVE_THRESHOLD);

        var after = PolicyEvaluator.evaluate(PredictedQuality.GOOD, 0.32, "cal-v1", List.of(policy("cal-v1", 0.35)));
        assertThat(after.action()).isEqualTo(RecommendedAction.AUTO_PASS);
        assertThat(after.passThreshold()).isEqualTo(0.35);
    }

    // 11/12 도어 시연 값 (AI 내부 평가, V6_2 example-door-demo-0092 기본 0.92%·조정 하한 0.84%). 소수 넷째 자리 비교에서 경계 포함
    @Test
    @DisplayName("관리자 조정 시연 11/12: 보정 0.0088은 0.84%에서 REVIEW, 0.92%에서 AUTO_PASS, 0.92% 경계 포함")
    void demoAdjust0084To0092() {
        var before = PolicyEvaluator.evaluate(PredictedQuality.GOOD, 0.0088, "cal-v1", List.of(policy("cal-v1", 0.0084)));
        assertThat(before.reviewReason()).isEqualTo(ReviewReason.ABOVE_THRESHOLD);
        assertThat(before.passThreshold()).isEqualTo(0.0084);

        var adjusted = List.of(policy("cal-v1", 0.0092));
        var after = PolicyEvaluator.evaluate(PredictedQuality.GOOD, 0.0088, "cal-v1", adjusted);
        assertThat(after.action()).isEqualTo(RecommendedAction.AUTO_PASS);
        assertThat(after.passThreshold()).isEqualTo(0.0092);
        assertThat(PolicyEvaluator.evaluate(PredictedQuality.GOOD, 0.0092, "cal-v1", adjusted).action())
                .isEqualTo(RecommendedAction.AUTO_PASS);
        assertThat(PolicyEvaluator.evaluate(PredictedQuality.GOOD, 0.0093, "cal-v1", adjusted).reviewReason())
                .isEqualTo(ReviewReason.ABOVE_THRESHOLD);
    }

    @Test
    @DisplayName("시연 30%여도 실서버처럼 보정 확률·보정기가 null이면 REVIEW(CALIBRATION_UNAVAILABLE)")
    void demoUncalibratedReview() {
        var d = PolicyEvaluator.evaluate(PredictedQuality.GOOD, null, null, DEMO_30);
        assertThat(d.action()).isEqualTo(RecommendedAction.REVIEW);
        assertThat(d.reviewReason()).isEqualTo(ReviewReason.CALIBRATION_UNAVAILABLE);
    }

    // ---- 자동 불량 AUTO_FAIL (계약 4.1) ----

    // 자동 통과 0.05 + 자동 불량 기준 0.8
    private static AutomationPolicy autoFailPolicy(boolean enabled, Double failThreshold) {
        AutomationPolicy p = policy("cal-v1", 0.05);
        ReflectionTestUtils.setField(p, "autoFailEnabled", enabled);
        ReflectionTestUtils.setField(p, "failThreshold", failThreshold);
        return p;
    }

    private static final List<AutomationPolicy> AUTO_FAIL_ON = List.of(autoFailPolicy(true, 0.8));

    @Test
    @DisplayName("DEFECT + 자동 불량 켜짐 + 보정 확률 ≥ 기준 → AUTO_FAIL, 사유 없음, 두 기준 스냅숏")
    void autoFailAboveThreshold() {
        var d = PolicyEvaluator.evaluate(PredictedQuality.DEFECT, 0.93, "cal-v1", AUTO_FAIL_ON);
        assertThat(d.action()).isEqualTo(RecommendedAction.AUTO_FAIL);
        assertThat(d.reviewReason()).isNull();
        assertThat(d.policy()).isNotNull();
        assertThat(d.passThreshold()).isEqualTo(0.05);
        assertThat(d.failThreshold()).isEqualTo(0.8);
    }

    @Test
    @DisplayName("기준과 같은 값도 AUTO_FAIL (≥, 반올림 전 값 비교)")
    void autoFailAtBoundary() {
        assertThat(PolicyEvaluator.evaluate(PredictedQuality.DEFECT, 0.8, "cal-v1", AUTO_FAIL_ON).action())
                .isEqualTo(RecommendedAction.AUTO_FAIL);
        assertThat(PolicyEvaluator.evaluate(PredictedQuality.DEFECT, 0.7999999, "cal-v1", AUTO_FAIL_ON).reviewReason())
                .isEqualTo(ReviewReason.DEFECT_PREDICTED);
    }

    @Test
    @DisplayName("DEFECT + 자동 불량 켜짐 + 보정 확률 < 기준 → REVIEW(DEFECT_PREDICTED), 불량 기준 스냅숏은 기록")
    void autoFailBelowThreshold() {
        var d = PolicyEvaluator.evaluate(PredictedQuality.DEFECT, 0.6, "cal-v1", AUTO_FAIL_ON);
        assertThat(d.action()).isEqualTo(RecommendedAction.REVIEW);
        assertThat(d.reviewReason()).isEqualTo(ReviewReason.DEFECT_PREDICTED);
        assertThat(d.failThreshold()).isEqualTo(0.8);
    }

    @Test
    @DisplayName("자동 불량 꺼짐이면 기준이 있어도 REVIEW, 불량 기준 스냅숏 null")
    void autoFailDisabled() {
        var d = PolicyEvaluator.evaluate(PredictedQuality.DEFECT, 0.99, "cal-v1", List.of(autoFailPolicy(false, 0.8)));
        assertThat(d.reviewReason()).isEqualTo(ReviewReason.DEFECT_PREDICTED);
        assertThat(d.failThreshold()).isNull();
    }

    @Test
    @DisplayName("불량 기준이 없으면 켜짐 표시여도 REVIEW")
    void autoFailWithoutThreshold() {
        var d = PolicyEvaluator.evaluate(PredictedQuality.DEFECT, 0.99, "cal-v1", List.of(autoFailPolicy(true, null)));
        assertThat(d.reviewReason()).isEqualTo(ReviewReason.DEFECT_PREDICTED);
        assertThat(d.failThreshold()).isNull();
    }

    @Test
    @DisplayName("보정 확률 null이면 자동 불량 정책이어도 REVIEW(DEFECT_PREDICTED)")
    void autoFailCalibrationNull() {
        var d = PolicyEvaluator.evaluate(PredictedQuality.DEFECT, null, null, AUTO_FAIL_ON);
        assertThat(d.reviewReason()).isEqualTo(ReviewReason.DEFECT_PREDICTED);
        assertThat(d.policy()).isNull();
        assertThat(d.failThreshold()).isNull();
    }

    @Test
    @DisplayName("ready·active 정책이 없거나 보정기가 다르면 자동 불량 없음")
    void autoFailNoCompatiblePolicy() {
        assertThat(PolicyEvaluator.evaluate(PredictedQuality.DEFECT, 0.99, "cal-v1", List.of()).reviewReason())
                .isEqualTo(ReviewReason.DEFECT_PREDICTED);
        var mismatch = PolicyEvaluator.evaluate(PredictedQuality.DEFECT, 0.99, "cal-v2", AUTO_FAIL_ON);
        assertThat(mismatch.action()).isEqualTo(RecommendedAction.REVIEW);
        assertThat(mismatch.failThreshold()).isNull();
    }

    @Test
    @DisplayName("자동 불량 정책에서 GOOD 예측은 AUTO_PASS 규칙 그대로, 불량 기준 스냅숏만 함께 기록")
    void autoFailPolicyGoodUnchanged() {
        var pass = PolicyEvaluator.evaluate(PredictedQuality.GOOD, 0.02, "cal-v1", AUTO_FAIL_ON);
        assertThat(pass.action()).isEqualTo(RecommendedAction.AUTO_PASS);
        assertThat(pass.failThreshold()).isEqualTo(0.8);
        // GOOD은 보정 확률이 불량 기준 이상이어도 자동 불량이 아님
        var high = PolicyEvaluator.evaluate(PredictedQuality.GOOD, 0.9, "cal-v1", AUTO_FAIL_ON);
        assertThat(high.reviewReason()).isEqualTo(ReviewReason.ABOVE_THRESHOLD);
    }
}
