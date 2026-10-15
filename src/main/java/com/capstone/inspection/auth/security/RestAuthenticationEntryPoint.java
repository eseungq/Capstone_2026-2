package com.capstone.inspection.auth.security;

import com.capstone.inspection.common.error.ErrorCode;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.stereotype.Component;

import java.io.IOException;

// 인증이 필요한 경로에 토큰이 없거나 잘못된 경우 → 401
@Component
@RequiredArgsConstructor
public class RestAuthenticationEntryPoint implements AuthenticationEntryPoint {

    private final SecurityErrorWriter errorWriter;

    @Override
    public void commence(HttpServletRequest request, HttpServletResponse response,
                         AuthenticationException authException) throws IOException {
        Object code = request.getAttribute(JwtAuthenticationFilter.AUTH_ERROR_ATTR);
        // 만료면 AUTH_TOKEN_EXPIRED(앱이 재발급), 그 외(없음·위조·형식 오류)는 AUTH_TOKEN_INVALID
        errorWriter.write(response, code instanceof ErrorCode ec ? ec : ErrorCode.AUTH_TOKEN_INVALID);
    }
}
