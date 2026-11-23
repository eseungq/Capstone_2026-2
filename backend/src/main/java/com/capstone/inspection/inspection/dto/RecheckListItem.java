package com.capstone.inspection.inspection.dto;

import com.capstone.inspection.common.time.Times;
import com.capstone.inspection.domain.inspection.AutoPassRecheck;
import com.capstone.inspection.domain.inspection.Inspection;
import com.capstone.inspection.domain.inspection.Judgement;
import com.capstone.inspection.domain.inspection.RecheckStratum;

import java.time.OffsetDateTime;

// GET /rechecks 항목 (계약 6.11)
public record RecheckListItem(String inspectionId,
                              String inspectionNo,
                              String partCode,
                              OffsetDateTime receivedAt,
                              RecheckStratum stratum,
                              OffsetDateTime sampledAt,
                              Judgement result,
                              OffsetDateTime recheckedAt,
                              String acknowledgedBy,          // 관리자 확인함 (해결 완료 아님)
                              OffsetDateTime acknowledgedAt) {

    public static RecheckListItem of(AutoPassRecheck r) {
        Inspection i = r.getInspection();
        return new RecheckListItem(i.getId(), i.getInspectionNo(), i.getPart().getPartCode(),
                Times.toOffset(i.getReceivedAt()), r.getStratum(), Times.toOffset(r.getSampledAt()), r.getResult(),
                Times.toOffset(r.getRecheckedAt()),
                r.getAcknowledgedBy() == null ? null : r.getAcknowledgedBy().getLoginId(),
                Times.toOffset(r.getAcknowledgedAt()));
    }
}
