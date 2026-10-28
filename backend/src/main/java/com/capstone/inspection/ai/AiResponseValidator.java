package com.capstone.inspection.ai;

import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.domain.inspection.PredictedQuality;

// AI 응답 계약 검증 (계약 v4 7.2). 위반이면 AI_RESPONSE_INVALID로 FAILED 처리
// Grad-CAM 형식 문제는 검사 실패가 아니라 gradcamStatus=FAILED로 처리하므로 여기서 검사하지 않음
public final class AiResponseValidator {

    private static final double DEFECT_CUTOFF = 0.5; // AI 분류 기준. passThreshold와 별개 (합의 10/15)

    private AiResponseValidator() {
    }

    public static PredictedQuality validate(AiPredictResponse r, String expectedInspectionId,
                                            String requestedModelVersion) {
        if (r == null) {
            throw invalid("응답 본문 없음");
        }
        if (!expectedInspectionId.equals(r.inspectionId())) {
            throw invalid("inspectionId 불일치: " + r.inspectionId());
        }
        if (!requestedModelVersion.equals(r.modelVersion())) {
            throw invalid("modelVersion 불일치: 요청 " + requestedModelVersion + ", 응답 " + r.modelVersion());
        }
        PredictedQuality quality = parseQuality(r.predictedQuality());
        double raw = requireProbability("rawDefectProbability", r.rawDefectProbability());
        if ((raw >= DEFECT_CUTOFF) != (quality == PredictedQuality.DEFECT)) {
            throw invalid("predictedQuality와 rawDefectProbability 불일치: " + quality + ", " + raw);
        }
        Double calibrated = r.calibratedDefectProbability();
        boolean hasCalibratorVersion = r.calibratorVersion() != null && !r.calibratorVersion().isBlank();
        if (calibrated != null) {
            requireProbability("calibratedDefectProbability", calibrated);
            if (!hasCalibratorVersion) {
                throw invalid("보정 확률이 있는데 calibratorVersion 없음");
            }
        } else if (hasCalibratorVersion) {
            throw invalid("보정 확률이 null인데 calibratorVersion 있음");
        }
        if (r.imageWidth() == null || r.imageWidth() <= 0 || r.imageHeight() == null || r.imageHeight() <= 0) {
            throw invalid("imageWidth·imageHeight 누락 또는 0 이하");
        }
        if (r.inferenceTimeMs() == null || r.inferenceTimeMs() < 0) {
            throw invalid("inferenceTimeMs 누락 또는 음수");
        }
        return quality;
    }

    private static PredictedQuality parseQuality(String value) {
        if (value == null) {
            throw invalid("predictedQuality 누락");
        }
        try {
            return PredictedQuality.valueOf(value);
        } catch (IllegalArgumentException e) {
            throw invalid("predictedQuality 값 오류: " + value);
        }
    }

    private static double requireProbability(String name, Double value) {
        if (value == null || !Double.isFinite(value) || value < 0.0 || value > 1.0) {
            throw invalid(name + " 누락 또는 0~1 범위 밖: " + value);
        }
        return value;
    }

    private static AiCallException invalid(String detail) {
        return new AiCallException(ErrorCode.AI_RESPONSE_INVALID, detail, false);
    }
}
