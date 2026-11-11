package com.capstone.inspection.domain.inspection;

// 검사가 만들어진 경로
public enum InspectionSource {
    DEVICE, // 사진 입력 프로그램
    ADMIN,  // 관리자 시연 접수
    RETRY,  // FAILED 재검사로 생성
    MANUAL  // FAILED를 AI 없이 작업자 판정으로 전환 (V6)
}
