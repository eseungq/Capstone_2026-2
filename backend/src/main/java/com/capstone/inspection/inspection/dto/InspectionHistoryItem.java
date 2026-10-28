package com.capstone.inspection.inspection.dto;

import com.capstone.inspection.domain.inspection.JudgedBy;
import com.capstone.inspection.domain.inspection.Judgement;
import com.capstone.inspection.domain.inspection.PredictedQuality;
import com.capstone.inspection.domain.inspection.ReviewReason;
import com.capstone.inspection.inspection.DisplayState;

import java.time.OffsetDateTime;

// GET /inspections 목록 항목 (계약 v4 6.6: 6.4 항목 형식 + 판정 정보)
public record InspectionHistoryItem(String inspectionId,
                                    String inspectionNo,
                                    String partCode,
                                    DisplayState displayState,
                                    PredictedQuality predictedQuality,
                                    ReviewReason reviewReason,
                                    String errorCode,            // FAILED일 때만
                                    OffsetDateTime receivedAt,
                                    String thumbnailUrl,         // 원본 서명 주소 (만료됨)
                                    Judgement finalJudgement,
                                    JudgedBy judgedBy,
                                    OffsetDateTime confirmedAt) { // 작업자 확인 시각 (REVIEW_DONE일 때만)
}
