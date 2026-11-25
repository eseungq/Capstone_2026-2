package com.capstone.inspection.admin.dto;

import jakarta.validation.constraints.NotNull;

// POST /admin/policies/{id}/fail-threshold 요청: 자동 불량 기준 등록·조정 (계약 6.9, 4.1)
public record FailThresholdRequest(@NotNull Double failThreshold,
                                   @NotNull Double failValidatedMin,
                                   @NotNull Double failValidatedMax) {
}
