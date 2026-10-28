package com.capstone.inspection.domain.inspection;

// Grad-CAM 상태 (계약 v4 6.5). 판정에는 사용하지 않음
public enum GradcamStatus {
    GENERATED,    // DEFECT 예측, 생성 성공
    NOT_REQUIRED, // GOOD 예측이라 생성하지 않음
    FAILED,       // DEFECT 예측인데 생성 실패 (검사는 COMPLETED 유지)
    NO_ACTIVATION // DEFECT 예측, 계산은 성공했지만 위치별 강조 반응 없음(0맵·상수맵). 이미지 없음 (합의 10/28)
}
