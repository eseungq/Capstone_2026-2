package com.capstone.inspection.inspection;

import com.capstone.inspection.common.time.Times;
import com.capstone.inspection.config.AppProperties;
import com.capstone.inspection.config.AsyncConfig;
import com.capstone.inspection.domain.inspection.InspectionStatus;
import com.capstone.inspection.notification.PushService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;

// 알림 발송 지점 (계약 v4 8장). REVIEW → REVIEW_REQUIRED, FAILED → ANALYSIS_FAILED, AUTO_PASS는 발송 안 함
// 결과 저장 커밋 후 호출됨. 발송은 전용 스레드에서 해서 분석 스레드를 잡지 않고, 실패해도 분석 결과에 영향 없음
@Component
public class InspectionNotifier {

    private static final Logger log = LoggerFactory.getLogger(InspectionNotifier.class);

    private final boolean pushEnabled;
    private final PushService pushService;
    private final ThreadPoolTaskExecutor executor;

    public InspectionNotifier(AppProperties props, PushService pushService,
                              @Qualifier(AsyncConfig.PUSH_EXECUTOR) ThreadPoolTaskExecutor executor) {
        this.pushEnabled = props.push().enabled();
        this.pushService = pushService;
        this.executor = executor;
    }

    public void notifyIfNeeded(AnalysisResultWriter.Outcome outcome) {
        PushService.Notice notice = noticeFor(outcome);
        if (notice == null) {
            return;
        }
        if (!pushEnabled) {
            log.info("[알림 로그] {} {} {} {}", notice.type(), notice.inspectionNo(), notice.partCode(),
                    notice.inspectionId());
            return;
        }
        try {
            executor.execute(() -> {
                try {
                    pushService.send(notice);
                } catch (RuntimeException e) {
                    log.warn("푸시 처리 실패 {}: {}", notice.inspectionNo(), e.getMessage());
                }
            });
        } catch (TaskRejectedException e) {
            log.warn("푸시 대기열 초과로 발송 생략 {} {}", notice.type(), notice.inspectionNo());
        }
    }

    // 알림 대상이 아니면 null
    static PushService.Notice noticeFor(AnalysisResultWriter.Outcome outcome) {
        if (outcome == null) {
            return null;
        }
        if (outcome.status() == InspectionStatus.FAILED) {
            return notice("ANALYSIS_FAILED", outcome, "분석 실패", "다시 검사가 필요합니다.");
        }
        if (outcome.status() == InspectionStatus.COMPLETED && outcome.reviewRequired()) {
            return notice("REVIEW_REQUIRED", outcome, "확인 필요", "작업자 확인이 필요합니다.");
        }
        return null;
    }

    private static PushService.Notice notice(String type, AnalysisResultWriter.Outcome o, String title, String message) {
        return new PushService.Notice(type, o.inspectionId(), o.inspectionNo(), o.partCode(),
                Times.toOffset(o.occurredAt()).toString(), title,
                o.partCode() + " " + o.inspectionNo() + " " + message);
    }
}
