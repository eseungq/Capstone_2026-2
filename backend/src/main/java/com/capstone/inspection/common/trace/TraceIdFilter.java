package com.capstone.inspection.common.trace;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.UUID;

// 요청마다 traceId를 발급해 로그(MDC)와 응답 헤더에 넣음
// 앱에서 오류가 나면 traceId로 서버 로그를 찾을 수 있음
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class TraceIdFilter extends OncePerRequestFilter {

    public static final String MDC_KEY = "traceId";
    public static final String HEADER = "X-Trace-Id";

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        String traceId = UUID.randomUUID().toString().replace("-", "").substring(0, 16); // 16자리 추적 ID
        MDC.put(MDC_KEY, traceId);
        response.setHeader(HEADER, traceId);
        try {
            chain.doFilter(request, response);
        } finally {
            MDC.remove(MDC_KEY); // 스레드 재사용 시 값이 섞이지 않도록 제거
        }
    }
}
