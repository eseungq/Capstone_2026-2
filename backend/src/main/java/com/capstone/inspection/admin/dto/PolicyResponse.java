package com.capstone.inspection.admin.dto;

import com.fasterxml.jackson.databind.JsonNode;

import java.time.OffsetDateTime;

// 정책 1건 (계약 v4 6.9). basedOnPolicyId는 조정으로 만든 버전의 직전 정책 ID
public record PolicyResponse(String policyId,
                             String policyVersion,
                             String partCode,
                             String modelVersion,
                             String calibratorVersion,
                             Double passThreshold,
                             Double validatedMin,
                             Double validatedMax,
                             boolean ready,
                             boolean active,
                             JsonNode metrics,
                             String basedOnPolicyId,
                             OffsetDateTime createdAt,
                             OffsetDateTime activatedAt) {
}
