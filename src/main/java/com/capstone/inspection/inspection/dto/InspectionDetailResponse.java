package com.capstone.inspection.inspection.dto;

import com.capstone.inspection.domain.inspection.GradcamStatus;
import com.capstone.inspection.domain.inspection.InspectionStatus;
import com.capstone.inspection.domain.inspection.JudgedBy;
import com.capstone.inspection.domain.inspection.Judgement;
import com.capstone.inspection.domain.inspection.PredictedQuality;
import com.capstone.inspection.domain.inspection.RecommendedAction;
import com.capstone.inspection.domain.inspection.ReviewReason;
import com.capstone.inspection.inspection.DisplayState;

import java.time.OffsetDateTime;

// GET /inspections/{id} 응답 (계약 v4 6.5). AI 결과·정책 결과·작업자 판정·이미지를 블록으로 분리
public record InspectionDetailResponse(String inspectionId,
                                       String inspectionNo,
                                       String partCode,
                                       String lineCode,
                                       InspectionStatus status,
                                       DisplayState displayState,
                                       OffsetDateTime receivedAt,
                                       OffsetDateTime completedAt,
                                       String retryOf,
                                       Ai ai,                 // FAILED·분석 중이면 null
                                       Policy policy,         // FAILED·분석 중이면 null
                                       JudgementBlock judgement,
                                       Images images,
                                       Error error) {         // FAILED일 때만

    public record Ai(String modelVersion, String calibratorVersion, PredictedQuality predictedQuality,
                     Double rawDefectProbability, Double calibratedDefectProbability, Integer inferenceTimeMs) {
    }

    public record Policy(boolean automationPolicyReady, String policyVersion, Double passThreshold,
                         RecommendedAction recommendedAction, ReviewReason reviewReason) {
    }

    public record JudgementBlock(Judgement finalJudgement, JudgedBy judgedBy, String confirmedBy,
                                 OffsetDateTime confirmedAt) {
    }

    public record Image(String url, int width, int height) {
    }

    public record Images(Image original, Image gradcam, GradcamStatus gradcamStatus, OffsetDateTime urlExpiresAt) {
    }

    public record Error(String code, String message, boolean retryable) {
    }
}
