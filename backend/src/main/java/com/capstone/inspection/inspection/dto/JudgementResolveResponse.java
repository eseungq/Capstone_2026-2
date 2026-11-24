package com.capstone.inspection.inspection.dto;

// 처리 응답 (계약 6.12): 처리된 요청 1건 + 검사의 correction (정정된 적이 없으면 null)
public record JudgementResolveResponse(JudgementRequestResponse request, CorrectionBlock correction) {
}
