package com.capstone.inspection.auth.dto;

// refreshToken을 보내면 해당 토큰을 폐기. 기기 푸시 토큰 해제는 알림 기능 구현 시 추가
public record LogoutRequest(String refreshToken) {
}
