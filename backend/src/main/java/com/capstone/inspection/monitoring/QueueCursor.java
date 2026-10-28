package com.capstone.inspection.monitoring;

import com.capstone.inspection.common.error.BusinessException;
import com.capstone.inspection.common.error.ErrorCode;

import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.util.Base64;

// 확인 필요 목록 커서: 마지막 항목의 (receivedAt, id). 앱에는 불투명 문자열로 전달
record QueueCursor(LocalDateTime receivedAt, String id) {

    String encode() {
        String raw = receivedAt + "|" + id;
        return Base64.getUrlEncoder().withoutPadding().encodeToString(raw.getBytes(StandardCharsets.UTF_8));
    }

    static QueueCursor decode(String cursor) {
        try {
            String raw = new String(Base64.getUrlDecoder().decode(cursor), StandardCharsets.UTF_8);
            int sep = raw.indexOf('|');
            if (sep < 0 || sep == raw.length() - 1) {
                throw new IllegalArgumentException();
            }
            return new QueueCursor(LocalDateTime.parse(raw.substring(0, sep)), raw.substring(sep + 1));
        } catch (RuntimeException e) {
            throw new BusinessException(ErrorCode.INVALID_PARAMETER, "cursor 값이 올바르지 않습니다.");
        }
    }
}
