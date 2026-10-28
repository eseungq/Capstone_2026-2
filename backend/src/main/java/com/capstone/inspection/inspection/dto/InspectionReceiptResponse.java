package com.capstone.inspection.inspection.dto;

import com.capstone.inspection.common.time.Times;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.capstone.inspection.domain.inspection.Inspection;
import com.capstone.inspection.domain.inspection.InspectionStatus;

import java.time.OffsetDateTime;

// POST /inspections 응답 (계약 v4 6.2). 202: 새 접수, 200: 같은 Idempotency-Key 재전송
@JsonInclude(JsonInclude.Include.NON_NULL) // retryOf는 재검사일 때만
public record InspectionReceiptResponse(String inspectionId,
                                        String inspectionNo,
                                        String partCode,
                                        InspectionStatus status,
                                        OffsetDateTime receivedAt,
                                        String retryOf) {

    public static InspectionReceiptResponse of(Inspection i) {
        return new InspectionReceiptResponse(i.getId(), i.getInspectionNo(), i.getPart().getPartCode(),
                i.getStatus(), Times.toOffset(i.getReceivedAt()), i.getRetryOfInspectionId());
    }
}
