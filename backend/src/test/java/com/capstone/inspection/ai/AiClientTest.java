package com.capstone.inspection.ai;

import com.capstone.inspection.TestProps;
import com.capstone.inspection.config.AppProperties;
import com.fasterxml.jackson.databind.JsonNode;
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

import static org.assertj.core.api.Assertions.assertThat;

// 계약 v4 7.1 요청 전송. 실제 AI 서버는 chunked 요청 본문을 읽지 못해 400 (11/03 연동 시험)
class AiClientTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final String MODEL = "door-swin-tiny-e02-28a2dd1cb40b-dev";

    private HttpServer server;
    private final List<JsonNode> requests = new ArrayList<>();
    private final List<String> contentLengths = new ArrayList<>();
    private final List<String> transferEncodings = new ArrayList<>();

    @AfterEach
    void stop() {
        if (server != null) {
            server.stop(0);
        }
    }

    // 요청을 기록하고 GOOD 응답을 돌려주는 가짜 AI
    private AiClient client() throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/internal/v1/predict", exchange -> {
            requests.add(MAPPER.readTree(exchange.getRequestBody().readAllBytes()));
            contentLengths.add(exchange.getRequestHeaders().getFirst("Content-Length"));
            transferEncodings.add(exchange.getRequestHeaders().getFirst("Transfer-Encoding"));
            byte[] body = ("{\"inspectionId\":\"insp-1\",\"modelVersion\":\"" + MODEL + "\",\"predictedQuality\":\"GOOD\","
                    + "\"rawDefectProbability\":0.0109,\"calibratedDefectProbability\":null,\"calibratorVersion\":null,"
                    + "\"imageWidth\":4032,\"imageHeight\":1908,\"gradcam\":null,\"inferenceTimeMs\":1517}")
                    .getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        });
        server.start();
        AppProperties d = TestProps.defaults();
        AppProperties.Ai ai = d.ai();
        AppProperties props = new AppProperties(d.upload(), new AppProperties.Ai(
                "http://127.0.0.1:" + server.getAddress().getPort(), ai.connectTimeoutMs(), ai.readTimeoutMs(),
                ai.retryCount(), ai.imageSizeCheckEnabled(), ai.maxResponseStringChars(), ai.modelCheckEnabled(),
                ai.modelCheckTtlSeconds(), ai.modelCheckFailureTtlSeconds(), ai.modelCheckConnectTimeoutMs(),
                ai.modelCheckReadTimeoutMs()),
                d.storage(), d.auth(), d.inspection(), d.monitoring(), d.policy(), d.push());
        return new AiClient(props, new AiJson(MAPPER, props));
    }

    @Test
    @DisplayName("predict 요청은 Content-Length를 붙여 보내고 chunked로 보내지 않음")
    void sendsContentLength() throws IOException {
        AiPredictRequest request = new AiPredictRequest("insp-1", "DOOR", MODEL,
                "http://100.117.82.89:8080/api/v1/images/img-1?exp=1&sig=s");

        AiClient.Result result = client().predict(request);

        assertThat(result.response().modelVersion()).isEqualTo(MODEL);
        assertThat(contentLengths.get(0)).isNotNull();
        assertThat(transferEncodings.get(0)).isNull();
        JsonNode sent = requests.get(0);
        assertThat(sent.path("inspectionId").asText()).isEqualTo("insp-1");
        assertThat(sent.path("partCode").asText()).isEqualTo("DOOR");
        assertThat(sent.path("requestedModelVersion").asText()).isEqualTo(MODEL);
        assertThat(sent.path("imageUrl").asText()).isEqualTo(request.imageUrl());
    }
}
