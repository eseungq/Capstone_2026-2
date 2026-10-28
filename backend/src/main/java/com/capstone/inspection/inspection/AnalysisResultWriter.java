package com.capstone.inspection.inspection;

import com.capstone.inspection.ai.AiClient;
import com.capstone.inspection.ai.AiJson;
import com.capstone.inspection.ai.AiPredictResponse;
import com.capstone.inspection.domain.inspection.GradcamStatus;
import com.capstone.inspection.domain.inspection.ImageStorage;
import com.capstone.inspection.domain.inspection.ImageStorageRepository;
import com.capstone.inspection.domain.inspection.ImageType;
import com.capstone.inspection.domain.inspection.Inspection;
import com.capstone.inspection.domain.inspection.InspectionRepository;
import com.capstone.inspection.domain.inspection.InspectionStatus;
import com.capstone.inspection.domain.inspection.PredictedQuality;
import com.capstone.inspection.domain.model.AutomationPolicyRepository;
import com.capstone.inspection.inspection.ImageInspector.ImageInfo;
import com.capstone.inspection.storage.StorageService;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import lombok.RequiredArgsConstructor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;
import java.time.format.DateTimeFormatter;

// 분석 단계별 DB 기록. AI 호출은 트랜잭션 밖에서 하고, 시작·완료·실패 기록만 짧은 트랜잭션으로 처리
@Component
@RequiredArgsConstructor
public class AnalysisResultWriter {

    private static final Logger log = LoggerFactory.getLogger(AnalysisResultWriter.class);
    private static final DateTimeFormatter DATE_PATH = DateTimeFormatter.ofPattern("yyyy/MM/dd");

    private final InspectionRepository inspectionRepository;
    private final ImageStorageRepository imageRepository;
    private final AutomationPolicyRepository policyRepository;
    private final StorageService storageService;
    private final AiJson aiJson;

    // AI 요청에 필요한 값
    public record Started(String inspectionId, String partCode, String modelVersion, String modelId,
                          String originalImageId, String traceId) {
    }

    // 결과 요약 (알림 판단용)
    public record Outcome(String inspectionId, String inspectionNo, String partCode, InspectionStatus status,
                          boolean reviewRequired) {
    }

    // RECEIVED → ANALYZING. 이미 처리된 건이면 null (중복 실행 방지)
    @Transactional
    public Started start(String inspectionId) {
        Inspection i = inspectionRepository.findDetailById(inspectionId).orElse(null);
        if (i == null || i.getStatus() != InspectionStatus.RECEIVED) {
            return null;
        }
        ImageStorage original = imageRepository.findByInspectionIdAndImageType(inspectionId, ImageType.ORIGINAL)
                .orElse(null);
        if (original == null) {
            i.fail("INTERNAL_SERVER_ERROR", "원본 이미지 기록 없음");
            return null;
        }
        i.startAnalysis();
        return new Started(i.getId(), i.getPart().getPartCode(), i.getModel().getModelVersion(),
                i.getModel().getId(), original.getId(), i.getTraceId());
    }

    // 검증된 AI 응답 → 정책 적용 → COMPLETED
    @Transactional
    public Outcome complete(Started started, AiClient.Result result, PredictedQuality quality) {
        Inspection i = inspectionRepository.findDetailById(started.inspectionId()).orElseThrow();
        if (i.getStatus() != InspectionStatus.ANALYZING) {
            log.warn("ANALYZING이 아닌 검사 결과 무시: {} {}", i.getId(), i.getStatus());
            return null;
        }
        AiPredictResponse r = result.response();
        i.recordAiResult(quality, r.rawDefectProbability(), r.calibratedDefectProbability(),
                r.calibratorVersion(), r.inferenceTimeMs(), stripImageData(result.rawBody()));

        GradcamStatus gradcamStatus = quality == PredictedQuality.DEFECT
                ? saveGradcam(i, r.gradcam())
                : GradcamStatus.NOT_REQUIRED; // GOOD 예측은 생성하지 않음. 응답에 있어도 저장하지 않음

        PolicyEvaluator.Decision d = PolicyEvaluator.evaluate(quality, r.calibratedDefectProbability(),
                r.calibratorVersion(), policyRepository.findReadyActiveByModelId(started.modelId()));
        i.complete(d.action(), d.reviewReason(), d.policy(), d.passThreshold(), gradcamStatus);
        log.info("분석 완료 {} {} quality={} action={} reason={} gradcam={}", i.getInspectionNo(), i.getId(),
                quality, d.action(), d.reviewReason(), gradcamStatus);
        return new Outcome(i.getId(), i.getInspectionNo(), i.getPart().getPartCode(), i.getStatus(),
                i.getFinalJudgement() == null);
    }

    // FAILED 확정 (이후 변경하지 않음)
    @Transactional
    public Outcome fail(String inspectionId, String errorCode, String detail) {
        Inspection i = inspectionRepository.findDetailById(inspectionId).orElse(null);
        if (i == null || i.isFinished()) {
            return null;
        }
        i.fail(errorCode, detail);
        log.warn("분석 실패 {} {} {} {}", i.getInspectionNo(), i.getId(), errorCode, detail);
        return new Outcome(i.getId(), i.getInspectionNo(), i.getPart().getPartCode(), i.getStatus(), false);
    }

    // DEFECT 예측의 Grad-CAM: 응답 해석(GradcamParser) 후 GENERATED만 저장. 저장 실패도 검사는 실패시키지 않고 FAILED로 기록
    private GradcamStatus saveGradcam(Inspection i, AiPredictResponse.Gradcam g) {
        GradcamParser.Parsed parsed = GradcamParser.parse(i.getId(), g);
        if (parsed.status() != GradcamStatus.GENERATED) {
            return parsed.status();
        }
        ImageInfo info = parsed.info();
        try {
            String key = "gradcam/" + LocalDate.now().format(DATE_PATH) + "/" + i.getId() + "." + info.extension();
            storageService.save(key, parsed.bytes());
            imageRepository.save(new ImageStorage(i, ImageType.GRADCAM, key, info.contentType(), parsed.bytes().length,
                    info.width(), info.height(), Hashes.sha256(parsed.bytes())));
            return GradcamStatus.GENERATED;
        } catch (Exception e) {
            log.warn("Grad-CAM 저장 실패 {}: {}", i.getId(), e.getMessage());
            return GradcamStatus.FAILED;
        }
    }

    // ai_response_json에는 이미지 데이터를 빼고 저장 (계약 7.2)
    private String stripImageData(String rawBody) {
        try {
            JsonNode root = aiJson.mapper().readTree(rawBody);
            JsonNode gradcam = root.path("gradcam");
            if (gradcam instanceof ObjectNode g && g.has("imageBase64")) {
                g.put("imageBase64", "<omitted " + g.path("imageBase64").asText("").length() + " chars>");
            }
            return aiJson.mapper().writeValueAsString(root);
        } catch (Exception e) {
            return null;
        }
    }
}
