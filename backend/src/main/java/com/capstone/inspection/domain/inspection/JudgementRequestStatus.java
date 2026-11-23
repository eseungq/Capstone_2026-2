package com.capstone.inspection.domain.inspection;

// 판정 확인 요청 상태 (계약 6.12): 대기 · 현재 판정 유지 · 요청한 판정으로 정정
public enum JudgementRequestStatus {
    OPEN,
    KEPT,
    CORRECTED
}
