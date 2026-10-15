package com.capstone.inspection.ai;

// AI 정상 응답 (계약 v4 7.2). 값 검증은 AiResponseValidator에서 수행하므로 전부 nullable 래퍼 타입
public record AiPredictResponse(String inspectionId,
                                String modelVersion,
                                String predictedQuality,           // GOOD / DEFECT
                                Double rawDefectProbability,       // 보정 전 softmax 불량 점수
                                Double calibratedDefectProbability,// 보정기 미준비면 null
                                String calibratorVersion,          // 보정값이 있으면 필수
                                Integer imageWidth,
                                Integer imageHeight,
                                Gradcam gradcam,                   // DEFECT 예측만, 실패·GOOD이면 null
                                Integer inferenceTimeMs) {

    public record Gradcam(String targetClass, String format, String imageBase64) {
    }
}
