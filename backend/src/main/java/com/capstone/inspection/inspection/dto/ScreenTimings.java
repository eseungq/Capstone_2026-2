package com.capstone.inspection.inspection.dto;

import com.capstone.inspection.common.error.BusinessException;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.common.time.Times;
import com.capstone.inspection.domain.inspection.ScreenTiming;

import java.time.OffsetDateTime;
import java.time.temporal.ChronoUnit;

// 요청의 화면 체류 시간 필드 → ScreenTiming (계약 6.11 "화면 체류 시간"). REVIEW 확인·재확인 제출이 같은 규칙
public final class ScreenTimings {

    public static final long MAX_DWELL_MS = 86_400_000L; // 24시간
    public static final long MAX_OPEN_COUNT = 1_000;

    private ScreenTimings() {
    }

    // 셋 다 없으면 null, 일부만 있으면 400. 범위는 요청 DTO의 Bean Validation이 먼저 확인
    public static ScreenTiming of(Long screenDwellMs, OffsetDateTime firstOpenedAt, Integer openCount) {
        if (screenDwellMs == null && firstOpenedAt == null && openCount == null) {
            return null;
        }
        if (screenDwellMs == null || firstOpenedAt == null || openCount == null) {
            throw new BusinessException(ErrorCode.INVALID_PARAMETER,
                    "screenDwellMs·firstOpenedAt·openCount는 셋 다 보내거나 모두 생략해야 합니다.");
        }
        // DB DATETIME(6)과 같은 정밀도
        return new ScreenTiming(screenDwellMs, Times.toLocal(firstOpenedAt).truncatedTo(ChronoUnit.MICROS), openCount);
    }
}
