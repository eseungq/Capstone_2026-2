package com.capstone.inspection.inspection;

import com.capstone.inspection.domain.inspection.PredictedQuality;
import com.capstone.inspection.domain.inspection.RecommendedAction;
import com.capstone.inspection.domain.inspection.ReviewReason;
import com.capstone.inspection.domain.model.AutomationPolicy;

import java.util.List;

// AUTO_PASS 판정 규칙 (계약 v4 4장). 아래를 모두 만족해야 AUTO_PASS, 하나라도 아니면 REVIEW
//   1. predictedQuality = GOOD               (아니면 DEFECT_PREDICTED, 단 아래 AUTO_FAIL 조건이면 AUTO_FAIL)
//   2. 모델 버전에 ready·active 정책 존재     (아니면 NO_ACTIVE_POLICY)
//   3. 보정 불량 확률이 null이 아님           (아니면 CALIBRATION_UNAVAILABLE)
//   4. 정책의 보정기 버전 = 응답 보정기 버전   (아니면 NO_ACTIVE_POLICY)
//   5. 보정 불량 확률 ≤ passThreshold         (아니면 ABOVE_THRESHOLD)
// 검사 순서가 곧 reviewReason 우선순위이므로 처음 걸린 사유 하나만 기록
// AUTO_FAIL 판정 규칙 (계약 4.1): DEFECT 예측 + 보정 확률 있음 + 위 2·4번과 같은 호환 정책
//   + 정책 autoFailEnabled + failThreshold 있음 + 보정 확률 ≥ failThreshold (반올림 전 값 비교)
//   조건을 못 맞춘 DEFECT는 지금처럼 REVIEW(DEFECT_PREDICTED)
// Grad-CAM 유무는 판정에 쓰지 않음
public final class PolicyEvaluator {

    private PolicyEvaluator() {
    }

    // policy: 판정에 사용한 호환 정책 (없으면 null)
    // passThreshold·failThreshold: 그 정책의 기준 스냅숏. failThreshold는 자동 불량이 켜져 있었을 때만 값
    public record Decision(RecommendedAction action, ReviewReason reviewReason,
                           AutomationPolicy policy, Double passThreshold, Double failThreshold) {

        static Decision of(RecommendedAction action, ReviewReason reason, AutomationPolicy policy) {
            return new Decision(action, reason, policy,
                    policy != null ? policy.getPassThreshold() : null, appliedFailThreshold(policy));
        }

        static Decision review(ReviewReason reason, AutomationPolicy policy) {
            return of(RecommendedAction.REVIEW, reason, policy);
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
            Double failThreshold = appliedFailThreshold(compatible);
            if (failThreshold != null && calibratedDefectProbability != null
                    && calibratedDefectProbability >= failThreshold) {
                return Decision.of(RecommendedAction.AUTO_FAIL, null, compatible);
            }
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
            return Decision.of(RecommendedAction.AUTO_PASS, null, compatible);
        }
        return Decision.review(ReviewReason.ABOVE_THRESHOLD, compatible);
    }

    // 자동 불량이 켜진 정책의 불량 기준. 꺼져 있거나 기준이 없으면 null
    private static Double appliedFailThreshold(AutomationPolicy policy) {
        return policy != null && policy.isAutoFailEnabled() ? policy.getFailThreshold() : null;
    }
}
