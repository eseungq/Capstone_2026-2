package com.capstone.inspection.inspection.dto;

import com.capstone.inspection.domain.inspection.Judgement;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.PositiveOrZero;
import jakarta.validation.constraints.Size;

import java.time.OffsetDateTime;
import java.util.List;

// POST /inspections/confirm-batch 요청 (계약 v4 6.7.1). FAIL만 허용, 1~50건, 중복 ID는 서비스에서 거절
public record ConfirmBatchRequest(@NotNull Judgement finalJudgement,
                                  @Size(max = 200) String comment,          // 모든 건에 같이 저장 (선택)
                                  @NotNull @Size(min = 1, max = ConfirmBatchRequest.MAX_ITEMS) List<@NotNull @Valid Item> items) {

    public static final int MAX_ITEMS = 50;

    // 건별 화면 체류 시간은 6.7과 같은 규칙 (선택, 셋 다 보내거나 생략)
    public record Item(@NotBlank String inspectionId,
                       @PositiveOrZero @Max(ScreenTimings.MAX_DWELL_MS) Long screenDwellMs,
                       OffsetDateTime firstOpenedAt,
                       @Min(1) @Max(ScreenTimings.MAX_OPEN_COUNT) Integer openCount) {
    }
}
