package com.capstone.inspection.auth.dto;

// refreshToken을 보내면 해당 토큰을 폐기, deviceToken을 보내면 그 기기의 푸시 토큰도 해제 (둘 다 선택)
public record LogoutRequest(String refreshToken, String deviceToken) {
}
