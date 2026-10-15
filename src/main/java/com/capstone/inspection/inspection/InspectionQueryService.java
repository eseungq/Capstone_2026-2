package com.capstone.inspection.inspection;

import com.capstone.inspection.common.error.BusinessException;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.common.time.Times;
import com.capstone.inspection.domain.inspection.ImageStorage;
import com.capstone.inspection.domain.inspection.ImageStorageRepository;
import com.capstone.inspection.domain.inspection.ImageType;
import com.capstone.inspection.domain.inspection.Inspection;
import com.capstone.inspection.domain.inspection.InspectionRepository;
import com.capstone.inspection.domain.inspection.InspectionStatus;
import com.capstone.inspection.domain.inspection.WorkerConfirmation;
import com.capstone.inspection.domain.inspection.WorkerConfirmationRepository;
import com.capstone.inspection.inspection.dto.InspectionDetailResponse;
import com.capstone.inspection.inspection.dto.InspectionDetailResponse.Ai;
import com.capstone.inspection.inspection.dto.InspectionDetailResponse.Image;
import com.capstone.inspection.inspection.dto.InspectionDetailResponse.Images;
import com.capstone.inspection.inspection.dto.InspectionDetailResponse.JudgementBlock;
import com.capstone.inspection.inspection.dto.InspectionDetailResponse.Policy;
import com.capstone.inspection.storage.ImageUrlSigner;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.List;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class InspectionQueryService {

    private final InspectionRepository inspectionRepository;
    private final ImageStorageRepository imageRepository;
    private final WorkerConfirmationRepository confirmationRepository;
    private final ImageUrlSigner signer;

    public InspectionDetailResponse getDetail(String inspectionId) {
        Inspection i = inspectionRepository.findDetailById(inspectionId)
                .orElseThrow(() -> new BusinessException(ErrorCode.INSPECTION_NOT_FOUND));

        boolean completed = i.getStatus() == InspectionStatus.COMPLETED;
        Ai ai = completed ? new Ai(i.getModel().getModelVersion(), i.getCalibratorVersion(), i.getPredictedQuality(),
                i.getRawDefectProbability(), i.getCalibratedDefectProbability(), i.getInferenceTimeMs()) : null;
        Policy policy = completed ? new Policy(i.isAutomationPolicyReady(),
                i.getPolicy() != null ? i.getPolicy().getPolicyVersion() : null, i.getPassThresholdApplied(),
                i.getRecommendedAction(), i.getReviewReason()) : null;

        WorkerConfirmation confirmation = confirmationRepository.findByInspectionIdWithWorker(i.getId()).orElse(null);
        JudgementBlock judgement = new JudgementBlock(i.getFinalJudgement(), i.getJudgedBy(),
                confirmation != null ? confirmation.getWorker().getLoginId() : null,
                confirmation != null ? Times.toOffset(confirmation.getConfirmedAt()) : null);

        InspectionDetailResponse.Error error = null;
        if (i.getStatus() == InspectionStatus.FAILED) {
            ErrorCode code = parseCode(i.getErrorCode());
            // 앱에는 오류 코드와 기본 문구만 전달 (AI 상세는 error_detail에만 보관)
            error = new InspectionDetailResponse.Error(code.name(), code.getDefaultMessage(), true);
        }

        return new InspectionDetailResponse(i.getId(), i.getInspectionNo(), i.getPart().getPartCode(),
                i.getLineCode(), i.getStatus(), DisplayState.of(i), Times.toOffset(i.getReceivedAt()),
                Times.toOffset(i.getCompletedAt()), i.getRetryOfInspectionId(), ai, policy, judgement,
                images(i), error);
    }

    private Images images(Inspection i) {
        List<ImageStorage> stored = imageRepository.findByInspectionId(i.getId());
        Image original = null;
        Image gradcam = null;
        Instant expiresAt = null;
        for (ImageStorage s : stored) {
            ImageUrlSigner.SignedUrl signed = signer.sign(s.getId());
            expiresAt = signed.expiresAt();
            Image image = new Image(signed.url(), s.getWidth(), s.getHeight());
            if (s.getImageType() == ImageType.ORIGINAL) {
                original = image;
            } else {
                gradcam = image;
            }
        }
        OffsetDateTime urlExpiresAt = expiresAt == null ? null : expiresAt.atZone(Times.ZONE).toOffsetDateTime();
        return new Images(original, gradcam, i.getGradcamStatus(), urlExpiresAt);
    }

    private static ErrorCode parseCode(String name) {
        try {
            return name == null ? ErrorCode.INTERNAL_SERVER_ERROR : ErrorCode.valueOf(name);
        } catch (IllegalArgumentException e) {
            return ErrorCode.INTERNAL_SERVER_ERROR;
        }
    }
}
