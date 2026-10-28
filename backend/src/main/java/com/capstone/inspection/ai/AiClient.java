package com.capstone.inspection.ai;

import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.config.AppProperties;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.util.StreamUtils;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

// AI 추론 서버 호출 (계약 v4 7장). 실패는 AiCallException으로 변환
//   연결 실패·5xx → AI_SERVER_ERROR (재시도 대상)
//   4xx           → AI_REQUEST_REJECTED (재시도 안 함, AI 오류 본문을 상세로 보관)
//   읽기 타임아웃 → AI_SERVER_TIMEOUT (재시도 안 함)
//   본문 형식 오류 → AI_RESPONSE_INVALID
@Component
public class AiClient {

    private static final Logger log = LoggerFactory.getLogger(AiClient.class);

    private final RestClient restClient;
    private final ObjectMapper objectMapper;
    private final int retryCount;

    public AiClient(AppProperties props, ObjectMapper objectMapper) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofMillis(props.ai().connectTimeoutMs()));
        factory.setReadTimeout(Duration.ofMillis(props.ai().readTimeoutMs()));
        this.restClient = RestClient.builder()
                .baseUrl(props.ai().baseUrl())
                .requestFactory(factory)
                .build();
        this.objectMapper = objectMapper;
        this.retryCount = Math.max(0, props.ai().retryCount());
    }

    public record Result(AiPredictResponse response, String rawBody) {
    }

    public Result predict(AiPredictRequest request) {
        AiCallException last = null;
        for (int attempt = 0; attempt <= retryCount; attempt++) {
            try {
                return callOnce(request);
            } catch (AiCallException e) {
                last = e;
                if (!e.isRetryable() || attempt == retryCount) {
                    break;
                }
                log.warn("AI 호출 실패, 재시도 {}/{}: {}", attempt + 1, retryCount, e.getMessage());
            }
        }
        throw last;
    }

    private Result callOnce(AiPredictRequest request) {
        String body;
        HttpStatusCode status;
        try {
            Exchange ex = restClient.post()
                    .uri("/internal/v1/predict")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .body(request)
                    .exchange((req, res) -> new Exchange(res.getStatusCode(),
                            StreamUtils.copyToString(res.getBody(), StandardCharsets.UTF_8)));
            status = ex.status();
            body = ex.body();
        } catch (ResourceAccessException e) {
            if (hasCause(e, SocketTimeoutException.class) && !isConnectTimeout(e)) {
                throw new AiCallException(ErrorCode.AI_SERVER_TIMEOUT, "AI 응답 시간 초과: " + e.getMessage(), false);
            }
            throw new AiCallException(ErrorCode.AI_SERVER_ERROR, "AI 연결 실패: " + e.getMessage(), true);
        }

        if (status.is5xxServerError()) {
            throw new AiCallException(ErrorCode.AI_SERVER_ERROR, "AI " + status.value() + ": " + abbreviate(body), true);
        }
        if (status.is4xxClientError()) {
            throw new AiCallException(ErrorCode.AI_REQUEST_REJECTED,
                    "AI " + status.value() + " " + extractAiError(body), false);
        }
        if (!status.is2xxSuccessful()) {
            throw new AiCallException(ErrorCode.AI_RESPONSE_INVALID, "예상하지 못한 상태 코드 " + status.value(), false);
        }
        try {
            return new Result(objectMapper.readValue(body, AiPredictResponse.class), body);
        } catch (JsonProcessingException e) {
            throw new AiCallException(ErrorCode.AI_RESPONSE_INVALID, "응답 JSON 형식 오류: " + e.getOriginalMessage(), false);
        } catch (IllegalArgumentException e) {
            throw new AiCallException(ErrorCode.AI_RESPONSE_INVALID, "응답 본문 없음", false);
        }
    }

    private record Exchange(HttpStatusCode status, String body) {
    }

    // AI 오류 본문 { error: { code, message, traceId } } 에서 코드·메시지만 추려 기록
    private String extractAiError(String body) {
        try {
            JsonNode error = objectMapper.readTree(body).path("error");
            if (!error.isMissingNode()) {
                return error.path("code").asText("") + " " + error.path("message").asText("")
                        + " (aiTraceId=" + error.path("traceId").asText("") + ")";
            }
        } catch (Exception ignored) {
            // 형식이 다르면 원문 일부를 그대로 기록
        }
        return abbreviate(body);
    }

    private static boolean isConnectTimeout(Throwable e) {
        for (Throwable t = e; t != null; t = t.getCause()) {
            if (t.getMessage() != null && t.getMessage().toLowerCase().contains("connect timed out")) {
                return true;
            }
        }
        return false;
    }

    private static boolean hasCause(Throwable e, Class<? extends Throwable> type) {
        for (Throwable t = e; t != null; t = t.getCause()) {
            if (type.isInstance(t)) {
                return true;
            }
        }
        return false;
    }

    private static String abbreviate(String s) {
        if (s == null) {
            return "";
        }
        return s.length() > 300 ? s.substring(0, 300) + "..." : s;
    }
}
