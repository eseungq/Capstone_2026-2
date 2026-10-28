package com.capstone.inspection.auth;

import com.capstone.inspection.auth.dto.LoginRequest;
import com.capstone.inspection.auth.dto.LogoutRequest;
import com.capstone.inspection.auth.dto.RefreshRequest;
import com.capstone.inspection.auth.dto.TokenResponse;
import com.capstone.inspection.auth.security.AuthUser;
import com.capstone.inspection.common.api.ApiResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@Tag(name = "인증", description = "로그인·토큰 재발급·로그아웃")
@RestController
@RequestMapping("/api/v1/auth")
@RequiredArgsConstructor
public class AuthController {

    private final AuthService authService;

    @Operation(summary = "로그인", description = "WORKER·ADMIN·DEVICE 공통. 실패가 기준 횟수에 도달하면 잠금(423)")
    @PostMapping("/login")
    public ApiResponse<TokenResponse> login(@Valid @RequestBody LoginRequest request) {
        return ApiResponse.of(authService.login(request.loginId(), request.password()));
    }

    @Operation(summary = "토큰 재발급", description = "사용한 Refresh Token은 폐기되고 새 토큰 쌍을 발급")
    @PostMapping("/refresh")
    public ApiResponse<TokenResponse> refresh(@Valid @RequestBody RefreshRequest request) {
        return ApiResponse.of(authService.refresh(request.refreshToken()));
    }

    @Operation(summary = "로그아웃", description = "보낸 Refresh Token을 폐기")
    @PostMapping("/logout")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void logout(@AuthenticationPrincipal AuthUser user,
                       @RequestBody(required = false) LogoutRequest request) {
        authService.logout(user.userId(), request == null ? null : request.refreshToken());
    }
}
