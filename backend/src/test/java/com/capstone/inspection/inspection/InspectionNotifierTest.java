package com.capstone.inspection.inspection;

import com.capstone.inspection.domain.inspection.InspectionStatus;
import com.capstone.inspection.domain.inspection.RecommendedAction;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.time.LocalDateTime;

import static org.assertj.core.api.Assertions.assertThat;

// 알림 대상 (계약 8.2): REVIEW → REVIEW_REQUIRED, FAILED → ANALYSIS_FAILED, AUTO_PASS·AUTO_FAIL은 발송 안 함
class InspectionNotifierTest {

    private static AnalysisResultWriter.Outcome outcome(InspectionStatus status, RecommendedAction action) {
        return new AnalysisResultWriter.Outcome("id", "INS-000001", "DOOR", status, action, LocalDateTime.now());
    }

    @Test
    @DisplayName("REVIEW만 확인 필요 알림, FAILED는 오류 알림")
    void reviewAndFailed() {
        assertThat(InspectionNotifier.noticeFor(outcome(InspectionStatus.COMPLETED, RecommendedAction.REVIEW)).type())
                .isEqualTo("REVIEW_REQUIRED");
        assertThat(InspectionNotifier.noticeFor(outcome(InspectionStatus.FAILED, null)).type())
                .isEqualTo("ANALYSIS_FAILED");
    }

    @Test
    @DisplayName("AUTO_PASS·AUTO_FAIL은 알림 없음")
    void systemJudgementsNotNotified() {
        assertThat(InspectionNotifier.noticeFor(outcome(InspectionStatus.COMPLETED, RecommendedAction.AUTO_PASS))).isNull();
        assertThat(InspectionNotifier.noticeFor(outcome(InspectionStatus.COMPLETED, RecommendedAction.AUTO_FAIL))).isNull();
    }
}
