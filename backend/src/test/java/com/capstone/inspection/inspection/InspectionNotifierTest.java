package com.capstone.inspection.inspection;

import com.capstone.inspection.domain.inspection.InspectionStatus;
import com.capstone.inspection.domain.inspection.RecommendedAction;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.time.LocalDateTime;

import static org.assertj.core.api.Assertions.assertThat;

// 알림 대상 (계약 8.2): REVIEW → REVIEW_REQUIRED, FAILED → ANALYSIS_FAILED, AUTO_FAIL → AUTO_FAILED, AUTO_PASS는 발송 안 함
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
    @DisplayName("AUTO_FAIL은 REVIEW와 구분되는 자동 불량 알림, AUTO_PASS는 알림 없음")
    void autoFailNotifiedSeparately() {
        var notice = InspectionNotifier.noticeFor(outcome(InspectionStatus.COMPLETED, RecommendedAction.AUTO_FAIL));
        assertThat(notice.type()).isEqualTo("AUTO_FAILED");
        assertThat(notice.title()).isEqualTo("자동 불량");
        assertThat(notice.inspectionId()).isEqualTo("id");
        assertThat(InspectionNotifier.noticeFor(outcome(InspectionStatus.COMPLETED, RecommendedAction.AUTO_PASS))).isNull();
    }

    @Test
    @DisplayName("AUTO_FAILED 원격 푸시는 autoFailed를 켰을 때만, 나머지 알림은 기존대로 enabled만 봄")
    void autoFailedRemotePushOffByDefault() {
        assertThat(InspectionNotifier.sendsRemotely("AUTO_FAILED", true, false)).isFalse();
        assertThat(InspectionNotifier.sendsRemotely("AUTO_FAILED", true, true)).isTrue();
        assertThat(InspectionNotifier.sendsRemotely("AUTO_FAILED", false, true)).isFalse();
        assertThat(InspectionNotifier.sendsRemotely("REVIEW_REQUIRED", true, false)).isTrue();
        assertThat(InspectionNotifier.sendsRemotely("REVIEW_REQUIRED", false, false)).isFalse();
    }
}
