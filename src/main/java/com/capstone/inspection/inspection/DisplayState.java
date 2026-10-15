package com.capstone.inspection.inspection;

import com.capstone.inspection.domain.inspection.Inspection;
import com.capstone.inspection.domain.inspection.RecommendedAction;

// 앱 표시용 파생 상태 (계약 v4 3.2). 앱은 이 값만 보고 화면을 정해도 됨
public enum DisplayState {
    ANALYZING,       // RECEIVED·ANALYZING
    AUTO_PASS,       // COMPLETED + AUTO_PASS
    REVIEW_PENDING,  // COMPLETED + REVIEW, 작업자 확인 전
    REVIEW_DONE,     // COMPLETED + REVIEW, 작업자 확인 완료
    FAILED;

    public static DisplayState of(Inspection i) {
        return switch (i.getStatus()) {
            case RECEIVED, ANALYZING -> ANALYZING;
            case FAILED -> FAILED;
            case COMPLETED -> i.getRecommendedAction() == RecommendedAction.AUTO_PASS ? AUTO_PASS
                    : (i.getFinalJudgement() == null ? REVIEW_PENDING : REVIEW_DONE);
        };
    }
}
