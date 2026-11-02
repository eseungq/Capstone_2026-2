package com.capstone.inspection.ai;

import com.capstone.inspection.common.error.BusinessException;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.config.AppProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.Map;

// 모델 로드 확인 (계약 v4 6.1, 6.2). 접수·재검사·부품 목록·모니터링이 모두 이 판단을 사용
// AI 조회 결과는 짧게 캐시해서 접수·폴링마다 AI 서버를 호출하지 않음
@Service
public class ModelAvailabilityService {

    private static final Logger log = LoggerFactory.getLogger(ModelAvailabilityService.class);

    private final AiModelListClient client;
    private final boolean enabled;
    private final long successTtlNanos;
    private final long failureTtlNanos;

    private volatile Snapshot snapshot;

    // models가 null이면 확인 실패 (UNKNOWN)
    private record Snapshot(Map<String, Boolean> models, long expiresAtNanos) {
        boolean isFresh() {
            return System.nanoTime() - expiresAtNanos < 0;
        }
    }

    public ModelAvailabilityService(AppProperties props, AiModelListClient client) {
        this.client = client;
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
        Map<String, Boolean> models = currentModels();
        if (models == null) {
            return ModelAvailability.UNKNOWN;
        }
        return Boolean.TRUE.equals(models.get(modelVersion))
                ? ModelAvailability.AVAILABLE : ModelAvailability.NOT_LOADABLE;
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

    private Map<String, Boolean> currentModels() {
        Snapshot current = snapshot;
        if (current != null && current.isFresh()) {
            return current.models();
        }
        synchronized (this) { // 동시 요청이 AI 서버를 함께 호출하지 않게
            current = snapshot;
            if (current != null && current.isFresh()) {
                return current.models();
            }
            current = fetch();
            snapshot = current;
            return current.models();
        }
    }

    private Snapshot fetch() {
        try {
            return new Snapshot(client.fetch(), System.nanoTime() + successTtlNanos);
        } catch (RuntimeException e) {
            log.warn("AI 모델 목록 조회 실패: {}", e.getMessage());
            return new Snapshot(null, System.nanoTime() + failureTtlNanos);
        }
    }
}
