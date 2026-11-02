package com.capstone.inspection.ai;

import com.capstone.inspection.TestProps;
import com.capstone.inspection.common.error.BusinessException;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.config.AppProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.ArrayDeque;
import java.util.Deque;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

// 계약 v4 6.1, 6.2 모델 로드 확인: 세 가지 결과와 캐시
class ModelAvailabilityServiceTest {

    private static final String MODEL = "mock-door-swin-t-v1";

    // 정해 둔 응답을 차례로 돌려주는 가짜 클라이언트 (RuntimeException이면 던짐)
    private static class FakeClient extends AiModelListClient {
        final Deque<Object> answers = new ArrayDeque<>();
        int calls;

        FakeClient(Object... answers) {
            super(TestProps.defaults(), new AiJson(new ObjectMapper(), TestProps.defaults()));
            this.answers.addAll(java.util.List.of(answers));
        }

        @Override
        @SuppressWarnings("unchecked")
        public Map<String, Boolean> fetch() {
            calls++;
            Object answer = answers.size() > 1 ? answers.poll() : answers.peek();
            if (answer instanceof RuntimeException e) {
                throw e;
            }
            return (Map<String, Boolean>) answer;
        }
    }

    private static AppProperties props(boolean enabled, int ttl, int failureTtl) {
        AppProperties d = TestProps.defaults();
        AppProperties.Ai a = d.ai();
        return new AppProperties(d.upload(), new AppProperties.Ai(a.baseUrl(), a.connectTimeoutMs(), a.readTimeoutMs(),
                a.retryCount(), a.imageSizeCheckEnabled(), a.maxResponseStringChars(), enabled, ttl, failureTtl,
                a.modelCheckConnectTimeoutMs(), a.modelCheckReadTimeoutMs()),
                d.storage(), d.auth(), d.inspection(), d.monitoring(), d.policy(), d.push());
    }

    @Test
    @DisplayName("목록에 있고 loadable=true면 AVAILABLE")
    void available() {
        var service = new ModelAvailabilityService(props(true, 30, 5), new FakeClient(Map.of(MODEL, true)));
        assertThat(service.check(MODEL)).isEqualTo(ModelAvailability.AVAILABLE);
    }

    @Test
    @DisplayName("loadable=false거나 목록에 없으면 NOT_LOADABLE이고 접수는 422")
    void notLoadable() {
        var service = new ModelAvailabilityService(props(true, 30, 5),
                new FakeClient(Map.of(MODEL, false)));
        assertThat(service.check(MODEL)).isEqualTo(ModelAvailability.NOT_LOADABLE);
        assertThat(service.check("other-model")).isEqualTo(ModelAvailability.NOT_LOADABLE);
        assertThatThrownBy(() -> service.requireNotRejected(MODEL))
                .isInstanceOfSatisfying(BusinessException.class,
                        e -> assertThat(e.getErrorCode()).isEqualTo(ErrorCode.MODEL_NOT_AVAILABLE));
    }

    @Test
    @DisplayName("조회 실패면 UNKNOWN이고 접수는 거절하지 않음")
    void unknown() {
        var service = new ModelAvailabilityService(props(true, 30, 5),
                new FakeClient(new IllegalStateException("연결 실패")));
        assertThat(service.check(MODEL)).isEqualTo(ModelAvailability.UNKNOWN);
        assertThatCode(() -> service.requireNotRejected(MODEL)).doesNotThrowAnyException();
    }

    @Test
    @DisplayName("확인을 끄면 AI를 호출하지 않고 AVAILABLE")
    void disabled() {
        FakeClient client = new FakeClient(new IllegalStateException("호출되면 안 됨"));
        var service = new ModelAvailabilityService(props(false, 30, 5), client);
        assertThat(service.check(MODEL)).isEqualTo(ModelAvailability.AVAILABLE);
        assertThat(client.calls).isZero();
    }

    @Test
    @DisplayName("성공 결과는 캐시 시간 동안 다시 조회하지 않음")
    void cachesSuccess() {
        FakeClient client = new FakeClient(Map.of(MODEL, true));
        var service = new ModelAvailabilityService(props(true, 30, 5), client);
        service.check(MODEL);
        service.check(MODEL);
        assertThat(client.calls).isEqualTo(1);
    }

    @Test
    @DisplayName("실패 결과도 캐시하고, 만료 후 다시 조회하면 복구")
    void cachesFailureThenRecovers() {
        FakeClient cached = new FakeClient(new IllegalStateException("연결 실패"));
        var cachedService = new ModelAvailabilityService(props(true, 30, 5), cached);
        cachedService.check(MODEL);
        cachedService.check(MODEL);
        assertThat(cached.calls).isEqualTo(1);

        FakeClient expired = new FakeClient(new IllegalStateException("연결 실패"), Map.of(MODEL, true));
        var expiredService = new ModelAvailabilityService(props(true, 30, 0), expired);
        assertThat(expiredService.check(MODEL)).isEqualTo(ModelAvailability.UNKNOWN);
        assertThat(expiredService.check(MODEL)).isEqualTo(ModelAvailability.AVAILABLE);
    }
}
