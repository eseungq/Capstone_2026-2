package com.capstone.inspection.inspection;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

// 알림 발송 지점 (계약 v4 8장). REVIEW → REVIEW_REQUIRED, FAILED → ANALYSIS_FAILED, AUTO_PASS는 발송 안 함
// Expo 푸시 연동은 다음 단계. 지금은 로그만 남기고, 앱은 5초 폴링으로 확인
@Component
public class InspectionNotifier {

    private static final Logger log = LoggerFactory.getLogger(InspectionNotifier.class);

    public void notifyIfNeeded(AnalysisResultWriter.Outcome outcome) {
        if (outcome == null) {
            return;
        }
        switch (outcome.status()) {
            case FAILED -> log.info("[알림 예정] ANALYSIS_FAILED {} {} {}", outcome.inspectionNo(),
                    outcome.partCode(), outcome.inspectionId());
            case COMPLETED -> {
                if (outcome.reviewRequired()) {
                    log.info("[알림 예정] REVIEW_REQUIRED {} {} {}", outcome.inspectionNo(),
                            outcome.partCode(), outcome.inspectionId());
                }
            }
            default -> {
            }
        }
    }
}
