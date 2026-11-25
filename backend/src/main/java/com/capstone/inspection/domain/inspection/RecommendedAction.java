package com.capstone.inspection.domain.inspection;

public enum RecommendedAction {
    AUTO_PASS, // 정책 조건 충족, 최종 PASS로 저장
    AUTO_FAIL, // 자동 불량을 켠 정책에서 불량 기준 이상인 DEFECT 예측, 최종 FAIL로 저장 (계약 4.1)
    REVIEW     // 작업자 확인 필요
}
