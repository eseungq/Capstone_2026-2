package com.capstone.inspection.auth.security;

import com.capstone.inspection.common.error.ErrorCode;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.stereotype.Component;

import java.io.IOException;

// 로그인은 했지만 역할 권한이 없는 경우 → 403 (예: WORKER가 관리자 API 호출)
@Component
@RequiredArgsConstructor
public class RestAccessDeniedHandler implements AccessDeniedHandler {

    private final SecurityErrorWriter errorWriter;

    @Override
    public void handle(HttpServletRequest request, HttpServletResponse response,
                       AccessDeniedException e) throws IOException {
        errorWriter.write(response, ErrorCode.ACCESS_DENIED);
    }
}
