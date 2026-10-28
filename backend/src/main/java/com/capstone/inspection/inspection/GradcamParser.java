package com.capstone.inspection.inspection;

import com.capstone.inspection.ai.AiPredictResponse;
import com.capstone.inspection.domain.inspection.GradcamStatus;
import com.capstone.inspection.inspection.ImageInspector.ImageInfo;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Base64;

// DEFECT 예측의 Grad-CAM 응답 해석 (합의 10/28). 판정에는 쓰지 않으며, 문제가 있어도 검사는 실패시키지 않음
//   gradcam null                                  → FAILED (생성 오류)
//   status NO_ACTIVATION                          → NO_ACTIVATION (0맵·상수맵, 이미지 없음. mapType은 ai_response_json에만)
//   status GENERATED 또는 없음 + 유효한 png·jpeg   → GENERATED (이미지 저장)
//   그 외 (알 수 없는 status, targetClass ≠ DEFECT, format이 png·jpeg 아님, 디코딩 실패, 선언과 실제 형식 불일치) → FAILED
public final class GradcamParser {

    private static final Logger log = LoggerFactory.getLogger(GradcamParser.class);

    private GradcamParser() {
    }

    // GENERATED일 때만 bytes·info 값이 있음
    public record Parsed(GradcamStatus status, byte[] bytes, ImageInfo info) {

        static Parsed of(GradcamStatus status) {
            return new Parsed(status, null, null);
        }
    }

    public static Parsed parse(String inspectionId, AiPredictResponse.Gradcam g) {
        if (g == null || !"DEFECT".equals(g.targetClass())) {
            return Parsed.of(GradcamStatus.FAILED);
        }
        if ("NO_ACTIVATION".equals(g.status())) {
            log.info("Grad-CAM 강조 반응 없음 {} mapType={}", inspectionId, g.mapType());
            return Parsed.of(GradcamStatus.NO_ACTIVATION);
        }
        if (g.status() != null && !"GENERATED".equals(g.status())) {
            log.warn("알 수 없는 Grad-CAM status {}: {}", inspectionId, g.status());
            return Parsed.of(GradcamStatus.FAILED);
        }
        String declared = declaredContentType(g.format());
        if (declared == null || g.imageBase64() == null) {
            log.warn("Grad-CAM format·이미지 없음 또는 미지원 {}: format={}", inspectionId, g.format());
            return Parsed.of(GradcamStatus.FAILED);
        }
        byte[] bytes;
        try {
            bytes = Base64.getDecoder().decode(g.imageBase64());
        } catch (IllegalArgumentException e) {
            log.warn("Grad-CAM base64 디코딩 실패 {}", inspectionId);
            return Parsed.of(GradcamStatus.FAILED);
        }
        ImageInfo info = ImageInspector.inspect(bytes);
        if (info == null || !declared.equals(info.contentType())) {
            log.warn("Grad-CAM 형식 불일치 {}: 선언 {}, 실제 {}", inspectionId, g.format(),
                    info == null ? "읽을 수 없음" : info.contentType());
            return Parsed.of(GradcamStatus.FAILED);
        }
        return new Parsed(GradcamStatus.GENERATED, bytes, info);
    }

    // 선언된 format → content type. png·jpeg(jpg) 허용, 대소문자 무시
    private static String declaredContentType(String format) {
        if (format == null) {
            return null;
        }
        return switch (format.toLowerCase()) {
            case "png" -> "image/png";
            case "jpeg", "jpg" -> "image/jpeg";
            default -> null;
        };
    }
}
