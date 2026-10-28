package com.capstone.inspection.domain.inspection;

public enum InspectionStatus {
    RECEIVED,  // 접수 완료, 분석 대기 (v4 추가)
    ANALYZING, // AI 분석 중
    COMPLETED, // 분석 완료 (AUTO_PASS 또는 REVIEW)
    FAILED     // 분석 실패 (AI 오류·타임아웃·응답 계약 위반). 이후 변경하지 않음
}
