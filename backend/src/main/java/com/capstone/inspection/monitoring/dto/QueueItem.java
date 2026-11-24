package com.capstone.inspection.monitoring.dto;

import com.capstone.inspection.domain.inspection.PredictedQuality;
import com.capstone.inspection.domain.inspection.ReviewReason;
import com.capstone.inspection.inspection.DisplayState;

import java.time.OffsetDateTime;

// 확인 필요 목록 항목 (계약 v4 6.4)
public record QueueItem(String inspectionId,
                        String inspectionNo,
                        String partCode,
                        DisplayState displayState,        // REVIEW_PENDING 또는 FAILED
                        PredictedQuality predictedQuality,
                        ReviewReason reviewReason,
                        Double calibratedDefectProbability, // 보정 불량 확률, 없으면 null [제안 11/23]
                        Double passThresholdApplied,      // 판정 당시 기준치, 없으면 null [제안 11/23]
                        String errorCode,                 // FAILED일 때만
                        OffsetDateTime receivedAt,
                        String thumbnailUrl) {
}
