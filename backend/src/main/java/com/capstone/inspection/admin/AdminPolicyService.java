package com.capstone.inspection.admin;

import com.capstone.inspection.admin.dto.ModelResponse;
import com.capstone.inspection.admin.dto.PolicyCreateRequest;
import com.capstone.inspection.admin.dto.PolicyResponse;
import com.capstone.inspection.ai.ModelAvailability;
import com.capstone.inspection.ai.ModelAvailabilityService;
import com.capstone.inspection.common.error.BusinessException;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.common.time.Times;
import com.capstone.inspection.config.AppProperties;
import com.capstone.inspection.domain.model.AiModel;
import com.capstone.inspection.domain.model.AiModelRepository;
import com.capstone.inspection.domain.model.AutomationPolicy;
import com.capstone.inspection.domain.model.AutomationPolicyRepository;
import com.capstone.inspection.domain.part.PartRepository;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;

// 관리자 모델·정책 관리 (계약 v4 6.9). 정책은 수정하지 않고 새 버전을 만듦. 모델 등록·활성화는 제공하지 않음
@Service
@RequiredArgsConstructor
public class AdminPolicyService {

    private final AiModelRepository modelRepository;
    private final AutomationPolicyRepository policyRepository;
    private final PartRepository partRepository;
    private final ModelAvailabilityService modelAvailability;
    private final AppProperties props;
    private final ObjectMapper objectMapper;

    @Transactional(readOnly = true)
    public List<ModelResponse> models() {
        return modelRepository.findAllWithPart().stream()
                .map(m -> new ModelResponse(m.getModelVersion(), m.getItem().getPart().getPartCode(),
                        m.getCalibratorVersion(), m.isActive(), loadable(m.getModelVersion())))
                .toList();
    }

    @Transactional(readOnly = true)
    public List<PolicyResponse> policies(String partCode, Boolean active) {
        String code = partCode == null || partCode.isBlank() ? null : partCode.trim();
        if (code != null && partRepository.findByPartCode(code).isEmpty()) {
            throw new BusinessException(ErrorCode.INVALID_PART_CODE);
        }
        return policyRepository.search(code, active).stream().map(this::toResponse).toList();
    }

    // AI 검증 자료 등록. 항상 active=false로 시작
    @Transactional
    public PolicyResponse create(PolicyCreateRequest request) {
        double threshold = PolicyRules.round6(unitValue(request.passThreshold()));
        double min = PolicyRules.round6(unitValue(request.validatedMin()));
        double max = PolicyRules.round6(unitValue(request.validatedMax()));
        if (min > max) {
            throw new BusinessException(ErrorCode.INVALID_PARAMETER, "validatedMin은 validatedMax보다 클 수 없습니다.");
        }
        requireInRange(threshold, min, max);
        JsonNode metrics = request.metrics() == null || request.metrics().isNull() ? null : request.metrics();
        if (metrics != null && !metrics.isObject()) {
            throw new BusinessException(ErrorCode.INVALID_PARAMETER, "metrics는 객체여야 합니다.");
        }
        AiModel model = modelRepository.findByModelVersion(request.modelVersion().trim())
                .orElseThrow(() -> new BusinessException(ErrorCode.MODEL_NOT_FOUND));
        String calibrator = request.calibratorVersion() == null || request.calibratorVersion().isBlank()
                ? null : request.calibratorVersion().trim();
        String version = request.policyVersion().trim();
        if (policyRepository.existsByPolicyVersion(version)) {
            throw new BusinessException(ErrorCode.POLICY_VERSION_DUPLICATE);
        }
        boolean ready = PolicyRules.isReady(calibrator, model.getCalibratorVersion(), metrics,
                props.policy().minSampleCount());
        return save(new AutomationPolicy(model, calibrator, version, threshold, min, max, metricsJson(metrics), ready,
                null));
    }

    // 기준치 조정: 기존 행은 그대로 두고 새 버전을 만듦. active=false, ready는 승계
    @Transactional
    public PolicyResponse adjustThreshold(String policyId, double passThreshold) {
        AutomationPolicy base = find(policyId);
        double threshold = PolicyRules.round6(passThreshold);
        if (base.getValidatedMin() == null || base.getValidatedMax() == null) {
            throw new BusinessException(ErrorCode.POLICY_THRESHOLD_OUT_OF_RANGE, "검증 범위가 없는 정책은 조정할 수 없습니다.");
        }
        requireInRange(threshold, base.getValidatedMin(), base.getValidatedMax());
        String root = rootVersion(base);
        String version = PolicyRules.nextVersion(root, policyRepository.findVersionsStartingWith(root + "-t"));
        return save(new AutomationPolicy(base.getModel(), base.getCalibratorVersion(), version, threshold,
                base.getValidatedMin(), base.getValidatedMax(), base.getMetricsJson(), base.isReady(), base.getId()));
    }

