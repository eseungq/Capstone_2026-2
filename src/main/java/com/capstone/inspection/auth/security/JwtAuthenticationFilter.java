package com.capstone.inspection.auth.security;

import com.capstone.inspection.common.error.BusinessException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpHeaders;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.List;

// Authorization: Bearer <accessToken> 를 읽어 인증 정보를 등록
// 토큰이 잘못돼도 여기서 응답하지 않고 오류 코드만 남김 → 인증이 필요한 경로면 RestAuthenticationEntryPoint가 401 응답
@RequiredArgsConstructor
public class JwtAuthenticationFilter extends OncePerRequestFilter {

    public static final String AUTH_ERROR_ATTR = "authErrorCode";
    private static final String BEARER = "Bearer ";

    private final JwtTokenProvider tokenProvider;

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        String header = request.getHeader(HttpHeaders.AUTHORIZATION);
        if (header != null && header.startsWith(BEARER)) {
            try {
                AuthUser user = tokenProvider.parse(header.substring(BEARER.length()).trim());
                var authority = new SimpleGrantedAuthority("ROLE_" + user.role().name());
                var authentication = new UsernamePasswordAuthenticationToken(user, null, List.of(authority));
                SecurityContextHolder.getContext().setAuthentication(authentication);
            } catch (BusinessException e) {
                request.setAttribute(AUTH_ERROR_ATTR, e.getErrorCode());
            }
        }
        chain.doFilter(request, response);
    }
}
