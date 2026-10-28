package com.capstone.inspection.inspection;

import com.capstone.inspection.auth.security.AuthUser;
import com.capstone.inspection.common.error.BusinessException;
import com.capstone.inspection.common.error.ErrorCode;
import com.capstone.inspection.common.time.Times;
import com.capstone.inspection.domain.inspection.Inspection;
import com.capstone.inspection.domain.inspection.InspectionRepository;
import com.capstone.inspection.domain.inspection.JudgedBy;
import com.capstone.inspection.domain.inspection.Judgement;
import com.capstone.inspection.domain.inspection.WorkerConfirmation;
import com.capstone.inspection.domain.inspection.WorkerConfirmationRepository;
import com.capstone.inspection.domain.user.UserRepository;
import com.capstone.inspection.inspection.dto.ConfirmRequest;
import com.capstone.inspection.inspection.dto.ConfirmResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

// 작업자 확인 (계약 v4 6.7). REVIEW_PENDING 건에 작업자 최종 판정을 기록
//   - AI 결과·정책 결과는 그대로 두고 worker_confirmation 1건 + inspection의 final_judgement·judged_by만 기록
//   - 같은 값 재전송은 기존 결과(200), 다른 값은 409 ALREADY_CONFIRMED
//   - 동시 제출: 조건부 갱신(final_judgement IS NULL) + worker_confirmation.inspection_id UNIQUE로 1건만 저장.
//     진 쪽은 저장 트랜잭션을 롤백하고, 새 트랜잭션에서 이긴 쪽 결과를 읽어 재전송 규칙대로 응답
@Service
public class InspectionConfirmService {

    private static final Logger log = LoggerFactory.getLogger(InspectionConfirmService.class);

    private final InspectionRepository inspectionRepository;
    private final WorkerConfirmationRepository confirmationRepository;
    private final UserRepository userRepository;
    private final TransactionTemplate tx;
    private final TransactionTemplate readTx;

    public InspectionConfirmService(InspectionRepository inspectionRepository,
                                    WorkerConfirmationRepository confirmationRepository,
                                    UserRepository userRepository,
                                    PlatformTransactionManager txManager) {
        this.inspectionRepository = inspectionRepository;
        this.confirmationRepository = confirmationRepository;
        this.userRepository = userRepository;
        this.tx = new TransactionTemplate(txManager);
        this.readTx = new TransactionTemplate(txManager);
        this.readTx.setReadOnly(true);
    }

    // 다른 요청이 먼저 판정을 기록한 경우 (저장 트랜잭션 롤백용)
    private static final class LostRace extends RuntimeException {
        LostRace() {
            super(null, null, false, false);
        }
    }

    public ConfirmResponse confirm(AuthUser worker, String inspectionId, ConfirmRequest request) {
        String comment = request.comment() == null || request.comment().isBlank() ? null : request.comment().trim();
        try {
            return tx.execute(status -> save(worker, inspectionId, request.finalJudgement(), comment));
        } catch (LostRace | DataIntegrityViolationException e) {
            log.info("동시 확인 요청: 먼저 저장된 판정 기준으로 응답 {}", inspectionId);
            return readTx.execute(status -> replayExisting(inspectionId, request.finalJudgement()));
        }
    }

    private ConfirmResponse save(AuthUser worker, String inspectionId, Judgement judgement, String comment) {
        Inspection i = inspectionRepository.findDetailById(inspectionId)
                .orElseThrow(() -> new BusinessException(ErrorCode.INSPECTION_NOT_FOUND));

        // 이미 확인된 건: 재전송 규칙
        WorkerConfirmation existing = confirmationRepository.findByInspectionIdWithWorker(inspectionId).orElse(null);
        if (existing != null) {
            return replay(i, existing, judgement);
        }
        if (DisplayState.of(i) != DisplayState.REVIEW_PENDING) {
            throw new BusinessException(ErrorCode.NOT_REVIEWABLE); // AUTO_PASS·FAILED·분석 중
        }

        if (inspectionRepository.markWorkerJudgement(inspectionId, judgement) != 1) {
            throw new LostRace();
        }
        WorkerConfirmation saved = confirmationRepository.saveAndFlush(
                new WorkerConfirmation(i, userRepository.getReferenceById(worker.userId()), judgement, comment));
        log.info("작업자 확인 {} {} {} by={}", i.getInspectionNo(), i.getId(), judgement, worker.loginId());
        return new ConfirmResponse(i.getId(), i.getInspectionNo(), i.getPredictedQuality(), i.getRecommendedAction(),
                judgement, JudgedBy.WORKER, worker.loginId(), Times.toOffset(saved.getConfirmedAt()));
    }

    private ConfirmResponse replayExisting(String inspectionId, Judgement judgement) {
        Inspection i = inspectionRepository.findDetailById(inspectionId)
                .orElseThrow(() -> new BusinessException(ErrorCode.INSPECTION_NOT_FOUND));
        WorkerConfirmation existing = confirmationRepository.findByInspectionIdWithWorker(inspectionId)
                .orElseThrow(() -> new BusinessException(ErrorCode.NOT_REVIEWABLE));
        return replay(i, existing, judgement);
    }

    private static ConfirmResponse replay(Inspection i, WorkerConfirmation existing, Judgement judgement) {
        if (existing.getFinalJudgement() != judgement) {
            throw new BusinessException(ErrorCode.ALREADY_CONFIRMED);
        }
        return ConfirmResponse.of(i, existing);
    }
}
