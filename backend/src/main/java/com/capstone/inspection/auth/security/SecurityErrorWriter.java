package com.capstone.inspection.auth.security;

import com.capstone.inspection.common.api.ErrorResponse;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.common.trace.TraceIdFilter;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.slf4j.MDC;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

// Security 필터 단계의 401·403도 공통 오류 형식으로 응답 (컨트롤러 밖이라 GlobalExceptionHandler가 처리하지 못함)
@Component
@RequiredArgsConstructor
public class SecurityErrorWriter {

    private final ObjectMapper objectMapper;

    public void write(HttpServletResponse response, ErrorCode code) throws IOException {
        response.setStatus(code.getStatus().value());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        String traceId = MDC.get(TraceIdFilter.MDC_KEY);
        ErrorResponse body = ErrorResponse.of(code.name(), code.getDefaultMessage(), traceId, null, null);
        objectMapper.writeValue(response.getOutputStream(), body);
    }
}
