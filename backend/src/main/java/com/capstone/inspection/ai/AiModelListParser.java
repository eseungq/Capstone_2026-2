package com.capstone.inspection.ai;

import com.fasterxml.jackson.databind.JsonNode;

import java.util.HashMap;
import java.util.Map;

// GET {AI}/internal/v1/models 응답 해석. 실제 AI 형식은 미확정이라 형식이 정해지면 이 클래스만 고침
// 현재 Mock 기준: { "data": [ { modelVersion, partCode, calibratorVersion, loadable } ] }
final class AiModelListParser {

    private AiModelListParser() {
    }

    // modelVersion → loadable. 형식이 다르면 IllegalArgumentException
    static Map<String, Boolean> parse(JsonNode root) {
        JsonNode data = root == null ? null : root.get("data");
        if (data == null || !data.isArray()) {
            throw new IllegalArgumentException("data 배열 없음");
        }
        Map<String, Boolean> models = new HashMap<>();
        for (JsonNode item : data) {
            JsonNode version = item.get("modelVersion");
            JsonNode loadable = item.get("loadable");
            if (version == null || !version.isTextual() || loadable == null || !loadable.isBoolean()) {
                throw new IllegalArgumentException("modelVersion 또는 loadable 형식 오류");
            }
            models.put(version.asText(), loadable.asBoolean());
        }
        return models;
    }
}
