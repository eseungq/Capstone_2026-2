package com.capstone.inspection.common.time;

import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;

// API 시각은 오프셋 포함 ISO-8601 (계약 v4 2장, 예: 2026-10-15T14:03:21+09:00). DB는 서울 시각으로 저장
public final class Times {

    public static final ZoneId ZONE = ZoneId.of("Asia/Seoul");

    private Times() {
    }

    public static OffsetDateTime toOffset(LocalDateTime value) {
        return value == null ? null : value.atZone(ZONE).toOffsetDateTime();
    }

    public static LocalDateTime toLocal(OffsetDateTime value) {
        return value == null ? null : value.atZoneSameInstant(ZONE).toLocalDateTime();
    }
}
