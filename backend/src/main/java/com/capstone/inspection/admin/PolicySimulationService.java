package com.capstone.inspection.admin;

import com.capstone.inspection.admin.dto.PolicySimulationResponse;
import com.capstone.inspection.common.error.BusinessException;
import com.capstone.inspection.config.AppProperties;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.domain.inspection.InspectionRepository;
import com.capstone.inspection.domain.inspection.RecheckRule;
import com.capstone.inspection.domain.model.AutomationPolicy;
import com.capstone.inspection.domain.model.AutomationPolicyRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;

// 정책 후보 비교 (계약 6.9.1). 기준치를 바꾸기 전에 같은 검사 기록으로 바뀌는 건과 작업자 판정을 확인하는 용도
@Service
@RequiredArgsConstructor
public class PolicySimulationService {

    private final AutomationPolicyRepository policyRepository;
    private final InspectionRepository inspectionRepository;
    private final AppProperties props;

    @Transactional(readOnly = true)
    public PolicySimulationResponse simulate(String policyId, double candidateThreshold, LocalDateTime from,
                                             LocalDateTime to) {
        if (!Double.isFinite(candidateThreshold) || candidateThreshold < 0 || candidateThreshold > 1) {
            throw new BusinessException(ErrorCode.INVALID_PARAMETER, "candidateThreshold는 0~1 사이여야 합니다.");
        }
        if (from != null && to != null && from.isAfter(to)) {
            throw new BusinessException(ErrorCode.INVALID_PARAMETER, "from은 to보다 늦을 수 없습니다.");
        }
        AutomationPolicy policy = policyRepository.findById(policyId)
                .orElseThrow(() -> new BusinessException(ErrorCode.POLICY_NOT_FOUND));
        if (policy.getPassThreshold() == null || policy.getCalibratorVersion() == null) {
            throw new BusinessException(ErrorCode.INVALID_PARAMETER,
                    "기준치나 보정기 버전이 없는 정책은 비교할 수 없습니다.");
        }
        double candidate = PolicyRules.round6(candidateThreshold);
        // 꺼져 있어도 켰을 때 기준으로 예상 재확인 건수를 냄. 설정 자체가 없으면 예상 0
        RecheckRule recheckRule = props.recheck() != null ? props.recheck().rule() : RecheckRule.NONE;
        PolicySimulation.Result result = PolicySimulation.run(
                inspectionRepository.findScored(policy.getModel().getId(), policy.getCalibratorVersion(), from, to),
                policy.getPassThreshold(), candidate, recheckRule);
        boolean withinRange = policy.getValidatedMin() != null && policy.getValidatedMax() != null
                && candidate >= policy.getValidatedMin() && candidate <= policy.getValidatedMax();
        return new PolicySimulationResponse(policy.getId(), policy.getPolicyVersion(),
                policy.getItem().getPart().getPartCode(), policy.getModel().getModelVersion(),
                policy.getCalibratorVersion(), policy.getPassThreshold(), candidate, policy.getValidatedMin(),
                policy.getValidatedMax(), withinRange, recheckRule.version(), result.evaluatedCount(),
                result.defectPredictedCount(),
                result.current(), result.candidate(), result.change());
    }
}
