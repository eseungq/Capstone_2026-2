package com.capstone.inspection.inspection.dto;

import com.capstone.inspection.domain.inspection.Judgement;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

// POST /inspections/{id}/recheck 요청 (계약 6.11)
public record RecheckRequest(@NotNull Judgement result,
                             @Size(max = 200) String comment) { // 선택, 최대 200자
}
