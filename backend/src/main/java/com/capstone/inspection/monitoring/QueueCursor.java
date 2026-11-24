package com.capstone.inspection.monitoring;

import com.capstone.inspection.common.error.BusinessException;
import com.capstone.inspection.common.error.ErrorCode;

import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.util.Base64;

// 확인 필요 목록 커서: 마지막 항목의 (receivedAt, id). 앱에는 불투명 문자열로 전달
//   RECEIVED는 기존 형식 그대로, PRIORITY는 앞에 그룹("P0|" 우선, "P1|" 나머지)을 붙임
//   다른 정렬의 커서는 400 (계약 6.4)
record QueueCursor(Integer group, LocalDateTime receivedAt, String id) {

    private static final String GROUP_PREFIX = "P";

    String encode() {
        String raw = (group == null ? "" : GROUP_PREFIX + group + "|") + receivedAt + "|" + id;
        return Base64.getUrlEncoder().withoutPadding().encodeToString(raw.getBytes(StandardCharsets.UTF_8));
    }

    static QueueCursor decode(String cursor, QueueSort sort) {
        try {
            String raw = new String(Base64.getUrlDecoder().decode(cursor), StandardCharsets.UTF_8);
            Integer group = null;
            if (raw.startsWith(GROUP_PREFIX)) {
                int end = raw.indexOf('|');
                group = Integer.parseInt(raw.substring(GROUP_PREFIX.length(), end));
                if (group != 0 && group != 1) {
                    throw new IllegalArgumentException();
                }
                raw = raw.substring(end + 1);
            }
            if ((group != null) != (sort == QueueSort.PRIORITY)) {
                throw new IllegalArgumentException();
            }
            int sep = raw.indexOf('|');
            if (sep < 0 || sep == raw.length() - 1) {
                throw new IllegalArgumentException();
            }
            return new QueueCursor(group, LocalDateTime.parse(raw.substring(0, sep)), raw.substring(sep + 1));
        } catch (RuntimeException e) {
            throw new BusinessException(ErrorCode.INVALID_PARAMETER, "cursor 값이 올바르지 않습니다.");
        }
    }
}
