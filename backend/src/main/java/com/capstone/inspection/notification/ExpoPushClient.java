package com.capstone.inspection.notification;

import com.capstone.inspection.config.AppProperties;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

// Expo Push API 호출. 한 번에 최대 100개, 응답 data는 보낸 순서와 같은 티켓 배열 (Expo 공식 문서)
// receipt 조회는 이번 범위에 없음: 발송 응답의 티켓까지만 확인
@Component
public class ExpoPushClient {

    public static final int MAX_MESSAGES = 100;

    private final RestClient restClient;
    private final ObjectMapper objectMapper;

    public ExpoPushClient(AppProperties props, ObjectMapper objectMapper) {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(Duration.ofMillis(props.push().connectTimeoutMs()));
        factory.setReadTimeout(Duration.ofMillis(props.push().readTimeoutMs()));
        this.restClient = RestClient.builder()
                .baseUrl(props.push().expoUrl())
                .requestFactory(factory)
                .build();
        this.objectMapper = objectMapper;
    }

    public record Message(String to, String title, String body, Map<String, Object> data) {
    }

    // error: details.error 값 (없으면 message). 성공이면 null
    public record Ticket(String token, String error) {
    }

    // 요청 전체가 거절되거나 응답 형식이 다르면 예외
    public List<Ticket> send(List<Message> messages) {
        String body = restClient.post()
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .body(messages)
                .retrieve()
                .body(String.class);
        return parseTickets(messages, body);
    }

    private List<Ticket> parseTickets(List<Message> messages, String body) {
        JsonNode data;
        try {
            data = objectMapper.readTree(body == null ? "" : body).path("data");
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("Expo 응답이 JSON이 아님", e);
        }
        if (!data.isArray() || data.size() != messages.size()) {
            throw new IllegalStateException("Expo 응답 형식 오류: " + body);
        }
        List<Ticket> tickets = new ArrayList<>();
        for (int i = 0; i < messages.size(); i++) {
            JsonNode ticket = data.get(i);
            String error = null;
            if (!"ok".equals(ticket.path("status").asText())) {
                error = ticket.path("details").path("error").asText(ticket.path("message").asText("UNKNOWN"));
            }
            tickets.add(new Ticket(messages.get(i).to(), error));
        }
        return tickets;
    }
}
