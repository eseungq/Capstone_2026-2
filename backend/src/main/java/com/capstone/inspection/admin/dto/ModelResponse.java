package com.capstone.inspection.admin.dto;

// GET /admin/models 응답의 모델 1개 (계약 v4 6.9)
// loadable: AI 서버 확인 결과. 확인할 수 없거나 확인을 끈 경우 null
public record ModelResponse(String modelVersion,
                            String partCode,
                            String calibratorVersion,
                            boolean active,
                            Boolean loadable) {
}
