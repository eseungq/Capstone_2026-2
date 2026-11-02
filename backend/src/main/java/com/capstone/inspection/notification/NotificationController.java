package com.capstone.inspection.notification;

import com.capstone.inspection.auth.security.AuthUser;
import com.capstone.inspection.notification.dto.DeviceRegisterRequest;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

// WORKER·ADMIN만 호출 가능 (SecurityConfig)
@Tag(name = "알림", description = "푸시 기기 토큰 등록·해제")
@RestController
@RequestMapping("/api/v1/notifications/devices")
@RequiredArgsConstructor
public class NotificationController {

    private final DeviceTokenService deviceTokenService;

    @Operation(summary = "기기 토큰 등록", description = "Expo 푸시 토큰. 같은 토큰이 있으면 사용자·플랫폼·최근 확인 시각을 갱신")
    @PostMapping
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void register(@AuthenticationPrincipal AuthUser user, @Valid @RequestBody DeviceRegisterRequest request) {
        deviceTokenService.register(user.userId(), request.token(), request.platform());
    }

    @Operation(summary = "기기 토큰 해제", description = "본인 토큰만 해제, 없으면 204. 토큰의 대괄호는 경로에 넣을 때 인코딩")
    @DeleteMapping("/{token}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void unregister(@AuthenticationPrincipal AuthUser user, @PathVariable String token) {
        deviceTokenService.unregister(user.userId(), token);
    }
}
