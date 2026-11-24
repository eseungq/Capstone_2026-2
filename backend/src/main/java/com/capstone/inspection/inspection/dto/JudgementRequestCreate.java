package com.capstone.inspection.inspection.dto;

import com.capstone.inspection.domain.inspection.Judgement;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

// POST /inspections/{id}/judgement-requests 요청 (계약 6.12). 근거 사진은 다음 단계 (TBD-19)
public record JudgementRequestCreate(@NotNull Judgement claimedJudgement, // 현재 판정과 다른 값
                                     @Size(max = 100) String area,       // 선택, 최대 100자
                                     @NotBlank @Size(max = 500) String reason) { // 필수 1~500자
}
