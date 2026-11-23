package com.capstone.inspection.common.time;

import com.capstone.inspection.common.error.BusinessException;
import com.capstone.inspection.common.error.ErrorCode;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeParseException;

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

    // 저장된 시각(LocalDateTime.now(), 서버 기본 시간대)의 KST 날짜. 서버 시간대가 서울이 아니어도 KST로 셈 (계약 6.13)
    public static LocalDate kstDate(LocalDateTime stored) {
        return stored.atZone(ZoneId.systemDefault()).withZoneSameInstant(ZONE).toLocalDate();
    }

    // KST 날짜 0시를 저장 시각(서버 기본 시간대)으로. 날짜 범위 조회의 경계
    public static LocalDateTime kstStartOfDay(LocalDate date) {
        return date.atStartOfDay(ZONE).withZoneSameInstant(ZoneId.systemDefault()).toLocalDateTime();
    }

    // 요청 파라미터의 KST 날짜 (yyyy-MM-dd). 비어 있으면 null, 형식이 틀리면 400 INVALID_PARAMETER
    public static LocalDate parseDateParam(String name, String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        try {
            return LocalDate.parse(value.trim());
        } catch (DateTimeParseException e) {
            throw new BusinessException(ErrorCode.INVALID_PARAMETER, name + "은(는) 2026-11-23 형식이어야 합니다.");
        }
    }

    // 요청 파라미터의 시각. 비어 있으면 null, 형식이 틀리면 400 INVALID_PARAMETER
    public static LocalDateTime parseParam(String name, String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        try {
            return toLocal(OffsetDateTime.parse(value.trim()));
        } catch (DateTimeParseException e) {
            throw new BusinessException(ErrorCode.INVALID_PARAMETER, name + "은(는) 2026-10-16T09:00:00+09:00 형식이어야 합니다.");
        }
    }
}
