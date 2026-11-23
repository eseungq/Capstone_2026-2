package com.capstone.inspection.inspection;

// 이력 필터: AI 예측과 작업자 판정이 엇갈린 REVIEW 확인 완료 건 (추가 검토·재학습 후보 선별용)
// 수동 판정은 AI 예측이 없고 AUTO_PASS·AUTO_FAIL은 사람이 보지 않으므로 대상이 아님
public enum ReviewMismatch {
    ANY,           // 아래 둘 다
    DEFECT_PASSED, // AI DEFECT 예측 → 작업자 PASS
    GOOD_FAILED    // AI GOOD 예측 → 작업자 FAIL
}
