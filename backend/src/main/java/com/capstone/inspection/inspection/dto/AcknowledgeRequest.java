package com.capstone.inspection.inspection.dto;

import jakarta.validation.constraints.Size;

// POST /admin/rechecks/{inspectionId}/acknowledge 요청 (계약 6.11). 본문 생략 가능
public record AcknowledgeRequest(@Size(max = 200) String note) { // 선택, 최대 200자
}
