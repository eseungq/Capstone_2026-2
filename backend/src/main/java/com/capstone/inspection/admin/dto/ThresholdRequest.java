package com.capstone.inspection.admin.dto;

import jakarta.validation.constraints.NotNull;

// POST /admin/policies/{id}/threshold 요청 (계약 v4 6.9)
public record ThresholdRequest(@NotNull Double passThreshold) {
}
