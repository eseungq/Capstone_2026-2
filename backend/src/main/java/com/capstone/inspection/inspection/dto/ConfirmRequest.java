package com.capstone.inspection.inspection.dto;

import com.capstone.inspection.domain.inspection.Judgement;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Size;

import java.time.OffsetDateTime;

// POST /inspections/{id}/confirm 요청 (계약 v4 6.7). 화면 체류 시간 3개는 선택, 셋 다 보내거나 생략 (6.11)
public record ConfirmRequest(@NotNull Judgement finalJudgement,
                             @Size(max = 200) String comment,       // 선택, 최대 200자
                             @PositiveOrZero @Max(ScreenTimings.MAX_DWELL_MS) Long screenDwellMs,
                             OffsetDateTime firstOpenedAt,
                             @Min(1) @Max(ScreenTimings.MAX_OPEN_COUNT) Integer openCount) {
}
