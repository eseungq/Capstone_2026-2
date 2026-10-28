package com.capstone.inspection.ai;

import com.capstone.inspection.config.AppProperties;
import com.fasterxml.jackson.core.StreamReadConstraints;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.stereotype.Component;

// AI 응답 파싱 전용 ObjectMapper. Grad-CAM base64가 수천만 자까지 커질 수 있어 문자열 길이 한도만 올림
// 앱 API용 전역 ObjectMapper 한도는 그대로 둠
@Component
public class AiJson {

    private final ObjectMapper mapper;

    public AiJson(ObjectMapper objectMapper, AppProperties props) {
        this.mapper = objectMapper.copy();
        this.mapper.getFactory().setStreamReadConstraints(StreamReadConstraints.builder()
                .maxStringLength(props.ai().maxResponseStringChars())
                .build());
    }

    public ObjectMapper mapper() {
        return mapper;
    }
}
