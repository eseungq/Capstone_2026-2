package com.capstone.inspection.inspection;

import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.domain.inspection.Inspection;
import com.capstone.inspection.domain.inspection.InspectionRepository;
import com.capstone.inspection.domain.inspection.InspectionStatus;
import lombok.RequiredArgsConstructor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

import java.util.List;

// 서버 재시작 시 정리 (계약 v4 5장)
//   RECEIVED: 분석 전이었으므로 다시 처리
//   ANALYZING: AI 결과를 알 수 없으므로 FAILED(INTERNAL_SERVER_ERROR)로 확정 → 재검사로 안내
@Component
@RequiredArgsConstructor
public class InspectionRecovery {

    private static final Logger log = LoggerFactory.getLogger(InspectionRecovery.class);

    private final InspectionRepository inspectionRepository;
    private final AnalysisResultWriter writer;
    private final AnalysisDispatcher dispatcher;

    @EventListener(ApplicationReadyEvent.class)
    public void recover() {
        List<Inspection> analyzing = inspectionRepository.findByStatus(InspectionStatus.ANALYZING);
        for (Inspection i : analyzing) {
            writer.fail(i.getId(), ErrorCode.INTERNAL_SERVER_ERROR.name(), "서버 재시작으로 분석 결과 확인 불가");
        }
        List<Inspection> received = inspectionRepository.findByStatus(InspectionStatus.RECEIVED);
        received.forEach(i -> dispatcher.dispatch(i.getId()));
        if (!analyzing.isEmpty() || !received.isEmpty()) {
            log.info("재시작 정리: ANALYZING {}건 FAILED 처리, RECEIVED {}건 재처리", analyzing.size(), received.size());
        }
    }
}
