package com.capstone.inspection.inspection;

import com.capstone.inspection.common.api.PageResponse;
import com.capstone.inspection.common.error.BusinessException;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.common.time.Times;
import com.capstone.inspection.domain.inspection.ImageStorage;
import com.capstone.inspection.domain.inspection.ImageStorageRepository;
import com.capstone.inspection.domain.inspection.ImageType;
import com.capstone.inspection.domain.inspection.Inspection;
import com.capstone.inspection.domain.inspection.InspectionRepository;
import com.capstone.inspection.domain.inspection.InspectionStatus;
import com.capstone.inspection.domain.inspection.JudgedBy;
import com.capstone.inspection.domain.inspection.WorkerConfirmation;
import com.capstone.inspection.domain.inspection.WorkerConfirmationRepository;
import com.capstone.inspection.domain.part.Part;
import com.capstone.inspection.domain.part.PartRepository;
import com.capstone.inspection.inspection.dto.InspectionDetailResponse;
import com.capstone.inspection.inspection.dto.InspectionHistoryItem;
import com.capstone.inspection.inspection.dto.InspectionDetailResponse.Ai;
import com.capstone.inspection.inspection.dto.InspectionDetailResponse.Image;
import com.capstone.inspection.inspection.dto.InspectionDetailResponse.Images;
import com.capstone.inspection.inspection.dto.InspectionDetailResponse.JudgementBlock;
import com.capstone.inspection.inspection.dto.InspectionDetailResponse.Policy;
import com.capstone.inspection.storage.ImageUrlSigner;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class InspectionQueryService {

    public static final int MAX_PAGE_SIZE = 100;
    // 이력 정렬: 접수 시각 최신순 (같은 시각이면 ID로 고정)
    private static final Sort HISTORY_SORT = Sort.by(Sort.Order.desc("receivedAt"), Sort.Order.desc("id"));

    private final InspectionRepository inspectionRepository;
    private final PartRepository partRepository;
    private final InspectionThumbnails thumbnails;
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
            ErrorCode code = ErrorCode.fromStored(i.getErrorCode());
            // 앱에는 오류 코드와 기본 문구만 전달 (AI 상세는 error_detail에만 보관)
            error = new InspectionDetailResponse.Error(code.name(), code.getDefaultMessage(), true);
        }

        return new InspectionDetailResponse(i.getId(), i.getInspectionNo(), i.getPart().getPartCode(),
                i.getLineCode(), i.getStatus(), DisplayState.of(i), Times.toOffset(i.getReceivedAt()),
                Times.toOffset(i.getCompletedAt()), i.getRetryOfInspectionId(), ai, policy, judgement,
                images(i), error);
    }

    // 검사 이력 (계약 v4 6.6). 작업자도 전체 검사 조회. 기간은 receivedAt 기준 from ≤ receivedAt < to
    public PageResponse<InspectionHistoryItem> search(String partCode, DisplayState displayState,
                                                      LocalDateTime from, LocalDateTime to, int page, int size) {
        if (page < 0 || size < 1 || size > MAX_PAGE_SIZE) {
            throw new BusinessException(ErrorCode.INVALID_PARAMETER, "page는 0 이상, size는 1~" + MAX_PAGE_SIZE + "이어야 합니다.");
        }
        if (from != null && to != null && !from.isBefore(to)) {
            throw new BusinessException(ErrorCode.INVALID_PARAMETER, "from은 to보다 앞선 시각이어야 합니다.");
        }
        Specification<Inspection> spec = InspectionSpecs.fetchPart();
        if (partCode != null && !partCode.isBlank()) {
            Part part = partRepository.findByPartCode(partCode.trim())
                    .orElseThrow(() -> new BusinessException(ErrorCode.INVALID_PART_CODE));
            spec = spec.and(InspectionSpecs.partId(part.getId()));
        }
        if (displayState != null) {
            spec = spec.and(InspectionSpecs.displayState(displayState));
        }
        if (from != null) {
            spec = spec.and(InspectionSpecs.receivedFrom(from));
        }
        if (to != null) {
            spec = spec.and(InspectionSpecs.receivedBefore(to));
        }
        Page<Inspection> result = inspectionRepository.findAll(spec, PageRequest.of(page, size, HISTORY_SORT));
        return PageResponse.of(result, this::toHistoryItems);
    }

    private List<InspectionHistoryItem> toHistoryItems(List<Inspection> inspections) {
        Map<String, String> urls = thumbnails.urlsFor(inspections);
        List<String> reviewedIds = inspections.stream()
                .filter(i -> i.getJudgedBy() == JudgedBy.WORKER)
                .map(Inspection::getId).toList();
        Map<String, LocalDateTime> confirmedAt = reviewedIds.isEmpty() ? Map.of()
                : confirmationRepository.findByInspectionIds(reviewedIds).stream()
                .collect(Collectors.toMap(c -> c.getInspection().getId(), WorkerConfirmation::getConfirmedAt));
        return inspections.stream().map(i -> new InspectionHistoryItem(i.getId(), i.getInspectionNo(),
                i.getPart().getPartCode(), DisplayState.of(i), i.getPredictedQuality(), i.getReviewReason(),
                errorCodeOf(i), Times.toOffset(i.getReceivedAt()), urls.get(i.getId()), i.getFinalJudgement(),
                i.getJudgedBy(), Times.toOffset(confirmedAt.get(i.getId())))).toList();
    }

    // 목록에 보여 줄 오류 코드 (FAILED일 때만)
    public static String errorCodeOf(Inspection i) {
        return i.getStatus() == InspectionStatus.FAILED ? ErrorCode.fromStored(i.getErrorCode()).name() : null;
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
}
