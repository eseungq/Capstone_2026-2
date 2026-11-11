package com.capstone.inspection.inspection.dto;

import com.capstone.inspection.common.time.Times;
import com.capstone.inspection.domain.inspection.Inspection;
import com.capstone.inspection.domain.inspection.InspectionSource;
import com.capstone.inspection.domain.inspection.InspectionStatus;
import com.capstone.inspection.domain.inspection.ReviewReason;
import com.capstone.inspection.inspection.DisplayState;

import java.time.OffsetDateTime;

// POST /inspections/{id}/manual 응답 (계약 v4 6.10). 새 수동 판정 검사와 원래 FAILED 연결
public record ManualConversionResponse(String inspectionId,
                                       String inspectionNo,
                                       String partCode,
                                       InspectionSource source,       // MANUAL
                                       InspectionStatus status,       // COMPLETED
                                       DisplayState displayState,     // REVIEW_PENDING
                                       ReviewReason reviewReason,     // AI_UNAVAILABLE
                                       OffsetDateTime receivedAt,
                                       String manualOf,               // 원래 FAILED 검사 ID
                                       String manualOfInspectionNo,
                                       String manualOfErrorCode) {    // 원래 FAILED의 AI 실패 사유

    public static ManualConversionResponse of(Inspection manual, Inspection failed) {
        return new ManualConversionResponse(manual.getId(), manual.getInspectionNo(), manual.getPart().getPartCode(),
                manual.getSource(), manual.getStatus(), DisplayState.of(manual), manual.getReviewReason(),
                Times.toOffset(manual.getReceivedAt()), failed.getId(), failed.getInspectionNo(),
                com.capstone.inspection.common.error.ErrorCode.fromStored(failed.getErrorCode()).name());
    }
}
