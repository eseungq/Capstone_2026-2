package com.capstone.inspection.inspection;

import com.capstone.inspection.ai.AiCallException;
import com.capstone.inspection.ai.AiClient;
import com.capstone.inspection.ai.AiPredictRequest;
import com.capstone.inspection.ai.AiResponseValidator;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.common.trace.TraceIdFilter;
import com.capstone.inspection.domain.inspection.PredictedQuality;
import com.capstone.inspection.storage.ImageUrlSigner;
import lombok.RequiredArgsConstructor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.stereotype.Service;

// 검사 1건 분석 (분석 스레드 풀에서 실행): 시작 기록 → AI 호출 → 응답 검증 → 정책 적용·저장 → 알림
@Service
@RequiredArgsConstructor
public class InspectionAnalysisService {

    private static final Logger log = LoggerFactory.getLogger(InspectionAnalysisService.class);

    private final AnalysisResultWriter writer;
    private final AiClient aiClient;
    private final ImageUrlSigner signer;
    private final InspectionNotifier notifier;

    public void analyze(String inspectionId) {
        AnalysisResultWriter.Started started = writer.start(inspectionId);
        if (started == null) {
            return;
        }
        if (started.traceId() != null) {
            MDC.put(TraceIdFilter.MDC_KEY, started.traceId()); // 접수 요청과 같은 traceId로 로그 연결
        }
        AnalysisResultWriter.Outcome outcome;
        try {
            String imageUrl = signer.sign(started.originalImageId()).url();
            AiClient.Result result = aiClient.predict(new AiPredictRequest(
                    started.inspectionId(), started.partCode(), started.modelVersion(), imageUrl));
            PredictedQuality quality = AiResponseValidator.validate(
                    result.response(), started.inspectionId(), started.modelVersion());
            outcome = writer.complete(started, result, quality);
        } catch (AiCallException e) {
            outcome = writer.fail(inspectionId, e.getErrorCode().name(), e.getMessage());
        } catch (Exception e) {
            log.error("분석 처리 중 예상하지 못한 오류 {}", inspectionId, e);
            outcome = writer.fail(inspectionId, ErrorCode.INTERNAL_SERVER_ERROR.name(), e.toString());
        }
        notifier.notifyIfNeeded(outcome);
    }
}
