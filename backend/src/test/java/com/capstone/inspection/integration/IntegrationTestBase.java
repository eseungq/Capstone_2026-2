package com.capstone.inspection.integration;

import com.capstone.inspection.ai.AiCallException;
import com.capstone.inspection.ai.AiClient;
import com.capstone.inspection.ai.AiJson;
import com.capstone.inspection.ai.AiModelListClient;
import com.capstone.inspection.ai.AiPredictRequest;
import com.capstone.inspection.ai.AiPredictResponse;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.config.AppProperties;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.testcontainers.DockerClientFactory;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.junit.jupiter.Testcontainers;

import java.time.Duration;
import java.time.Instant;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.function.Supplier;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

// 통합 테스트 공통: 실제 MySQL 8.4 + Flyway(V1~V5 + 개발 시드), 실제 보안 필터. AI만 가짜
// 시드를 포함해 시드 계정·Mock 모델·예시 정책이 제약 위에서 그대로 동작하는지도 함께 확인
// 컨테이너는 테스트 클래스 전체에서 1개를 공유. Docker가 없으면 전부 건너뜀
@SpringBootTest(properties = {
        "app.ai.model-check-ttl-seconds=0",
        "app.ai.model-check-failure-ttl-seconds=0",
        "app.storage.local-root=build/test-storage"
})
@AutoConfigureMockMvc
@Testcontainers(disabledWithoutDocker = true)
@Import(IntegrationTestBase.FakeAiConfig.class)
abstract class IntegrationTestBase {

    protected static final String MOCK_MODEL = "mock-door-swin-t-v1";
    protected static final String REAL_MODEL = "door-swin-tiny-e20-8d042c7bfab2";
    private static final Duration ANALYSIS_WAIT = Duration.ofSeconds(15);
    // 1x1 PNG
    private static final byte[] IMAGE = java.util.Base64.getDecoder().decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNgYPgPAAEDAQAIicLsAAAAAElFTkSuQmCC");

    private static final MySQLContainer<?> MYSQL = new MySQLContainer<>("mysql:8.4")
            .withDatabaseName("inspection").withUsername("inspection").withPassword("inspection")
            .withUrlParam("serverTimezone", "Asia/Seoul").withUrlParam("characterEncoding", "UTF-8")
            .withCommand("--character-set-server=utf8mb4", "--collation-server=utf8mb4_unicode_ci");

    static {
        if (DockerClientFactory.instance().isDockerAvailable()) {
            MYSQL.start();
        }
    }

    @DynamicPropertySource
    static void database(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", MYSQL::getJdbcUrl);
        registry.add("spring.datasource.username", MYSQL::getUsername);
        registry.add("spring.datasource.password", MYSQL::getPassword);
    }

    // 테스트마다 바꾸는 가짜 AI 동작
    protected static volatile Function<AiPredictRequest, AiPredictResponse> ai;
    protected static volatile Supplier<Map<String, Boolean>> aiModels;

    @TestConfiguration
    static class FakeAiConfig {
        @Bean
        @Primary
        AiClient fakeAiClient(AppProperties props, AiJson aiJson) {
            return new AiClient(props, aiJson) {
                @Override
                public Result predict(AiPredictRequest request) {
                    return new Result(ai.apply(request), "{}");
                }
            };
        }

        @Bean
        @Primary
        AiModelListClient fakeAiModelListClient(AppProperties props, AiJson aiJson) {
            return new AiModelListClient(props, aiJson) {
                @Override
                public Map<String, Boolean> fetch(String baseUrl) {
                    return aiModels.get();
                }
            };
        }
    }

    @Autowired
    protected MockMvc mvc;
    @Autowired
    protected JdbcTemplate jdbc;
    @Autowired
    protected ObjectMapper mapper;

    private static String workerToken;
    private static String adminToken;
    private static String deviceToken;

