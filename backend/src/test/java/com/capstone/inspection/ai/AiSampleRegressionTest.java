package com.capstone.inspection.ai;

import com.capstone.inspection.TestProps;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.config.AppProperties;
import com.capstone.inspection.domain.inspection.GradcamStatus;
import com.capstone.inspection.domain.inspection.PredictedQuality;
import com.capstone.inspection.inspection.GradcamParser;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

// 실제 AI 응답 원문 3종 회귀 테스트 (AI 김도현 10/28 전달, src/test/resources/ai-samples)
// 02_DEFECT.json은 15MB라 저장소에 올리지 않음 → 파일이 없으면 해당 테스트는 건너뜀
class AiSampleRegressionTest {

    private static final String MODEL = "door-swin-tiny-e20-8d042c7bfab2";

    private final AiJson aiJson = new AiJson(new ObjectMapper(), TestProps.defaults());
    private HttpServer server;

    @AfterEach
    void stopServer() {
        if (server != null) {
            server.stop(0);
        }
    }

    private static byte[] sample(String name) throws IOException {
        try (InputStream in = AiSampleRegressionTest.class.getResourceAsStream("/ai-samples/" + name)) {
            assumeTrue(in != null, name + " 없음 (저장소에 올리지 않는 큰 샘플)");
            return in.readAllBytes();
        }
    }

    private AiPredictResponse parse(byte[] json) throws IOException {
        return aiJson.mapper().readValue(json, AiPredictResponse.class);
    }

    @Test
    void goodSample() throws IOException {
        AiPredictResponse r = parse(sample("01_GOOD.json"));
        assertThat(AiResponseValidator.validate(r, r.inspectionId(), MODEL)).isEqualTo(PredictedQuality.GOOD);
        assertThat(r.modelVersion()).isEqualTo(MODEL);
        assertThat(r.calibratedDefectProbability()).isNull();
        assertThat(r.calibratorVersion()).isNull();
        assertThat(r.gradcam()).isNull(); // GOOD 예측은 백엔드에서 NOT_REQUIRED
    }

    @Test
    void defectSample() throws IOException {
        AiPredictResponse r = parse(sample("02_DEFECT.json"));
        assertThat(AiResponseValidator.validate(r, r.inspectionId(), MODEL)).isEqualTo(PredictedQuality.DEFECT);
        assertThat(r.gradcam().imageBase64().length()).isGreaterThan(15_000_000);

        GradcamParser.Parsed cam = GradcamParser.parse(r.inspectionId(), r.gradcam());
        assertThat(cam.status()).isEqualTo(GradcamStatus.GENERATED);
        assertThat(cam.info().contentType()).isEqualTo("image/png");
        assertThat(cam.info().width()).isEqualTo(4224);
        assertThat(cam.info().height()).isEqualTo(2376);
        assertThat(cam.info().width()).isEqualTo(r.imageWidth());
        assertThat(cam.info().height()).isEqualTo(r.imageHeight());
    }

    @Test
    void defectSampleThroughAiClient() throws IOException {
        byte[] body = sample("02_DEFECT.json");
        AiPredictResponse expected = parse(body);
        AtomicInteger calls = startServer(200, body);

        AiClient.Result result = client().predict(
                new AiPredictRequest(expected.inspectionId(), "DOOR", MODEL, "http://example.invalid/img"));
        assertThat(calls.get()).isEqualTo(1);
        assertThat(result.response().gradcam().imageBase64()).isEqualTo(expected.gradcam().imageBase64());
    }

    @Test
    void errorSampleIsRejectedWithoutRetry() throws IOException {
        AtomicInteger calls = startServer(422, sample("03_ERROR_HTTP422.json"));

        assertThatThrownBy(() -> client().predict(
                new AiPredictRequest("749f4308-d0bf-5dd3-81e3-0c9e53c9580e", "DOOR", MODEL, "http://example.invalid/img")))
                .isInstanceOf(AiCallException.class)
                .satisfies(e -> {
                    AiCallException ai = (AiCallException) e;
                    assertThat(ai.getErrorCode()).isEqualTo(ErrorCode.AI_REQUEST_REJECTED);
                    assertThat(ai.isRetryable()).isFalse();
                    assertThat(ai.getMessage()).contains("IMAGE_ACCESS_FAILED"); // error_detail로 저장되는 값
                });
        assertThat(calls.get()).isEqualTo(1); // retry-count 1이어도 4xx는 재시도 안 함
    }

    @Test
    void parsesThirtyMillionCharBase64() throws IOException {
        String huge = "A".repeat(30_000_000);
        String json = "{\"inspectionId\":\"x\",\"gradcam\":{\"targetClass\":\"DEFECT\",\"format\":\"png\",\"imageBase64\":\""
                + huge + "\"}}";
        AiPredictResponse r = aiJson.mapper().readValue(json, AiPredictResponse.class);
        assertThat(r.gradcam().imageBase64()).hasSize(30_000_000);

        // 앱 API용 기본 ObjectMapper는 Jackson 기본 한도(2,000만 자)에 걸림
        assertThatThrownBy(() -> new ObjectMapper().readValue(json, AiPredictResponse.class))
                .hasMessageContaining("exceeds the maximum allowed (20000000");
    }

    private AtomicInteger startServer(int status, byte[] body) throws IOException {
        AtomicInteger calls = new AtomicInteger();
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/internal/v1/predict", exchange -> {
            calls.incrementAndGet();
            exchange.getRequestBody().readAllBytes();
            exchange.getResponseHeaders().add("Content-Type", "application/json");
            exchange.sendResponseHeaders(status, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        });
        server.start();
        return calls;
    }

    private AiClient client() {
        AppProperties base = TestProps.defaults();
        AppProperties.Ai ai = base.ai();
        AppProperties props = new AppProperties(base.upload(),
                new AppProperties.Ai("http://127.0.0.1:" + server.getAddress().getPort(), ai.connectTimeoutMs(),
                        ai.readTimeoutMs(), ai.retryCount(), ai.imageSizeCheckEnabled(), ai.maxResponseStringChars()),
                base.storage(), base.auth(), base.inspection(), base.monitoring());
        return new AiClient(props, aiJson);
    }
}
