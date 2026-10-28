package com.capstone.inspection.auth.security;

import com.capstone.inspection.domain.user.Role;

// 인증된 요청의 사용자 정보 (Access Token에서 꺼낸 값, 컨트롤러에서 @AuthenticationPrincipal로 받음)
public record AuthUser(String userId, String loginId, Role role) {
}
