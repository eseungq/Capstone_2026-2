package com.capstone.inspection.inspection;

import com.capstone.inspection.auth.security.AuthUser;
import com.capstone.inspection.common.error.BusinessException;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.common.trace.TraceIdFilter;
import com.capstone.inspection.domain.inspection.ImageStorage;
import com.capstone.inspection.domain.inspection.ImageStorageRepository;
import com.capstone.inspection.domain.inspection.ImageType;
import com.capstone.inspection.domain.inspection.Inspection;
import com.capstone.inspection.domain.inspection.InspectionNoGenerator;
import com.capstone.inspection.domain.inspection.InspectionRepository;
import com.capstone.inspection.domain.inspection.InspectionSource;
import com.capstone.inspection.domain.inspection.InspectionStatus;
import com.capstone.inspection.domain.model.AiModel;
import com.capstone.inspection.domain.model.AiModelRepository;
import com.capstone.inspection.domain.user.UserRepository;
import lombok.RequiredArgsConstructor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

// FAILED 재검사 (계약 v4 6.8). 원래 FAILED 기록은 그대로 두고 새 검사를 만들어 기존 분석 흐름으로 처리
//   - 사진은 다시 받지 않고 원본의 저장 키·체크섬을 그대로 쓰는 image_storage 행을 새로 만듦
//   - 모델은 원래 검사의 모델이 아니라 부품(검사항목)의 현재 활성 모델
//   - FAILED 1건당 재검사 1회 (retry_of_inspection_id UNIQUE로도 보장)
@Service
@RequiredArgsConstructor
public class InspectionRetryService {

    private static final Logger log = LoggerFactory.getLogger(InspectionRetryService.class);

    private final InspectionRepository inspectionRepository;
    private final ImageStorageRepository imageRepository;
    private final AiModelRepository aiModelRepository;
    private final UserRepository userRepository;
    private final InspectionNoGenerator inspectionNoGenerator;
    private final ApplicationEventPublisher eventPublisher;

    @Transactional
    public Inspection retry(AuthUser requester, String inspectionId) {
        Inspection failed = inspectionRepository.findDetailById(inspectionId)
                .orElseThrow(() -> new BusinessException(ErrorCode.INSPECTION_NOT_FOUND));
        if (failed.getStatus() != InspectionStatus.FAILED) {
            throw new BusinessException(ErrorCode.NOT_RETRYABLE);
        }
        if (inspectionRepository.existsByRetryOfInspectionId(failed.getId())) {
            throw new BusinessException(ErrorCode.ALREADY_RETRIED);
        }
        List<AiModel> models = aiModelRepository.findActiveByItemId(failed.getItem().getId());
        if (models.isEmpty()) {
            throw new BusinessException(ErrorCode.MODEL_NOT_AVAILABLE);
        }
        ImageStorage original = imageRepository.findByInspectionIdAndImageType(failed.getId(), ImageType.ORIGINAL)
                .orElseThrow(() -> new IllegalStateException("원본 이미지 기록 없음 " + failed.getId()));

        // 같은 사진이므로 촬영 시각·라인은 원래 검사 값을 이어 씀
        Inspection retry = new Inspection(inspectionNoGenerator.next(),
                userRepository.getReferenceById(requester.userId()), InspectionSource.RETRY, failed.getPart(),
                failed.getItem(), models.get(0), failed.getLineCode(), failed.getCapturedAt(), null,
                failed.getId(), MDC.get(TraceIdFilter.MDC_KEY));
        try {
            inspectionRepository.saveAndFlush(retry);
        } catch (DataIntegrityViolationException e) {
            // 동시 재검사 요청: 먼저 커밋된 쪽만 남음
            throw new BusinessException(ErrorCode.ALREADY_RETRIED);
        }
        imageRepository.save(new ImageStorage(retry, ImageType.ORIGINAL, original.getStorageUri(),
                original.getContentType(), original.getSizeBytes(), original.getWidth(), original.getHeight(),
                original.getChecksum()));

        log.info("재검사 접수 {} {} retryOf={} {} by={}", retry.getInspectionNo(), retry.getId(),
                failed.getInspectionNo(), failed.getId(), requester.loginId());

        // 커밋 후 분석 시작 (AnalysisDispatcher가 받음)
        eventPublisher.publishEvent(new InspectionReceivedEvent(retry.getId()));
        return retry;
    }
}