    // 시드 상태로 되돌림 (Mock 모델·예시 정책 적용 중). 정책 행은 검사가 참조하므로 지우지 않음
    @BeforeEach
    void resetState() throws Exception {
        ai = goodBelowThreshold();
        aiModels = () -> Map.of(MOCK_MODEL, true, REAL_MODEL, true);
        jdbc.update("update automation_policy set active = false");
        jdbc.update("update ai_model set active = false");
        jdbc.update("update ai_model set active = true where model_version = ?", MOCK_MODEL);
        jdbc.update("update automation_policy set active = true where policy_version = 'example-door-p1'");
        jdbc.update("delete from device_token");
        if (workerToken == null) {
            workerToken = login("worker01", "Worker1234!");
            adminToken = login("admin01", "Admin1234!");
            deviceToken = login("device-door", "Device1234!");
        }
    }

    protected String worker() {
        return workerToken;
    }

    protected String admin() {
        return adminToken;
    }

    protected String device() {
        return deviceToken;
    }

    private String login(String id, String password) throws Exception {
        MvcResult result = mvc.perform(post("/api/v1/auth/login").contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(Map.of("loginId", id, "password", password)))).andReturn();
        return json(result).at("/data/accessToken").asText();
    }

    // 가짜 AI 응답
    protected static AiPredictResponse response(AiPredictRequest r, String quality, double raw, Double calibrated) {
        return new AiPredictResponse(r.inspectionId(), r.requestedModelVersion(), quality, raw, calibrated,
                calibrated == null ? null : "mock-cal-v1", 64, 64, null, 10);
    }

    // 예시 정책(0.05) 이하 → AUTO_PASS
    protected static Function<AiPredictRequest, AiPredictResponse> goodBelowThreshold() {
        return r -> response(r, "GOOD", 0.01, 0.021);
    }

    // 예시 정책(0.05) 초과 → REVIEW(ABOVE_THRESHOLD)
    protected static Function<AiPredictRequest, AiPredictResponse> goodAboveThreshold() {
        return r -> response(r, "GOOD", 0.2, 0.2);
    }

    protected static Function<AiPredictRequest, AiPredictResponse> aiServerError() {
        return r -> {
            throw new AiCallException(ErrorCode.AI_SERVER_ERROR, "가짜 AI 오류", false);
        };
    }

    // HTTP 도우미
    protected MvcResult call(MockHttpServletRequestBuilder request, String token) throws Exception {
        return mvc.perform(request.header("Authorization", "Bearer " + token)).andReturn();
    }

    protected MvcResult postJson(String url, Object body, String token) throws Exception {
        return call(post(url).contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsString(body)), token);
    }

    protected JsonNode json(MvcResult result) throws Exception {
        return mapper.readTree(result.getResponse().getContentAsByteArray());
    }

    protected String errorCode(MvcResult result) throws Exception {
        return json(result).at("/error/code").asText();
    }

    // 접수 가능한 작은 PNG (테스트마다 같은 사진)
    protected static byte[] imageBytes() {
        return IMAGE.clone();
    }

    protected MvcResult submit() throws Exception {
        return call(multipart("/api/v1/inspections")
                .file(new MockMultipartFile("image", "t.png", "image/png", IMAGE)).param("partCode", "DOOR"), device());
    }

    // 사진 접수 후 분석이 끝난 상세를 반환
    protected JsonNode submitAndWait() throws Exception {
        MvcResult result = submit();
        assertThat(result.getResponse().getStatus()).isEqualTo(202);
        return waitFinished(json(result).at("/data/inspectionId").asText());
    }

    protected JsonNode waitFinished(String inspectionId) throws Exception {
        Instant deadline = Instant.now().plus(ANALYSIS_WAIT);
        while (Instant.now().isBefore(deadline)) {
            JsonNode detail = json(call(get("/api/v1/inspections/{id}", inspectionId), worker())).path("data");
            String status = detail.path("status").asText();
            if (status.equals("COMPLETED") || status.equals("FAILED")) {
                return detail;
            }
            Thread.sleep(50);
        }
        throw new AssertionError("분석이 끝나지 않음: " + inspectionId);
    }

    protected static String unique(String prefix) {
        return prefix + "-" + UUID.randomUUID().toString().substring(0, 8);
    }

    protected long inspectionCount() {
        return jdbc.queryForObject("select count(*) from inspection", Long.class);
    }
}
