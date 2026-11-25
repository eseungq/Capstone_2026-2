package com.capstone.inspection.admin.dto;

import jakarta.validation.constraints.NotNull;

// POST /admin/policies/{id}/auto-fail 요청: 자동 불량 켜고 끄기 (계약 6.9, 4.1)
public record AutoFailRequest(@NotNull Boolean enabled) {
}
