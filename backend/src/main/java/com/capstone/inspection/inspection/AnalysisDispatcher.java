package com.capstone.inspection.inspection;

import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.config.AsyncConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

// 접수 커밋 후 분석을 스레드 풀에 넘김. 접수 응답(202)은 분석을 기다리지 않음 (계약 v4 5장)
@Component
public class AnalysisDispatcher {

    private static final Logger log = LoggerFactory.getLogger(AnalysisDispatcher.class);

    private final ThreadPoolTaskExecutor executor;
    private final InspectionAnalysisService analysisService;
    private final AnalysisResultWriter writer;
    private final InspectionNotifier notifier;

    public AnalysisDispatcher(@Qualifier(AsyncConfig.ANALYSIS_EXECUTOR) ThreadPoolTaskExecutor executor,
                              InspectionAnalysisService analysisService,
                              AnalysisResultWriter writer,
                              InspectionNotifier notifier) {
        this.executor = executor;
        this.analysisService = analysisService;
        this.writer = writer;
        this.notifier = notifier;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onReceived(InspectionReceivedEvent event) {
        dispatch(event.inspectionId());
    }

    public void dispatch(String inspectionId) {
        try {
            executor.execute(() -> analysisService.analyze(inspectionId));
        } catch (TaskRejectedException e) {
            // 대기열이 가득 찬 경우: RECEIVED로 방치하지 않고 FAILED로 확정해 재검사로 안내
            log.error("분석 대기열 초과로 접수 처리 불가 {}", inspectionId);
            notifier.notifyIfNeeded(writer.fail(inspectionId, ErrorCode.INTERNAL_SERVER_ERROR.name(), "분석 대기열 초과"));
        }
    }
}
