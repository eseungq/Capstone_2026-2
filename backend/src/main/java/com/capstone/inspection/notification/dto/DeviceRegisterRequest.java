package com.capstone.inspection.notification.dto;

import com.capstone.inspection.domain.user.DevicePlatform;
import jakarta.validation.constraints.NotNull;

// POST /notifications/devices 요청 (계약 v4 8.3). token 형식은 서비스에서 검사해 INVALID_DEVICE_TOKEN으로 응답
public record DeviceRegisterRequest(String token, @NotNull DevicePlatform platform) {
}
