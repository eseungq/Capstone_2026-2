package com.capstone.inspection.admin.dto;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

// POST /admin/policies 요청: AI 검증 자료 등록 (계약 v4 6.9). ready는 받지 않고 규칙으로 결정
// policyVersion은 조정 버전 접미어(-t번호)가 컬럼 길이(100)를 넘지 않게 90자까지
public record PolicyCreateRequest(@NotBlank @Size(max = 100) String modelVersion,
                                  @Size(max = 100) String calibratorVersion,
                                  @NotBlank @Size(max = 90) String policyVersion,
                                  @NotNull Double passThreshold,
                                  @NotNull Double validatedMin,
                                  @NotNull Double validatedMax,
                                  JsonNode metrics) {
}
