package com.capstone.inspection.ai;

// POST {AI}/internal/v1/predict 요청 (계약 v4 7.1)
public record AiPredictRequest(String inspectionId,
                               String partCode,
                               String requestedModelVersion,
                               String imageUrl) {          // 만료되는 이미지 접근 주소
}
