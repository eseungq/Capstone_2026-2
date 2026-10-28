package com.capstone.inspection.domain.inspection;

public enum RecommendedAction {
    AUTO_PASS, // 정책 조건 충족, 최종 PASS로 저장
    REVIEW     // 작업자 확인 필요
}
