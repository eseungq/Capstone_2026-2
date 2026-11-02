package com.capstone.inspection.ai;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class AiModelListParserTest {

    private static JsonNode json(String body) throws Exception {
        return new ObjectMapper().readTree(body);
    }

    @Test
    @DisplayName("Mock 형식을 modelVersion → loadable로 해석")
    void parses() throws Exception {
        var models = AiModelListParser.parse(json("""
                {"data":[{"modelVersion":"a","partCode":"DOOR","calibratorVersion":null,"loadable":true},
                         {"modelVersion":"b","partCode":"DOOR","calibratorVersion":"c","loadable":false}]}"""));
        assertThat(models).containsEntry("a", true).containsEntry("b", false).hasSize(2);
    }

    @ParameterizedTest
    @ValueSource(strings = {"{}", "[]", "{\"data\":{}}", "{\"data\":[{\"modelVersion\":\"a\"}]}",
            "{\"data\":[{\"modelVersion\":1,\"loadable\":true}]}", "{\"data\":[{\"modelVersion\":\"a\",\"loadable\":\"yes\"}]}"})
    @DisplayName("형식이 다르면 예외")
    void rejects(String body) throws Exception {
        JsonNode root = json(body);
        assertThatThrownBy(() -> AiModelListParser.parse(root)).isInstanceOf(IllegalArgumentException.class);
    }
}
