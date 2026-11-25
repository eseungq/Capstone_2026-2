package com.capstone.inspection.inspection.dto;

import com.capstone.inspection.domain.inspection.JudgementRequestStatus;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

// POST /admin/judgement-requests/{requestId}/resolve 요청 (계약 6.12)
public record JudgementResolveRequest(@NotNull Decision decision,
                                      @NotBlank @Size(max = 500) String note) { // 필수 1~500자

    // KEEP: 현재 판정 유지, CORRECT: 요청한 판정으로 정정
    public enum Decision {
        KEEP(JudgementRequestStatus.KEPT),
        CORRECT(JudgementRequestStatus.CORRECTED);

        private final JudgementRequestStatus status;

        Decision(JudgementRequestStatus status) {
            this.status = status;
        }

        public JudgementRequestStatus status() {
            return status;
        }
    }
}