    // 적용 시작. 모델 행을 잠가 같은 모델의 동시 적용을 줄 세움 (uq_policy_active_model)
    // MySQL은 유일 제약을 문장마다 검사하므로 다른 정책 중지를 먼저 반영한 뒤 대상을 켬
    @Transactional
    public PolicyResponse activate(String policyId) {
        AutomationPolicy policy = find(policyId);
        AiModel model = modelRepository.findByIdForUpdate(policy.getModel().getId()).orElseThrow();
        boolean calibratorMatches = model.getCalibratorVersion() != null
                && model.getCalibratorVersion().equals(policy.getCalibratorVersion());
        if (!policy.isReady() || !model.isActive() || !calibratorMatches) {
            throw new BusinessException(ErrorCode.POLICY_NOT_READY);
        }
        if (policy.isActive()) {
            return toResponse(policy);
        }
        policyRepository.deactivateOthers(model.getId(), policy.getId());
        policy.activate(LocalDateTime.now());
        try {
            policyRepository.saveAndFlush(policy);
        } catch (DataIntegrityViolationException e) {
            throw new BusinessException(ErrorCode.POLICY_NOT_READY, "동시에 다른 정책이 적용되었습니다. 다시 시도하세요.");
        }
        return toResponse(policy);
    }

    @Transactional
    public PolicyResponse deactivate(String policyId) {
        AutomationPolicy policy = find(policyId);
        policy.deactivate();
        return toResponse(policy);
    }

    private AutomationPolicy find(String policyId) {
        return policyRepository.findById(policyId)
                .orElseThrow(() -> new BusinessException(ErrorCode.POLICY_NOT_FOUND));
    }

    // based_on 연결을 끝까지 따라가 원본 이름을 찾음
    private String rootVersion(AutomationPolicy policy) {
        AutomationPolicy current = policy;
        while (current.getBasedOnPolicyId() != null) {
            current = policyRepository.findById(current.getBasedOnPolicyId()).orElseThrow();
        }
        return current.getPolicyVersion();
    }

    private PolicyResponse save(AutomationPolicy policy) {
        try {
            policyRepository.saveAndFlush(policy);
        } catch (DataIntegrityViolationException e) {
            // 동시 등록·조정으로 이름이 겹침: 먼저 커밋된 쪽만 남음
            throw new BusinessException(ErrorCode.POLICY_VERSION_DUPLICATE);
        }
        return toResponse(policy);
    }

    private Boolean loadable(String modelVersion) {
        if (!modelAvailability.isEnabled()) {
            return null;
        }
        ModelAvailability availability = modelAvailability.check(modelVersion);
        return availability == ModelAvailability.UNKNOWN ? null : availability == ModelAvailability.AVAILABLE;
    }

    private static double unitValue(double value) {
        if (value < 0 || value > 1) {
            throw new BusinessException(ErrorCode.INVALID_PARAMETER, "기준치와 검증 범위는 0~1이어야 합니다.");
        }
        return value;
    }

    private static void requireInRange(double threshold, double min, double max) {
        if (threshold < min || threshold > max) {
            throw new BusinessException(ErrorCode.POLICY_THRESHOLD_OUT_OF_RANGE);
        }
    }

    private String metricsJson(JsonNode metrics) {
        try {
            return metrics == null ? "{}" : objectMapper.writeValueAsString(metrics);
        } catch (JsonProcessingException e) {
            throw new BusinessException(ErrorCode.INVALID_PARAMETER, "metrics를 저장할 수 없습니다.");
        }
    }

    private PolicyResponse toResponse(AutomationPolicy p) {
        JsonNode metrics;
        try {
            metrics = objectMapper.readTree(p.getMetricsJson());
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("정책 metrics 형식 오류 " + p.getId(), e);
        }
        return new PolicyResponse(p.getId(), p.getPolicyVersion(), p.getItem().getPart().getPartCode(),
                p.getModel().getModelVersion(), p.getCalibratorVersion(), p.getPassThreshold(), p.getValidatedMin(),
                p.getValidatedMax(), p.isReady(), p.isActive(), metrics, p.getBasedOnPolicyId(),
                Times.toOffset(p.getCreatedAt()), Times.toOffset(p.getActivatedAt()));
    }
}
