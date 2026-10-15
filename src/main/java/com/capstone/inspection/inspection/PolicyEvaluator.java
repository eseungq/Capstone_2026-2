package com.capstone.inspection.inspection;

import com.capstone.inspection.domain.inspection.PredictedQuality;
import com.capstone.inspection.domain.inspection.RecommendedAction;
import com.capstone.inspection.domain.inspection.ReviewReason;
import com.capstone.inspection.domain.model.AutomationPolicy;

import java.util.List;

// AUTO_PASS 판정 규칙 (계약 v4 4장). 아래를 모두 만족해야 AUTO_PASS, 하나라도 아니면 REVIEW
//   1. predictedQuality = GOOD               (아니면 DEFECT_PREDICTED)
//   2. 모델 버전에 ready·active 정책 존재     (아니면 NO_ACTIVE_POLICY)
//   3. 보정 불량 확률이 null이 아님           (아니면 CALIBRATION_UNAVAILABLE)
//   4. 정책의 보정기 버전 = 응답 보정기 버전   (아니면 NO_ACTIVE_POLICY)
//   5. 보정 불량 확률 ≤ passThreshold         (아니면 ABOVE_THRESHOLD)
// 검사 순서가 곧 reviewReason 우선순위이므로 처음 걸린 사유 하나만 기록. 자동 FAIL은 없음
// Grad-CAM 유무는 판정에 쓰지 않음
public final class PolicyEvaluator {

    private PolicyEvaluator() {
    }

    // policy: 판정에 사용한 호환 정책 (없으면 null), passThreshold: 그 정책의 기준치 스냅숏
    public record Decision(RecommendedAction action, ReviewReason reviewReason,
                           AutomationPolicy policy, Double passThreshold) {

        static Decision review(ReviewReason reason, AutomationPolicy policy) {
            return new Decision(RecommendedAction.REVIEW, reason, policy,
                    policy != null ? policy.getPassThreshold() : null);
        }
    }

    public static Decision evaluate(PredictedQuality quality, Double calibratedDefectProbability,
                                    String calibratorVersion, List<AutomationPolicy> readyActivePolicies) {
        // 보정기 버전까지 맞는 정책 (같은 모델에 여러 개면 첫 번째. 활성 정책은 조합당 1개가 원칙)
        AutomationPolicy compatible = readyActivePolicies.stream()
                .filter(p -> p.getPassThreshold() != null && p.isCompatibleWith(calibratorVersion))
                .findFirst()
                .orElse(null);

        if (quality == PredictedQuality.DEFECT) {
            return Decision.review(ReviewReason.DEFECT_PREDICTED, compatible);
        }
        if (readyActivePolicies.isEmpty()) {
            return Decision.review(ReviewReason.NO_ACTIVE_POLICY, null);
        }
        if (calibratedDefectProbability == null) {
            return Decision.review(ReviewReason.CALIBRATION_UNAVAILABLE, null);
        }
        if (compatible == null) {
            return Decision.review(ReviewReason.NO_ACTIVE_POLICY, null);
        }
        if (calibratedDefectProbability <= compatible.getPassThreshold()) {
            return new Decision(RecommendedAction.AUTO_PASS, null, compatible, compatible.getPassThreshold());
        }
        return Decision.review(ReviewReason.ABOVE_THRESHOLD, compatible);
    }
}
