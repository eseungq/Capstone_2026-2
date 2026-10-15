package com.capstone.inspection.domain.inspection;

// REVIEW 사유 (계약 v4 4장). 여러 사유가 겹치면 선언 순서(우선순위)가 가장 앞선 하나만 기록
public enum ReviewReason {
    DEFECT_PREDICTED,        // AI가 불량으로 예측
    NO_ACTIVE_POLICY,        // 부품·모델·보정기 버전에 맞는 ready·active 정책 없음
    CALIBRATION_UNAVAILABLE, // 보정 불량 확률이 null
    ABOVE_THRESHOLD          // 보정 불량 확률 > passThreshold
}
