package com.capstone.inspection.inspection.dto;

import com.capstone.inspection.domain.inspection.Judgement;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

// POST /inspections/{id}/confirm 요청 (계약 v4 6.7)
public record ConfirmRequest(@NotNull Judgement finalJudgement,
                             @Size(max = 200) String comment) { // 선택, 최대 200자
}
