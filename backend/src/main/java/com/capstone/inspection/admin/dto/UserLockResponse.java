package com.capstone.inspection.admin.dto;

// POST /admin/users/{loginId}/unlock 응답
public record UserLockResponse(String loginId, boolean locked, int failedLoginCount) {
}
