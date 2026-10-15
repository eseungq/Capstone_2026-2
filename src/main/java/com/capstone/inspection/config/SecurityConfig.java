package com.capstone.inspection.config;

import com.capstone.inspection.auth.security.JwtAuthenticationFilter;
import com.capstone.inspection.auth.security.JwtTokenProvider;
import com.capstone.inspection.auth.security.RestAccessDeniedHandler;
import com.capstone.inspection.auth.security.RestAuthenticationEntryPoint;
import lombok.RequiredArgsConstructor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

// 역할별 접근 규칙 (계약 v4 6.1). 앱 메뉴 숨김과 별개로 서버에서 검사
@Configuration
@EnableWebSecurity
@RequiredArgsConstructor
public class SecurityConfig {

    private static final String API = "/api/v1";

    private final JwtTokenProvider tokenProvider;
    private final RestAuthenticationEntryPoint authenticationEntryPoint;
    private final RestAccessDeniedHandler accessDeniedHandler;

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
                .csrf(AbstractHttpConfigurer::disable)            // 쿠키 세션을 쓰지 않는 토큰 방식
                .formLogin(AbstractHttpConfigurer::disable)
                .httpBasic(AbstractHttpConfigurer::disable)
                .logout(AbstractHttpConfigurer::disable)          // /auth/logout은 컨트롤러에서 처리
                .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .exceptionHandling(e -> e
                        .authenticationEntryPoint(authenticationEntryPoint)
                        .accessDeniedHandler(accessDeniedHandler))
                .authorizeHttpRequests(auth -> auth
                        // 공개
                        .requestMatchers(HttpMethod.POST, API + "/auth/login", API + "/auth/refresh").permitAll()
                        .requestMatchers("/swagger-ui.html", "/swagger-ui/**", "/v3/api-docs/**", "/error").permitAll()
                        // 이미지 접근 주소는 서명·만료 시간으로 보호 (AI 서버·앱이 토큰 없이 읽음)
                        .requestMatchers(HttpMethod.GET, API + "/images/**").permitAll()

                        // 검사 접수: 사진 입력 프로그램(DEVICE), 시연용 ADMIN
                        .requestMatchers(HttpMethod.POST, API + "/inspections").hasAnyRole("DEVICE", "ADMIN")
                        // 작업자 확인: WORKER만 (ADMIN은 조회만)
                        .requestMatchers(HttpMethod.POST, API + "/inspections/*/confirm").hasRole("WORKER")
                        // FAILED 재검사: WORKER·ADMIN
                        .requestMatchers(HttpMethod.POST, API + "/inspections/*/retry").hasAnyRole("WORKER", "ADMIN")
                        // 조회: WORKER·ADMIN
                        .requestMatchers(HttpMethod.GET, API + "/inspections", API + "/inspections/**",
                                API + "/parts", API + "/monitoring/**").hasAnyRole("WORKER", "ADMIN")
                        .requestMatchers(API + "/notifications/**").hasAnyRole("WORKER", "ADMIN")
                        // 관리자
                        .requestMatchers(API + "/admin/**").hasRole("ADMIN")
                        // 그 외는 로그인만 확인 (로그아웃 등)
                        .anyRequest().authenticated())
                .addFilterBefore(new JwtAuthenticationFilter(tokenProvider), UsernamePasswordAuthenticationFilter.class);
        return http.build();
    }

    @Bean
    public PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }
}
