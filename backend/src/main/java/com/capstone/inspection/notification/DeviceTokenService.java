package com.capstone.inspection.notification;

import com.capstone.inspection.common.error.BusinessException;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.domain.user.DevicePlatform;
import com.capstone.inspection.domain.user.DeviceTokenRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.UUID;
import java.util.regex.Pattern;

// 푸시 기기 토큰 등록·해제 (계약 v4 8장)
@Service
@RequiredArgsConstructor
public class DeviceTokenService {

    private static final Pattern EXPO_TOKEN = Pattern.compile("Expo(nent)?PushToken\\[[^\\[\\]\\s]+]");
    private static final int MAX_TOKEN_LENGTH = 200;

    private final DeviceTokenRepository repository;

    @Transactional
    public void register(String userId, String token, DevicePlatform platform) {
        if (token == null || token.length() > MAX_TOKEN_LENGTH || !EXPO_TOKEN.matcher(token).matches()) {
            throw new BusinessException(ErrorCode.INVALID_DEVICE_TOKEN);
        }
        repository.upsert(UUID.randomUUID().toString(), userId, token, platform.name(), LocalDateTime.now());
    }

    // 본인 토큰만 해제. 없거나 다른 사람 토큰이면 아무 일도 하지 않음
    @Transactional
    public void unregister(String userId, String token) {
        if (token != null && !token.isBlank()) {
            repository.deleteOwn(token, userId);
        }
    }
}
