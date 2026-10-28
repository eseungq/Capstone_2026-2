package com.capstone.inspection.auth.dto;

import com.capstone.inspection.domain.user.Role;

// 로그인·재발급 응답
public record TokenResponse(String accessToken,
                            String refreshToken,
                            String tokenType,           // 항상 "Bearer"
                            long expiresIn,             // Access Token 유효 시간(초)
                            UserInfo user) {

    public record UserInfo(String userId, String loginId, Role role) {
    }
}
