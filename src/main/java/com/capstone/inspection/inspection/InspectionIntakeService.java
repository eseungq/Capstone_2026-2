package com.capstone.inspection.inspection;

import com.capstone.inspection.auth.security.AuthUser;
import com.capstone.inspection.common.error.BusinessException;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.common.trace.TraceIdFilter;
import com.capstone.inspection.config.AppProperties;
import com.capstone.inspection.domain.inspection.ImageStorage;
import com.capstone.inspection.domain.inspection.ImageStorageRepository;
import com.capstone.inspection.domain.inspection.ImageType;
import com.capstone.inspection.domain.inspection.Inspection;
import com.capstone.inspection.domain.inspection.InspectionNoGenerator;
import com.capstone.inspection.domain.inspection.InspectionRepository;
import com.capstone.inspection.domain.inspection.InspectionSource;
import com.capstone.inspection.domain.model.AiModel;
import com.capstone.inspection.domain.model.AiModelRepository;
import com.capstone.inspection.domain.part.InspectionItem;
import com.capstone.inspection.domain.part.InspectionItemRepository;
import com.capstone.inspection.domain.part.Part;
import com.capstone.inspection.domain.part.PartRepository;
import com.capstone.inspection.domain.user.Role;
import com.capstone.inspection.domain.user.UserRepository;
import com.capstone.inspection.inspection.ImageInspector.ImageInfo;
import com.capstone.inspection.storage.StorageService;
import lombok.RequiredArgsConstructor;
import org.slf4j.MDC;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.io.IOException;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Optional;

// 사진 접수 (계약 v4 6.2). 입력 검증 → 원본 저장 → RECEIVED 기록 → 커밋 후 분석 시작
@Service
@RequiredArgsConstructor
public class InspectionIntakeService {

    private static final DateTimeFormatter DATE_PATH = DateTimeFormatter.ofPattern("yyyy/MM/dd");

    private final AppProperties props;
    private final PartRepository partRepository;
    private final InspectionItemRepository itemRepository;
    private final AiModelRepository aiModelRepository;
    private final UserRepository userRepository;
    private final InspectionRepository inspectionRepository;
    private final ImageStorageRepository imageRepository;
    private final InspectionNoGenerator inspectionNoGenerator;
    private final StorageService storageService;
    private final ApplicationEventPublisher eventPublisher;

    public record Receipt(Inspection inspection, boolean replayed) {
    }

    @Transactional
    public Receipt receive(AuthUser requester, String partCode, byte[] image, String lineCode,
                           LocalDateTime capturedAt, String idempotencyKey) {
        // 1) 입력 검증 (검사 기록을 만들기 전에 거절)
        if (image == null || image.length == 0) {
            throw new BusinessException(ErrorCode.INVALID_IMAGE_FORMAT);
        }
        if (image.length > props.upload().maxBytes()) {
            throw new BusinessException(ErrorCode.IMAGE_TOO_LARGE);
        }
        ImageInfo info = ImageInspector.inspect(image);
        if (info == null || !props.upload().allowedContentTypes().contains(info.contentType())) {
            throw new BusinessException(ErrorCode.INVALID_IMAGE_FORMAT);
        }
        if (info.width() < props.upload().minWidth() || info.height() < props.upload().minHeight()) {
            throw new BusinessException(ErrorCode.IMAGE_RESOLUTION_TOO_LOW);
        }
        Part part = partRepository.findByPartCode(partCode)
                .orElseThrow(() -> new BusinessException(ErrorCode.INVALID_PART_CODE));
        String checksum = Hashes.sha256(image);

        // 2) 같은 Idempotency-Key 재전송이면 기존 검사 반환, 내용이 다르면 422 (계약 6.2)
        String key = (idempotencyKey == null || idempotencyKey.isBlank()) ? null : idempotencyKey.trim();
        if (key != null) {
            Optional<Inspection> existing = inspectionRepository.findByUserIdAndClientRequestId(requester.userId(), key);
            if (existing.isPresent()) {
                return replayOrReject(existing.get(), part, checksum);
            }
        }

        // 3) 부품의 검사항목과 활성 모델 (없으면 기록 없이 422)
        InspectionItem item = itemRepository.findByPartId(part.getId()).stream().findFirst()
                .orElseThrow(() -> new BusinessException(ErrorCode.MODEL_NOT_AVAILABLE));
        List<AiModel> models = aiModelRepository.findActiveByItemId(item.getId());
        if (models.isEmpty()) {
            throw new BusinessException(ErrorCode.MODEL_NOT_AVAILABLE);
        }

        // 4) 검사 기록 + 원본 저장 (같은 트랜잭션. 원본 없는 검사는 만들지 않음)
        InspectionSource source = requester.role() == Role.ADMIN ? InspectionSource.ADMIN : InspectionSource.DEVICE;
        Inspection inspection = new Inspection(inspectionNoGenerator.next(),
                userRepository.getReferenceById(requester.userId()), source, part, item, models.get(0),
                blankToNull(lineCode), capturedAt, key, null, MDC.get(TraceIdFilter.MDC_KEY));
        inspectionRepository.save(inspection);

        String storageKey = "original/" + LocalDate.now().format(DATE_PATH) + "/" + inspection.getId() + "." + info.extension();
        try {
            storageService.save(storageKey, image);
        } catch (IOException e) {
            throw new BusinessException(ErrorCode.STORAGE_UPLOAD_FAILED);
        }
        imageRepository.save(new ImageStorage(inspection, ImageType.ORIGINAL, storageKey, info.contentType(),
                image.length, info.width(), info.height(), checksum));

        // 5) 커밋 후 분석 시작 (AnalysisDispatcher가 받음)
        eventPublisher.publishEvent(new InspectionReceivedEvent(inspection.getId()));
        return new Receipt(inspection, false);
    }

    private Receipt replayOrReject(Inspection existing, Part part, String checksum) {
        boolean samePart = existing.getPart().getId().equals(part.getId());
        boolean sameImage = imageRepository.findByInspectionIdAndImageType(existing.getId(), ImageType.ORIGINAL)
                .map(img -> img.getChecksum().equals(checksum))
                .orElse(false);
        if (samePart && sameImage) {
            return new Receipt(existing, true);
        }
        throw new BusinessException(ErrorCode.IDEMPOTENCY_KEY_MISMATCH);
    }

    private static String blankToNull(String s) {
        return (s == null || s.isBlank()) ? null : s.trim();
    }
}
