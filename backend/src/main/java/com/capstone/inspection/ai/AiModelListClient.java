package com.capstone.inspection.ai;

import com.capstone.inspection.config.AppProperties;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.time.Duration;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

// AI 서버의 로드 가능 모델 조회. 접수·모니터링을 오래 잡지 않게 분석용과 다른 짧은 타임아웃 사용
@Component
public class AiModelListClient {

    private final SimpleClientHttpRequestFactory factory;
    private final Map<String, RestClient> clients = new ConcurrentHashMap<>(); // AI 주소별
    private final ObjectMapper objectMapper;

    public AiModelListClient(AppProperties props, AiJson aiJson) {
        this.factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofMillis(props.ai().modelCheckConnectTimeoutMs()));
        factory.setReadTimeout(Duration.ofMillis(props.ai().modelCheckReadTimeoutMs()));
        this.objectMapper = aiJson.mapper();
    }

    // baseUrl AI 서버의 modelVersion → loadable. 연결 실패·오류 응답·형식 오류는 예외
    public Map<String, Boolean> fetch(String baseUrl) {
        RestClient restClient = clients.computeIfAbsent(baseUrl,
                url -> RestClient.builder().baseUrl(url).requestFactory(factory).build());
        String body = restClient.get()
                .uri("/internal/v1/models")
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(String.class);
        try {
            return AiModelListParser.parse(objectMapper.readTree(body == null ? "" : body));
        } catch (JsonProcessingException e) {
            throw new IllegalArgumentException("JSON 아님", e);
        }
    }
}
