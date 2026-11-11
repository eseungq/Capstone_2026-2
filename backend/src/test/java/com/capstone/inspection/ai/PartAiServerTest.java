package com.capstone.inspection.ai;

import com.capstone.inspection.TestProps;
import com.capstone.inspection.config.AppProperties;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

// 부품별 AI 서버 (app.ai.part-base-urls): 도어는 기본 주소, 프레임은 별도 주소
class PartAiServerTest {

    private static final String DOOR_URL = "http://door-ai";
    private static final String FRAME_URL = "http://frame-ai";

    private final List<HttpServer> servers = new ArrayList<>();

    @AfterEach
    void stop() {
        servers.forEach(s -> s.stop(0));
    }

    private static AppProperties props(String baseUrl, Map<String, String> partBaseUrls) {
        AppProperties d = TestProps.defaults();
        AppProperties.Ai a = d.ai();
        return new AppProperties(d.upload(), new AppProperties.Ai(baseUrl, a.connectTimeoutMs(), a.readTimeoutMs(),
                a.retryCount(), a.imageSizeCheckEnabled(), a.maxResponseStringChars(), true, 30, 5,
                a.modelCheckConnectTimeoutMs(), a.modelCheckReadTimeoutMs(), partBaseUrls),
                d.storage(), d.auth(), d.inspection(), d.monitoring(), d.policy(), d.push());
    }

    @Test
    @DisplayName("부품 주소가 있으면 그 주소, 없으면 기본 주소. 환경변수로 들어온 소문자·점 키도 인식")
    void baseUrlFor() {
        AppProperties.Ai ai = props(DOOR_URL, Map.of("frame", FRAME_URL, "cowl.cover", "http://cowl-ai")).ai();
        assertThat(ai.baseUrlFor("FRAME")).isEqualTo(FRAME_URL);
        assertThat(ai.baseUrlFor("COWL_COVER")).isEqualTo("http://cowl-ai");
        assertThat(ai.baseUrlFor("DOOR")).isEqualTo(DOOR_URL);
        assertThat(ai.allBaseUrls()).hasSize(3).startsWith(DOOR_URL);
        assertThat(props(DOOR_URL, null).ai().allBaseUrls()).containsExactly(DOOR_URL);
    }

    // 주소별로 정해 둔 목록을 돌려줌 (null이면 조회 실패)
    private static AiModelListClient fakeList(Map<String, Map<String, Boolean>> byUrl) {
        AppProperties p = TestProps.defaults();
        return new AiModelListClient(p, new AiJson(new ObjectMapper(), p)) {
            @Override
            public Map<String, Boolean> fetch(String baseUrl) {
                Map<String, Boolean> models = byUrl.get(baseUrl);
                if (models == null) {
                    throw new IllegalStateException("연결 실패 " + baseUrl);
                }
                return models;
            }
        };
    }

    @Test
    @DisplayName("모델 확인은 두 서버 목록을 합쳐 판단, 한 서버가 꺼져도 다른 서버 모델은 정상 판단")
    void availabilityAcrossServers() {
        AppProperties p = props(DOOR_URL, Map.of("FRAME", FRAME_URL));
        var both = new ModelAvailabilityService(p, fakeList(Map.of(
                DOOR_URL, Map.of("door-m", true), FRAME_URL, Map.of("frame-m", true))));
        assertThat(both.check("door-m")).isEqualTo(ModelAvailability.AVAILABLE);
        assertThat(both.check("frame-m")).isEqualTo(ModelAvailability.AVAILABLE);
        assertThat(both.check("other")).isEqualTo(ModelAvailability.NOT_LOADABLE);

        var doorDown = new ModelAvailabilityService(p, fakeList(Map.of(FRAME_URL, Map.of("frame-m", true))));
        assertThat(doorDown.check("frame-m")).isEqualTo(ModelAvailability.AVAILABLE);
        assertThat(doorDown.check("door-m")).isEqualTo(ModelAvailability.UNKNOWN);
    }

    private String startAi(String name, List<String> hits) throws IOException {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/internal/v1/predict", exchange -> {
            hits.add(name);
            exchange.getRequestBody().readAllBytes();
            byte[] body = ("{\"inspectionId\":\"i\",\"modelVersion\":\"" + name + "\",\"predictedQuality\":\"GOOD\","
                    + "\"rawDefectProbability\":0.01,\"imageWidth\":1,\"imageHeight\":1,\"inferenceTimeMs\":1}")
                    .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        });
        server.start();
        servers.add(server);
        return "http://127.0.0.1:" + server.getAddress().getPort();
    }

    @Test
    @DisplayName("추론 요청은 부품 코드에 맞는 AI 서버로 감")
    void predictRoutesByPart() throws IOException {
        List<String> hits = new ArrayList<>();
        String door = startAi("door", hits);
        String frame = startAi("frame", hits);
        AppProperties p = props(door, Map.of("FRAME", frame));
        AiClient client = new AiClient(p, new AiJson(new ObjectMapper(), p));

        client.predict(new AiPredictRequest("i", "FRAME", "frame-m", "http://x/img"));
        client.predict(new AiPredictRequest("i", "DOOR", "door-m", "http://x/img"));

        assertThat(hits).containsExactly("frame", "door");
    }
}
