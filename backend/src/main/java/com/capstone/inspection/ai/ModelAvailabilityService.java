package com.capstone.inspection.ai;

import com.capstone.inspection.common.error.BusinessException;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.config.AppProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

// 모델 로드 확인 (계약 v4 6.1, 6.2). 접수·재검사·부품 목록·모니터링이 모두 이 판단을 사용
// AI 조회 결과는 짧게 캐시해서 접수·폴링마다 AI 서버를 호출하지 않음
// 부품별 AI 서버가 여럿이면(app.ai.part-base-urls) 서버마다 따로 조회·캐시하고 결과를 합쳐 판단
@Service
public class ModelAvailabilityService {

    private static final Logger log = LoggerFactory.getLogger(ModelAvailabilityService.class);

    private final AiModelListClient client;
    private final List<String> baseUrls;
    private final boolean enabled;
    private final long successTtlNanos;
    private final long failureTtlNanos;

    private final Map<String, Snapshot> snapshots = new ConcurrentHashMap<>(); // AI 주소별

    // models가 null이면 확인 실패 (UNKNOWN)
    private record Snapshot(Map<String, Boolean> models, long expiresAtNanos) {
        boolean isFresh() {
            return System.nanoTime() - expiresAtNanos < 0;
        }
    }

    public ModelAvailabilityService(AppProperties props, AiModelListClient client) {
        this.client = client;
        this.baseUrls = props.ai().allBaseUrls();
        this.enabled = props.ai().modelCheckEnabled();
        this.successTtlNanos = props.ai().modelCheckTtlSeconds() * 1_000_000_000L;
        this.failureTtlNanos = props.ai().modelCheckFailureTtlSeconds() * 1_000_000_000L;
    }

    public boolean isEnabled() {
        return enabled;
    }

    // 확인을 끈 경우 활성 모델이 있다는 것만으로 판단 (실제 AI에 이 엔드포인트가 없을 때)
    public ModelAvailability check(String modelVersion) {
        if (!enabled) {
            return ModelAvailability.AVAILABLE;
        }
        // 어느 서버 목록에든 있으면 그 값으로 판단. 없는데 조회 실패한 서버가 있으면 확인 불가
        boolean anyUnknown = false;
        for (String baseUrl : baseUrls) {
            Map<String, Boolean> models = currentModels(baseUrl);
            if (models == null) {
                anyUnknown = true;
            } else if (models.containsKey(modelVersion)) {
                return Boolean.TRUE.equals(models.get(modelVersion))
                        ? ModelAvailability.AVAILABLE : ModelAvailability.NOT_LOADABLE;
            }
        }
        return anyUnknown ? ModelAvailability.UNKNOWN : ModelAvailability.NOT_LOADABLE;
    }

    // 접수·재검사용: NOT_LOADABLE만 거절. UNKNOWN은 받아서 분석 단계에서 판단 (AI 오류면 FAILED)
    public void requireNotRejected(String modelVersion) {
        ModelAvailability availability = check(modelVersion);
        if (availability == ModelAvailability.NOT_LOADABLE) {
            throw new BusinessException(ErrorCode.MODEL_NOT_AVAILABLE);
        }
        if (availability == ModelAvailability.UNKNOWN) {
            log.warn("모델 로드 확인 불가, 접수는 진행: {}", modelVersion);
        }
    }

    private Map<String, Boolean> currentModels(String baseUrl) {
        Snapshot current = snapshots.get(baseUrl);
        if (current != null && current.isFresh()) {
            return current.models();
        }
        synchronized (this) { // 동시 요청이 AI 서버를 함께 호출하지 않게
            current = snapshots.get(baseUrl);
            if (current != null && current.isFresh()) {
                return current.models();
            }
            current = fetch(baseUrl);
            snapshots.put(baseUrl, current);
            return current.models();
        }
    }

    private Snapshot fetch(String baseUrl) {
        try {
            return new Snapshot(client.fetch(baseUrl), System.nanoTime() + successTtlNanos);
        } catch (RuntimeException e) {
            log.warn("AI 모델 목록 조회 실패 {}: {}", baseUrl, e.getMessage());
            return new Snapshot(null, System.nanoTime() + failureTtlNanos);
        }
    }
}
