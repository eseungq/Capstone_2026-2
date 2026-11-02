package com.capstone.inspection.notification;

import com.capstone.inspection.TestProps;
import com.capstone.inspection.config.AppProperties;
import com.capstone.inspection.domain.user.DeviceTokenRepository;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

// 계약 v4 8장 발송: 100개 단위 분할, payload, DeviceNotRegistered 토큰 삭제, 발송 실패 격리
class PushServiceTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final PushService.Notice NOTICE = new PushService.Notice("REVIEW_REQUIRED", "id-1", "INS-000006",
            "DOOR", "2026-11-02T14:03:24+09:00", "확인 필요", "DOOR INS-000006 작업자 확인이 필요합니다.");

    private HttpServer server;
    private final List<JsonNode> requests = new ArrayList<>();
    private final DeviceTokenRepository repository = Mockito.mock(DeviceTokenRepository.class);

    @AfterEach
    void stop() {
        if (server != null) {
            server.stop(0);
        }
    }

    // 요청마다 메시지 수만큼 티켓을 돌려주는 가짜 Expo. errorToken에는 DeviceNotRegistered
    private PushService service(int status, String errorToken) throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/", exchange -> {
            JsonNode request = MAPPER.readTree(exchange.getRequestBody().readAllBytes());
            requests.add(request);
            List<String> tickets = new ArrayList<>();
            for (JsonNode message : request) {
                tickets.add(message.path("to").asText().equals(errorToken)
                        ? "{\"status\":\"error\",\"message\":\"x\",\"details\":{\"error\":\"DeviceNotRegistered\"}}"
                        : "{\"status\":\"ok\",\"id\":\"t\"}");
            }
            byte[] body = ("{\"data\":[" + String.join(",", tickets) + "]}").getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(status, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        });
        server.start();
        AppProperties d = TestProps.defaults();
        AppProperties props = new AppProperties(d.upload(), d.ai(), d.storage(), d.auth(), d.inspection(),
                d.monitoring(), d.policy(), new AppProperties.Push(true,
                "http://127.0.0.1:" + server.getAddress().getPort() + "/send", 1000, 1000));
        return new PushService(repository, new ExpoPushClient(props, MAPPER),
                new TransactionTemplate(Mockito.mock(PlatformTransactionManager.class)));
    }

    private void registered(List<String> tokens) {
        when(repository.findTokensByRoles(any())).thenReturn(tokens);
    }

    @Test
    @DisplayName("계약 8.3 payload로 보내고 제목·본문을 포함")
    void payload() throws Exception {
        registered(List.of("ExponentPushToken[a]"));
        service(200, null).send(NOTICE);

        JsonNode message = requests.get(0).get(0);
        assertThat(message.path("to").asText()).isEqualTo("ExponentPushToken[a]");
        assertThat(message.path("title").asText()).isEqualTo("확인 필요");
        JsonNode data = message.path("data");
        assertThat(data.path("type").asText()).isEqualTo("REVIEW_REQUIRED");
        assertThat(data.path("inspectionId").asText()).isEqualTo("id-1");
        assertThat(data.path("inspectionNo").asText()).isEqualTo("INS-000006");
        assertThat(data.path("partCode").asText()).isEqualTo("DOOR");
        assertThat(data.path("occurredAt").asText()).isEqualTo("2026-11-02T14:03:24+09:00");
    }

    @Test
    @DisplayName("100개씩 나눠 보냄")
    void splitsBy100() throws Exception {
        registered(IntStream.range(0, 205).mapToObj(i -> "ExponentPushToken[" + i + "]").toList());
        service(200, null).send(NOTICE);
        assertThat(requests).extracting(JsonNode::size).containsExactly(100, 100, 5);
    }

    @Test
    @DisplayName("티켓이 DeviceNotRegistered인 토큰만 삭제")
    void deletesExpired() throws Exception {
        registered(List.of("ExponentPushToken[a]", "ExponentPushToken[gone]"));
        service(200, "ExponentPushToken[gone]").send(NOTICE);
        verify(repository).deleteByTokens(List.of("ExponentPushToken[gone]"));
    }

    @Test
    @DisplayName("Expo 오류 응답이어도 예외가 밖으로 나가지 않고 토큰도 지우지 않음")
    void isolatesFailure() throws Exception {
        registered(List.of("ExponentPushToken[a]"));
        PushService service = service(500, null);
        assertThatCode(() -> service.send(NOTICE)).doesNotThrowAnyException();
        verify(repository, never()).deleteByTokens(any());
    }

    @Test
    @DisplayName("등록된 기기가 없으면 호출하지 않음")
    void noDevices() throws Exception {
        registered(List.of());
        service(200, null).send(NOTICE);
        assertThat(requests).isEmpty();
    }
}
