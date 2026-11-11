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
import com.capstone.inspection.domain.inspection.InspectionStatus;
import com.capstone.inspection.domain.user.UserRepository;
import lombok.RequiredArgsConstructor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

// AI 없이 작업자 수동 판정으로 전환 (docs/수동판정_결정안.md B안, V6)
//   - FAILED 원본은 그대로 두고, 원본 사진을 재사용한 새 검사(source=MANUAL)를 COMPLETED·REVIEW(AI_UNAVAILABLE)로 만듦
//   - 판정은 새 검사에 기존 작업자 확인(confirm)으로 기록
//   - 실패 사유와 상관없이 모든 FAILED 허용, AI 모델 확인 안 함 (AI가 꺼져 있어도 써야 하는 기능)
//   - 재검사와 같은 retry_of_inspection_id(UNIQUE)로 원본과 연결 → FAILED 1건당 재검사 또는 수동 전환 1건만
@Service
@RequiredArgsConstructor
public class InspectionManualService {

    private static final Logger log = LoggerFactory.getLogger(InspectionManualService.class);

    private final InspectionRepository inspectionRepository;
    private final ImageStorageRepository imageRepository;
    private final UserRepository userRepository;
    private final InspectionNoGenerator inspectionNoGenerator;

    public record Result(Inspection manual, Inspection failed) {
    }

    @Transactional
    public Result convert(AuthUser requester, String inspectionId) {
        Inspection failed = inspectionRepository.findDetailById(inspectionId)
                .orElseThrow(() -> new BusinessException(ErrorCode.INSPECTION_NOT_FOUND));
        if (failed.getStatus() != InspectionStatus.FAILED) {
            throw new BusinessException(ErrorCode.NOT_MANUAL_CONVERTIBLE);
        }
        if (inspectionRepository.existsByRetryOfInspectionId(failed.getId())) {
            throw new BusinessException(ErrorCode.ALREADY_RETRIED);
        }
        ImageStorage original = imageRepository.findByInspectionIdAndImageType(failed.getId(), ImageType.ORIGINAL)
                .orElseThrow(() -> new BusinessException(ErrorCode.ORIGINAL_IMAGE_MISSING));

        Inspection manual = Inspection.manualOf(failed, inspectionNoGenerator.next(),
                userRepository.getReferenceById(requester.userId()), MDC.get(TraceIdFilter.MDC_KEY));
        try {
            inspectionRepository.saveAndFlush(manual);
        } catch (DataIntegrityViolationException e) {
            // 재검사·수동 전환 동시 요청: 먼저 커밋된 쪽만 남음
            throw new BusinessException(ErrorCode.ALREADY_RETRIED);
        }
        imageRepository.save(new ImageStorage(manual, ImageType.ORIGINAL, original.getStorageUri(),
                original.getContentType(), original.getSizeBytes(), original.getWidth(), original.getHeight(),
                original.getChecksum()));

        log.info("수동 판정 전환 {} {} manualOf={} {} error={} by={}", manual.getInspectionNo(), manual.getId(),
                failed.getInspectionNo(), failed.getId(), failed.getErrorCode(), requester.loginId());
        return new Result(manual, failed);
    }
}
